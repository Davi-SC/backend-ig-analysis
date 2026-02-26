"""
Rotas de autenticação OAuth para Instagram e Facebook.
"""

from fastapi import APIRouter, HTTPException, Query, status
import logging

from app.services.auth_service import (
    generate_fb_auth_url,
    generate_ig_auth_url,
    code_to_short_lived_token,
    short_to_long_lived_token,
    refresh_ig_token,
    validate_token,
)
from app.domain.schemas.auth_schemas import AuthUrlResponse, CallbackResponse, TokenValidationResponse

# Configurar logger
logger = logging.getLogger(__name__)

# Criar router
router = APIRouter(prefix="/auth", tags=["auth", "oauth"])


### >> Gerar URLs de autenticação << ###

@router.get("/fb/url", response_model=AuthUrlResponse, summary="Gera URL de login do Facebook")
async def get_fb_auth_url():
    """Retorna a URL para o usuário autorizar o app no Facebook."""
    try:
        url = generate_fb_auth_url()
        return AuthUrlResponse(url=url)
    except Exception as e:
        logger.error(f"Erro ao gerar URL FB: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao gerar URL de autenticação")


@router.get("/ig/url", response_model=AuthUrlResponse, summary="Gera URL de login do Instagram")
async def get_ig_auth_url():
    """Retorna a URL para o usuário autorizar o app no Instagram (Business Login)."""
    try:
        url = generate_ig_auth_url()
        return AuthUrlResponse(url=url)
    except Exception as e:
        logger.error(f"Erro ao gerar URL IG: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao gerar URL de autenticação")


### >> Callback — trocar code por token << ###

@router.get("/callback", response_model=CallbackResponse, summary="Troca o code OAuth por token de acesso")
async def callback(
    code: str = Query(..., description="Código retornado pelo Instagram/Facebook após o login"),
    is_instagram_only: bool = Query(False, description="True para fluxo Instagram Business, False para fluxo Facebook")
):
    """
    Recebe o `code` que o Instagram/Facebook envia ao redirect_uri após o login.
    Troca o code por um short-lived token e depois por um long-lived token (~60 dias).
    """
    try:
        short_token = code_to_short_lived_token(code, is_instagram_only=is_instagram_only)
        if not short_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falha ao trocar o code pelo token. O code pode ter expirado."
            )

        long_token = short_to_long_lived_token(short_token, is_instagram_only=is_instagram_only)
        if not long_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falha ao obter token de longa duração."
            )

        logger.info("Autenticação concluída com sucesso.")
        return CallbackResponse(access_token=long_token)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no callback de autenticação: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno na autenticação")


### >> Validar token << ###

@router.get("/validate", response_model=TokenValidationResponse, summary="Valida se o token de acesso ainda é válido")
async def validate(
    token: str = Query(..., description="Token de acesso do usuário a ser validado")
):
    """
    Usa o endpoint /debug_token da Meta para verificar se o token ainda é válido.
    Retorna is_valid, quando expira e quais permissões o token tem.
    """
    try:
        result = validate_token(token)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Não foi possível verificar o token com a Meta."
            )

        return TokenValidationResponse(
            is_valid=result["is_valid"],
            expires_at=result["expires_at"] or 0,
            scopes=result["scopes"],
            user_id=result.get("user_id"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao validar token: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao validar token")


### >> Renovar token do Instagram << ###

@router.get("/refresh", response_model=CallbackResponse, summary="Renova o token de longa duração do Instagram")
async def refresh(
    token: str = Query(..., description="Token de longa duração do Instagram a ser renovado")
):
    """
    Renova um token de longa duração do Instagram antes de expirar (~60 dias).
    Retorna um novo token com mais 60 dias de validade.
    """
    try:
        new_token = refresh_ig_token(token)
        if not new_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falha ao renovar o token. Ele pode já ter expirado — faça login novamente."
            )

        logger.info("Token IG renovado com sucesso.")
        return CallbackResponse(access_token=new_token)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao renovar token: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao renovar token")