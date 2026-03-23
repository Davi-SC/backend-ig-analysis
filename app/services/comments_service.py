"""
Extract Service 1.4 — comments_service
Responsável por coletar e persistir comentários e replies de todos os posts.
Design de armazenamento:
  - Replies são embutidas no documento do comentário (não collection separada)
  - Relação 1:N  -> embed é ideal
  - Leitura de comentário + replies = operação de documento único

Fluxo do DAG:
  1. Roda APÓS snapshot_service
  2. Lê todos os post_ids ativos do banco
  3. Para cada post:
     a. Busca comentários com paginação
     b. Para cada comentário: busca replies com paginação
     c. Tenta insert_one (DuplicateKeyError = já existe, skip)
  4. Retorna resumo com totais de novos, já existentes e erros

Endpoints (v25.0):
  GET /{base_url}/{version}/{media_id}/comments
      ?fields=id,text,timestamp,like_count,username
  GET /{base_url}/{version}/{comment_id}/replies
      ?fields=id,text,timestamp,username
"""

import logging
import requests
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser

from pymongo.errors import DuplicateKeyError

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v25.0"

COMMENT_FIELDS = "id,text,timestamp,like_count,username"
REPLY_FIELDS   = "id,text,timestamp,username"


def _get_token_doc(profile_id: str) -> dict | None:
    """Busca token válido no MongoDB. Retorna None se inválido/expirado."""
    doc = mongo_repo.oauth_tokens.find_one({"profile_id": profile_id})
    if not doc:
        logger.error(f"[comments_service] Token não encontrado para profile_id={profile_id}")
        return None
    if not doc.get("is_valid", False):
        logger.error(f"[comments_service] Token inválido para profile_id={profile_id}")
        return None
    expires_at = doc.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        logger.error(f"[comments_service] Token expirado para profile_id={profile_id}")
        return None
    return doc


def _get_base_url(auth_method: str) -> str:
    return (
        "https://graph.facebook.com" if auth_method == "facebook"
        else "https://graph.instagram.com"
    )


def _parse_dt(ts: str | None) -> datetime | None:
    """Converte string ISO 8601 da API para datetime UTC aware."""
    if not ts:
        return None
    try:
        return dateutil_parser.parse(ts).astimezone(timezone.utc)
    except Exception:
        return None


# ─── API fetch functions ──────────────────────────────────────────────────────

def fetch_comments(
    base_url: str, media_id: str, access_token: str, limit: int = 100
) -> list[dict]:
    """
    Coleta todos os comentários de um post com paginação.
    Retorna lista de dicts brutos da API.
    """
    all_comments: list[dict] = []
    next_url = (
        f"{base_url}/{GRAPH_VERSION}/{media_id}/comments"
        f"?fields={COMMENT_FIELDS}&limit={limit}&access_token={access_token}"
    )

    while next_url:
        try:
            response = requests.get(next_url, timeout=15)
        except requests.RequestException as e:
            logger.error(f"[comments_service] Erro de rede ao buscar comentários de {media_id}: {e}")
            break

        if response.status_code != 200:
            error_msg = response.json().get("error", {}).get("message", response.text)
            logger.warning(f"[comments_service] Erro {response.status_code} nos comentários de {media_id}: {error_msg}")
            break

        data = response.json()
        all_comments.extend(data.get("data", []))
        next_url = data.get("paging", {}).get("next")

    return all_comments


def fetch_replies(
    base_url: str, comment_id: str, access_token: str, limit: int = 100
) -> list[dict]:
    """
    Coleta todas as replies de um comentário com paginação.
    Retorna lista de dicts brutos da API.
    """
    all_replies: list[dict] = []
    next_url = (
        f"{base_url}/{GRAPH_VERSION}/{comment_id}/replies"
        f"?fields={REPLY_FIELDS}&limit={limit}&access_token={access_token}"
    )

    while next_url:
        try:
            response = requests.get(next_url, timeout=15)
        except requests.RequestException as e:
            logger.error(f"[comments_service] Erro de rede ao buscar replies de {comment_id}: {e}")
            break

        if response.status_code != 200:
            # Comentários sem replies retornam 200 com data:[], não é erro
            # Mas alguns comentários antigos podem retornar 400 — ignoramos silenciosamente
            logger.debug(f"[comments_service] Sem replies ou erro em {comment_id}: {response.status_code}")
            break

        data = response.json()
        all_replies.extend(data.get("data", []))
        next_url = data.get("paging", {}).get("next")

    return all_replies


# ─── Mapping ──────────────────────────────────────────────────────────────────

