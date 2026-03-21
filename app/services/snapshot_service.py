"""
Extract Service 1.3 — snapshot_service
Responsável pela fotografia diária do estado de um perfil e de seus posts.
Duas collections escritas por este service:

  profile_snapshots -> um documento por perfil por dia
      profile_id, date, followers_count, follows_count, media_count
  post_snapshots -> um documento por post por dia
      post_id, profile_id, date, like_count, comments_count, followers_at_date
"""

import logging
import requests
from datetime import datetime, date, timezone

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v25.0"

# Campos mínimos para o profile_snapshot
PROFILE_SNAPSHOT_FIELDS = "id,followers_count,follows_count,media_count"

# Campos mínimos para post_snapshots (não precisamos de caption, permalink, etc.)
POST_SNAPSHOT_FIELDS = "id,like_count,comments_count"


def _get_token_doc(profile_id: str) -> dict | None:
    """Busca token válido no MongoDB. Retorna None se inválido ou expirado."""
    doc = mongo_repo.oauth_tokens.find_one({"profile_id": profile_id})
    if not doc:
        logger.error(f"[snapshot_service] Token não encontrado para profile_id={profile_id}")
        return None
    if not doc.get("is_valid", False):
        logger.error(f"[snapshot_service] Token inválido para profile_id={profile_id}")
        return None
    expires_at = doc.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        logger.error(f"[snapshot_service] Token expirado para profile_id={profile_id}")
        return None
    return doc


def _get_base_url(auth_method: str) -> str:
    return (
        "https://graph.facebook.com" if auth_method == "facebook"
        else "https://graph.instagram.com"
    )


# ─── Profile snapshot ─────────────────────────────────────────────────────────

def fetch_profile_counts(profile_id: str, access_token: str, auth_method: str) -> dict | None:
    """
    Busca apenas os contadores do perfil necessários para o profile_snapshot.
    Usa o mesmo endpoint do profile_service, mas com campos mínimos.
    """
    base_url = _get_base_url(auth_method)

    if auth_method == "facebook":
        endpoint = f"{base_url}/{GRAPH_VERSION}/{profile_id}"
    else:
        endpoint = f"{base_url}/{GRAPH_VERSION}/me"

    try:
        response = requests.get(
            endpoint,
            params={"fields": PROFILE_SNAPSHOT_FIELDS, "access_token": access_token},
            timeout=15,
        )
    except requests.RequestException as e:
        logger.error(f"[snapshot_service] Erro de rede ao buscar contadores do perfil: {e}")
        return None

    if response.status_code == 200:
        return response.json()

    error_msg = response.json().get("error", {}).get("message", response.text)
    logger.error(f"[snapshot_service] Erro {response.status_code} ao buscar perfil: {error_msg}")
    return None


def upsert_profile_snapshot(
    profile_id: str,
    snapshot_date: date,
    followers_count: int,
    follows_count: int,
    media_count: int,
    collected_at: datetime,
) -> bool:
    """
    Insere ou atualiza o profile_snapshot do dia.
    O índice único (profile_id, date) garante idempotência.
    """
    result = mongo_repo.profile_snapshots.update_one(
        {"profile_id": profile_id, "date": snapshot_date.isoformat()},
        {"$set": {
            "profile_id":      profile_id,
            "date":            snapshot_date.isoformat(),
            "followers_count": followers_count,
            "follows_count":   follows_count,
            "media_count":     media_count,
            "collected_at":    collected_at,
        }},
        upsert=True,
    )
    action = "inserido" if result.upserted_id else "atualizado"
    logger.info(
        f"[snapshot_service] profile_snapshot {action}: "
        f"profile_id={profile_id} | date={snapshot_date} | followers={followers_count}"
    )
    return True


# ─── Post snapshots ───────────────────────────────────────────────────────────

def fetch_all_post_counts(
    profile_id: str,
    access_token: str,
    auth_method: str,
    limit: int = 100,
) -> list[dict]:
    """
    Coleta os contadores atuais de todos os posts com paginação cursor-based.

    Usa apenas os campos necessários para o snapshot (id, like_count, comments_count).
    Mesma lógica de paginação do media_discovery_service.
    """
    base_url = _get_base_url(auth_method)
    all_posts: list[dict] = []
    page_num = 1
    next_url = (
        f"{base_url}/{GRAPH_VERSION}/{profile_id}/media"
        f"?fields={POST_SNAPSHOT_FIELDS}&limit={limit}&access_token={access_token}"
    )

    while next_url:
        try:
            response = requests.get(next_url, timeout=20)
        except requests.RequestException as e:
            logger.error(f"[snapshot_service] Erro de rede na página {page_num} de posts: {e}")
            break

        if response.status_code != 200:
            error_msg = response.json().get("error", {}).get("message", response.text)
            logger.error(f"[snapshot_service] Erro {response.status_code} na página {page_num}: {error_msg}")
            break

        data = response.json()
        posts = data.get("data", [])
        all_posts.extend(posts)
        logger.info(f"[snapshot_service] Posts página {page_num:>3} | +{len(posts):>3} | Total: {len(all_posts):>5}")

        next_url = data.get("paging", {}).get("next")
        page_num += 1

    return all_posts


