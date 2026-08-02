"""
Dependency de autenticação — FastAPI

Uso em endpoints protegidos:
    from app.utils.auth import get_authenticated_profile

    @router.get("/data/profile")
    async def get_profile(profile_id: str = Depends(get_authenticated_profile)):
        ...

Fluxo:
    1. Lê o header obrigatório `X-Profile-ID`
    2. Busca o documento na collection `oauth_tokens` do MongoDB
    3. Valida: token presente + is_valid = True + não expirado
    4. Retorna o `profile_id` validado, ou levanta HTTP 401

O `access_token` NUNCA sai do backend — o frontend só envia o `profile_id`.
"""

import logging
from datetime import datetime, timezone

from fastapi import Header, HTTPException, status

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)


def get_authenticated_profile(x_profile_id: str = Header(..., alias="X-Profile-ID")) -> str:
    """
    FastAPI Dependency: valida o `X-Profile-ID` recebido no header.

    Retorna o `profile_id` se o token no banco for válido e não expirado.
    Levanta HTTP 401 em qualquer falha de autenticação.

    Parâmetros (via header):
        X-Profile-ID (str): ID do perfil Instagram retornado após o OAuth.

    Returns:
        str: profile_id validado.

    Raises:
        HTTPException 401: token não encontrado, inválido ou expirado.
    """
    if not x_profile_id or not x_profile_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header X-Profile-ID ausente ou vazio.",
        )

    profile_id = x_profile_id.strip()

    try:
        token_doc = mongo_repo.oauth_tokens.find_one({"profile_id": profile_id})
    except Exception as e:
        logger.error(f"[auth] Erro ao buscar token para profile_id={profile_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Erro interno ao validar autenticação.",
        )

    if not token_doc:
        logger.warning(f"[auth] Token não encontrado para profile_id={profile_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Perfil não autenticado. Faça login novamente.",
        )

    if not token_doc.get("is_valid", False):
        logger.warning(f"[auth] Token marcado como inválido para profile_id={profile_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido. Faça login novamente.",
        )

    expires_at = token_doc.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        logger.warning(f"[auth] Token expirado para profile_id={profile_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado. Faça login novamente.",
        )

    return profile_id
