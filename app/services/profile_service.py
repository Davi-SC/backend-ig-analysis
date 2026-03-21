"""
Extract Service 1.1 — profile_service
Responsável por coletar os dados estáticos do perfil Instagram via Graph API
e fazer upsert em 'ig_profiles', enriquecendo o documento criado no OAuth.

Suporta dois fluxos de autenticação:
  - facebook:   GET graph.facebook.com/v25.0/{ig_user_id}
                (account_type não disponível neste fluxo)
  - instagram:  GET graph.instagram.com/v25.0/me
                (account_type disponível)

O token e o profile_id são lidos do MongoDB (oauth_tokens)
"""

import logging
import requests
from datetime import datetime, timezone

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v25.0"

# Campos solicitados por auth_method.
# facebook: account_type NÃO está disponível neste fluxo de API.
PROFILE_FIELDS = {
    "facebook": "id,username,name,biography,website,followers_count,follows_count,media_count,profile_picture_url",
    "instagram": "id,username,name,biography,website,followers_count,follows_count,media_count,profile_picture_url,account_type",
}


def _get_token_doc(profile_id: str) -> dict | None:
    """
    Busca o documento de token no MongoDB.
    Retorna None se o token não existir ou estiver inválido/expirado.
    """
    doc = mongo_repo.oauth_tokens.find_one({"profile_id": profile_id})
    if not doc:
        logger.error(f"[profile_service] Token não encontrado para profile_id={profile_id}")
        return None

    if not doc.get("is_valid", False):
        logger.error(f"[profile_service] Token inválido para profile_id={profile_id}")
        return None

    expires_at = doc.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        logger.error(f"[profile_service] Token expirado para profile_id={profile_id} (expirou em {expires_at})")
        return None

    return doc


def fetch_profile(profile_id: str, access_token: str, auth_method: str) -> dict | None:
    """
    Chama a Graph API e retorna os dados brutos do perfil.

    Diferença entre fluxos:
      - facebook:   endpoint /{ig_user_id}
      - instagram:  endpoint /me
    """
    if auth_method == "facebook":
        base_url = "https://graph.facebook.com"
        endpoint = f"{base_url}/{GRAPH_VERSION}/{profile_id}"
    else:
        base_url = "https://graph.instagram.com"
        endpoint = f"{base_url}/{GRAPH_VERSION}/me"

    fields = PROFILE_FIELDS.get(auth_method, PROFILE_FIELDS["facebook"])

    try:
        response = requests.get(
            endpoint,
            params={"fields": fields, "access_token": access_token},
            timeout=15,
        )
    except requests.RequestException as e:
        logger.error(f"[profile_service] Erro de rede ao buscar perfil {profile_id}: {e}")
        return None

    if response.status_code == 200:
        data = response.json()
        logger.info(f"[profile_service] Perfil coletado: profile_id={data.get('id')} | username={data.get('username')!r}")
        return data

    error_msg = response.json().get("error", {}).get("message", response.text)
    logger.error(f"[profile_service] Erro {response.status_code} ao buscar perfil {profile_id}: {error_msg}")
    return None


def run_profile_service(profile_id: str) -> dict:
    """
    Ponto de entrada principal — chamado pelo DAG do Airflow.
    Fluxo:
      1. Busca token em oauth_tokens
      2. Chama API Graph
      3. Faz upsert em ig_profiles com os campos enriquecidos
      4. Retorna resumo da operação
    Retorna:
        {
            "status": "ok" | "error",
            "profile_id": str,
            "username": str | None,
            "message": str,
        }
    """
    logger.info(f"[profile_service] Iniciando coleta para profile_id={profile_id}")

    # 1. Token
    token_doc = _get_token_doc(profile_id)
    if not token_doc:
        return {"status": "error", "profile_id": profile_id, "username": None,
                "message": "Token não encontrado, inválido ou expirado"}

    access_token = token_doc["long_lived_token"]
    auth_method = token_doc.get("auth_method", "facebook")

    # 2. API
    profile_data = fetch_profile(profile_id, access_token, auth_method)
    if not profile_data:
        return {"status": "error", "profile_id": profile_id, "username": None,
                "message": "Falha ao buscar dados do perfil na Graph API"}

    # 3. Upsert em ig_profiles
    now = datetime.now(timezone.utc)

    # account_type só está disponível no fluxo instagram
    raw_account_type = profile_data.get("account_type")   # None para fluxo facebook
    valid_types = {"BUSINESS", "MEDIA_CREATOR", "PERSONAL"}
    ig_account_type = raw_account_type if raw_account_type in valid_types else None

    update_fields = {
        "username":        profile_data.get("username"),
        "name":            profile_data.get("name"),
        "biography":       profile_data.get("biography"),
        "website":         profile_data.get("website"),
        "ig_account_type": ig_account_type,
        "updated_at":      now,
    }
    # Remove campos None para não sobrescrever valores já existentes com None
    update_fields = {k: v for k, v in update_fields.items() if v is not None}

    mongo_repo.ig_profiles.update_one(
        {"profile_id": profile_id},
        {
            "$set": update_fields,
            "$setOnInsert": {"created_at": now, "is_active": True},
        },
        upsert=True,
    )

    username = profile_data.get("username")
    logger.info(f"[profile_service] ig_profiles atualizado: profile_id={profile_id} | username={username!r} | ig_account_type={ig_account_type}")

    return {
        "status": "ok",
        "profile_id": profile_id,
        "username": username,
        "message": f"Perfil enriquecido com sucesso (ig_account_type={ig_account_type})",
    }