def bulk_upsert_post_snapshots(
    posts: list[dict],
    profile_id: str,
    snapshot_date: date,
    followers_at_date: int,
    collected_at: datetime,
) -> dict:
    """
    Faz upsert em lote de todos os post_snapshots do dia usando bulk_write.

    Mais eficiente que um loop de update_one, envia todas as operações
    em uma única round-trip ao MongoDB.
    """
    if not posts:
        return {"upserted": 0, "modified": 0}

    date_str = snapshot_date.isoformat()

    operations = [
        UpdateOne(
            {"post_id": post["id"], "date": date_str},
            {"$set": {
                "post_id":           post["id"],
                "profile_id":        profile_id,
                "date":              date_str,
                "like_count":        post.get("like_count", 0),
                "comments_count":    post.get("comments_count", 0),
                "followers_at_date": followers_at_date,
                "collected_at":      collected_at,
            }},
            upsert=True,
        )
        for post in posts
    ]

    try:
        result = mongo_repo.post_snapshots.bulk_write(operations, ordered=False)
        upserted = result.upserted_count
        modified = result.modified_count
        logger.info(
            f"[snapshot_service] post_snapshots bulk_write: "
            f"upserted={upserted} | modified={modified} | total={len(posts)}"
        )
        return {"upserted": upserted, "modified": modified}
    except BulkWriteError as e:
        logger.error(f"[snapshot_service] BulkWriteError: {e.details}")
        return {"upserted": 0, "modified": 0}


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_snapshot_service(profile_id: str, target_date: date | None = None) -> dict:
    """
    Ponto de entrada principal, chamado pelo DAG do Airflow.

    target_date: data do snapshot. None = hoje (UTC).
    Retorna:
        {
            "status": "ok" | "error",
            "profile_id": str,
            "date": str (YYYY-MM-DD),
            "followers_count": int,
            "posts_processed": int,
            "post_snapshots_upserted": int,
            "post_snapshots_updated": int,
            "message": str,
        }
    """
    snapshot_date = target_date or datetime.now(timezone.utc).date()
    collected_at  = datetime.now(timezone.utc)

    logger.info(f"[snapshot_service] Iniciando snapshot: profile_id={profile_id} | date={snapshot_date}")

    # 1. Token
    token_doc = _get_token_doc(profile_id)
    if not token_doc:
        return {
            "status": "error", "profile_id": profile_id,
            "date": snapshot_date.isoformat(),
            "message": "Token não encontrado, inválido ou expirado",
        }

    access_token = token_doc["long_lived_token"]
    auth_method  = token_doc.get("auth_method", "facebook")

    # 2. Profile snapshot
    profile_data = fetch_profile_counts(profile_id, access_token, auth_method)
    if not profile_data:
        return {
            "status": "error", "profile_id": profile_id,
            "date": snapshot_date.isoformat(),
            "message": "Falha ao buscar contadores do perfil",
        }

    followers_count = profile_data.get("followers_count", 0)
    follows_count   = profile_data.get("follows_count", 0)
    media_count     = profile_data.get("media_count", 0)

    upsert_profile_snapshot(
        profile_id, snapshot_date,
        followers_count, follows_count, media_count,
        collected_at,
    )

    # 3. Post snapshots (com followers_at_date)
    raw_posts = fetch_all_post_counts(profile_id, access_token, auth_method)

    post_results = bulk_upsert_post_snapshots(
        raw_posts, profile_id, snapshot_date,
        followers_at_date=followers_count,
        collected_at=collected_at,
    )

    logger.info(
        f"[snapshot_service] Concluído: profile_id={profile_id} | date={snapshot_date} | "
        f"followers={followers_count} | posts={len(raw_posts)}"
    )

    return {
        "status": "ok",
        "profile_id": profile_id,
        "date": snapshot_date.isoformat(),
        "followers_count": followers_count,
        "posts_processed": len(raw_posts),
        "post_snapshots_upserted": post_results["upserted"],
        "post_snapshots_updated":  post_results["modified"],
        "message": f"Snapshot de {snapshot_date} concluído com sucesso",
    }