def _map_reply(raw: dict) -> dict:
    """Mapeia reply bruta da API para o formato de embed no documento do comentário."""
    return {
        "reply_id":    raw["id"],
        "username":    raw.get("username", ""),
        "text":        raw.get("text", ""),
        "published_at": _parse_dt(raw.get("timestamp")),
    }


def _map_comment(raw: dict, post_id: str, profile_id: str, replies: list[dict], collected_at: datetime) -> dict:
    """Mapeia comentário bruto + replies para o formato da collection 'comments'."""
    return {
        "comment_id":      raw["id"],
        "post_id":         post_id,
        "profile_id":      profile_id,
        "username":        raw.get("username", ""),
        "text":            raw.get("text", ""),
        "like_count":      raw.get("like_count", 0),
        "published_at":    _parse_dt(raw.get("timestamp")),
        "collected_at":    collected_at,
        "replies":         [_map_reply(r) for r in replies],
        # Preenchidos depois pelo sentiment_service
        "sentiment_score": None,
        "sentiment_label": None,
    }


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_comments_service(profile_id: str) -> dict:
    """
    Ponto de entrada principal — chamado pelo DAG do Airflow.

    Lê os post_ids do banco (não da API) para garantir que só processa
    posts que já foram descobertos pelo media_discovery_service.

    Retorna:
        {
            "status": "ok" | "error",
            "profile_id": str,
            "posts_processed": int,
            "comments_new": int,         # inseridos agora
            "comments_known": int,       # já existiam (DuplicateKeyError)
            "comments_error": int,       # falha inesperada na inserção
            "message": str,
        }
    """
    logger.info(f"[comments_service] Iniciando coleta de comentários para profile_id={profile_id}")

    # 1. Token
    token_doc = _get_token_doc(profile_id)
    if not token_doc:
        return {
            "status": "error", "profile_id": profile_id,
            "posts_processed": 0, "comments_new": 0,
            "comments_known": 0, "comments_error": 0,
            "message": "Token não encontrado, inválido ou expirado",
        }

    access_token = token_doc["long_lived_token"]
    auth_method  = token_doc.get("auth_method", "facebook")
    base_url     = _get_base_url(auth_method)
    collected_at = datetime.now(timezone.utc)

    # 2. Lê post_ids do banco (apenas os do perfil, sem trazer documentos inteiros)
    post_ids = [
        doc["post_id"]
        for doc in mongo_repo.posts.find(
            {"profile_id": profile_id},
            {"post_id": 1, "_id": 0},
        )
    ]

    if not post_ids:
        logger.warning(f"[comments_service] Nenhum post encontrado no banco para profile_id={profile_id}")
        return {
            "status": "ok", "profile_id": profile_id,
            "posts_processed": 0, "comments_new": 0,
            "comments_known": 0, "comments_error": 0,
            "message": "Nenhum post encontrado no banco. Execute media_discovery_service primeiro.",
        }

    logger.info(f"[comments_service] {len(post_ids)} posts a processar")

    # 3. Para cada post: busca comentários e replies
    comments_new   = 0
    comments_known = 0
    comments_error = 0

    for post_id in post_ids:
        raw_comments = fetch_comments(base_url, post_id, access_token)

        if not raw_comments:
            continue

        for raw_comment in raw_comments:
            comment_id = raw_comment.get("id")
            if not comment_id:
                continue

            # Busca replies deste comentário
            raw_replies = fetch_replies(base_url, comment_id, access_token)

            comment_doc = _map_comment(raw_comment, post_id, profile_id, raw_replies, collected_at)

            try:
                mongo_repo.comments.insert_one(comment_doc)
                comments_new += 1
            except DuplicateKeyError:
                # Comentário já estava no banco — skip silencioso
                comments_known += 1
            except Exception as e:
                logger.error(f"[comments_service] Erro ao inserir comment_id={comment_id}: {e}")
                comments_error += 1

        logger.info(
            f"[comments_service] post_id={post_id} | "
            f"comentários={len(raw_comments)} | novos={comments_new} | skip={comments_known}"
        )

    total_comments = comments_new + comments_known + comments_error
    logger.info(
        f"[comments_service] Concluído: posts={len(post_ids)} | "
        f"total={total_comments} | novos={comments_new} | já existiam={comments_known} | erros={comments_error}"
    )

    return {
        "status": "ok",
        "profile_id": profile_id,
        "posts_processed": len(post_ids),
        "comments_new":   comments_new,
        "comments_known": comments_known,
        "comments_error": comments_error,
        "message": f"{comments_new} comentários inseridos, {comments_known} já existiam",
    }
