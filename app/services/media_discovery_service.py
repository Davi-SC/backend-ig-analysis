"""
Extract Service 1.2 — media_discovery_service
Responsável por descobrir e persistir posts novos de um perfil Instagram.
Fluxo:
  GET /{ig_user_id}/media (idêntico para fluxos facebook e instagram)
  -> paginação cursor-based via paging.next (limit=100 por página)
  -> extração de hashtags do caption via regex
  -> insert_one em 'posts' (write-once — DuplicateKeyError = post já existia)

Por que write-once?
  Os metadados de um post não mudam após a publicação (caption, tipo, data).
  O que muda com o tempo (likes, comments) vive em 'post_snapshots', não aqui.
  Isso garante que qualquer re-run do DAG é 100% idempotente: se o post
  já existe no banco, simplesmente ignoramos e contamos como 'already_known'.

Campos coletados da API (v25.0):
  id, caption, media_type, media_url, thumbnail_url, permalink, timestamp,
  like_count, comments_count
"""

import re
import logging
import requests
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v25.0"

MEDIA_FIELDS = (
    "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,"
    "like_count,comments_count"
)

HASHTAG_PATTERN = re.compile(r"#(\w+)", re.UNICODE)


def _get_token_doc(profile_id: str) -> dict | None:
    """Busca token válido no MongoDB. Retorna None se inválido/expirado."""
    doc = mongo_repo.oauth_tokens.find_one({"profile_id": profile_id})
    if not doc:
        logger.error(f"[media_discovery] Token não encontrado para profile_id={profile_id}")
        return None
    if not doc.get("is_valid", False):
        logger.error(f"[media_discovery] Token inválido para profile_id={profile_id}")
        return None
    expires_at = doc.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        logger.error(f"[media_discovery] Token expirado para profile_id={profile_id}")
        return None
    return doc


def _extract_hashtags(caption: str | None) -> list[str]:
    """
    Extrai hashtags de uma legenda de post via regex.
    Retorna lista de strings sem o '#', lowercase.
    Ex: "Bom dia! #café #tech" → ["café", "tech"]
    """
    if not caption:
        return []
    return [tag.lower() for tag in HASHTAG_PATTERN.findall(caption)]


def _map_post(raw: dict, profile_id: str, collected_at: datetime) -> dict:
    """
    Mapeia um item bruto da API para o formato da collection 'posts'
    thumbnail_url é armazenado apenas para VIDEO.
    """
    media_type = raw.get("media_type", "IMAGE")
    caption = raw.get("caption", "")

    return {
        "post_id":        raw["id"],
        "profile_id":     profile_id,
        "media_type":     media_type,
        "caption":        caption,
        "hashtags":       _extract_hashtags(caption),
        "permalink":      raw.get("permalink"),
        # thumbnail_url só existe para VIDEO — None para IMAGE/CAROUSEL
        "thumbnail_url":  raw.get("thumbnail_url") if media_type == "VIDEO" else None,
        "published_at":   raw.get("timestamp"),   # ISO 8601 string da API
        "collected_at":   collected_at,
    }


def fetch_all_posts(profile_id: str, access_token: str, auth_method: str, limit: int = 100) -> list[dict]:
    """
    Coleta todos os posts do perfil com paginação cursor-based.

    O endpoint /{ig_user_id}/media funciona igual para os dois fluxos
    (facebook e instagram) — só muda o base_url.

    Limite prático da API: até 10.000 posts por perfil.
    Usa limit=100 por página.
    """
    base_url = (
        "https://graph.facebook.com" if auth_method == "facebook"
        else "https://graph.instagram.com"
    )

    all_posts: list[dict] = []
    page_num = 1
    next_url = (
        f"{base_url}/{GRAPH_VERSION}/{profile_id}/media"
        f"?fields={MEDIA_FIELDS}&limit={limit}&access_token={access_token}"
    )

    while next_url:
        try:
            response = requests.get(next_url, timeout=20)
        except requests.RequestException as e:
            logger.error(f"[media_discovery] Erro de rede na página {page_num}: {e}")
            break

        if response.status_code != 200:
            error_msg = response.json().get("error", {}).get("message", response.text)
            logger.error(f"[media_discovery] Erro {response.status_code} na página {page_num}: {error_msg}")
            break

        data = response.json()
        posts = data.get("data", [])
        all_posts.extend(posts)
        logger.info(f"[media_discovery] Página {page_num:>3} | +{len(posts):>3} posts | Total: {len(all_posts):>5}")

        next_url = data.get("paging", {}).get("next")
        page_num += 1

    logger.info(f"[media_discovery] Coleta concluída: {len(all_posts)} posts coletados da API")
    return all_posts


def run_media_discovery_service(profile_id: str) -> dict:
    """
    Ponto de entrada principal — chamado pelo DAG do Airflow.
    Fluxo:
      1. Busca token em oauth_tokens
      2. Coleta todos os posts via paginação
      3. Para cada post: tenta insert_one em 'posts'
         - Sucesso -> novo post descoberto
         - DuplicateKeyError -> post já existia (ignorado silenciosamente)
      4. Retorna resumo da operação
    Retorna:
        {
            "status": "ok" | "error",
            "profile_id": str,
            "total_fetched": int,     # posts retornados pela API
            "new_posts": int,         # inseridos agora
            "already_known": int,     # já existiam no banco
            "message": str,
        }
    """
    logger.info(f"[media_discovery] Iniciando descoberta de posts para profile_id={profile_id}")

    # 1. Token
    token_doc = _get_token_doc(profile_id)
    if not token_doc:
        return {
            "status": "error", "profile_id": profile_id,
            "total_fetched": 0, "new_posts": 0, "already_known": 0,
            "message": "Token não encontrado, inválido ou expirado",
        }

    access_token = token_doc["long_lived_token"]
    auth_method = token_doc.get("auth_method", "facebook")

    # 2. Coleta da API
    raw_posts = fetch_all_posts(profile_id, access_token, auth_method)
    if not raw_posts:
        return {
            "status": "ok", "profile_id": profile_id,
            "total_fetched": 0, "new_posts": 0, "already_known": 0,
            "message": "Nenhum post retornado pela API",
        }

    # 3. Persist: write-once via insert_one + DuplicateKeyError handling
    collected_at = datetime.now(timezone.utc)
    new_posts = 0
    already_known = 0

    for raw in raw_posts:
        post_doc = _map_post(raw, profile_id, collected_at)
        try:
            mongo_repo.posts.insert_one(post_doc)
            new_posts += 1
        except DuplicateKeyError:
            # post_id já existe — comportamento esperado em re-runs do DAG
            already_known += 1
        except Exception as e:
            logger.error(f"[media_discovery] Erro ao inserir post {raw.get('id')}: {e}")

    logger.info(
        f"[media_discovery] Concluído: total={len(raw_posts)} | "
        f"novos={new_posts} | já existiam={already_known}"
    )

    return {
        "status": "ok",
        "profile_id": profile_id,
        "total_fetched": len(raw_posts),
        "new_posts": new_posts,
        "already_known": already_known,
        "message": f"{new_posts} novos posts inseridos, {already_known} já existiam",
    }
