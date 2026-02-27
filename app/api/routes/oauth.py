"""
Rotas OAuth da Meta (Instagram e Facebook).
O frontend NÃO tem lógica de OAuth — apenas consome estas rotas.
"""

from fastapi import APIRouter, HTTPException, Query, status
import logging

from app.services.oauth_service import (
    generate_fb_oauth_url,
    generate_ig_oauth_url,
    oauth_code_to_short_lived_token,
    oauth_short_to_long_lived_token,
    refresh_ig_oauth_token,
    validate_oauth_token,
)
from app.domain.schemas.oauth_schemas import OAuthUrlResponse, OAuthCallbackResponse, OAuthTokenValidationResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])

### >> Gerar URLs de autorização OAuth << ###

@router.get("/fb/url", response_model=OAuthUrlResponse, summary="Gera URL de autorização OAuth do Facebook")
async def get_fb_oauth_url():
    """Retorna a URL para o usuário autorizar o app no Facebook."""
    try:
        url = generate_fb_oauth_url()
        return OAuthUrlResponse(url=url)
    except Exception as e:
        logger.error(f"Erro ao gerar URL OAuth FB: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao gerar URL de autorização OAuth")

@router.get("/ig/url", response_model=OAuthUrlResponse, summary="Gera URL de autorização OAuth do Instagram")
async def get_ig_oauth_url():
    """Retorna a URL para o usuário autorizar o app no Instagram (Business Login)."""
    try:
        url = generate_ig_oauth_url()
        return OAuthUrlResponse(url=url)
    except Exception as e:
        logger.error(f"Erro ao gerar URL OAuth IG: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao gerar URL de autorização OAuth")

### >> Callback — trocar code por token << ###

@router.get("/callback", response_model=OAuthCallbackResponse, summary="Troca o code OAuth por token de acesso")
async def oauth_callback(
    code: str = Query(..., description="Código retornado pelo Instagram/Facebook após o login"),
    is_instagram_only: bool = Query(False, description="True para fluxo Instagram Business, False para fluxo Facebook")
):
    """
    Recebe o `code` que o Instagram/Facebook envia ao redirect_uri após o login.
    Troca o code por um short-lived token e depois por um long-lived token (~60 dias).
    """
    try:
        short_token = oauth_code_to_short_lived_token(code, is_instagram_only=is_instagram_only)
        if not short_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falha ao trocar o code pelo token. O code pode ter expirado."
            )

        long_token = oauth_short_to_long_lived_token(short_token, is_instagram_only=is_instagram_only)
        if not long_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falha ao obter token de longa duração."
            )

        logger.info("OAuth concluído com sucesso.")
        return OAuthCallbackResponse(access_token=long_token)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no OAuth callback: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno no OAuth callback")


### >> Validar OAuth token << ###

@router.get("/validate", response_model=OAuthTokenValidationResponse, summary="Valida se o token OAuth ainda é válido")
async def oauth_validate(
    token: str = Query(..., description="Token de acesso OAuth a ser validado")
):
    """
    Usa o endpoint /debug_token da Meta para verificar se o token OAuth ainda é válido.
    Retorna is_valid, quando expira e quais permissões o token tem.
    """
    try:
        result = validate_oauth_token(token)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Não foi possível verificar o token com a Meta."
            )

        return OAuthTokenValidationResponse(
            is_valid=result["is_valid"],
            expires_at=result["expires_at"] or 0,
            scopes=result["scopes"],
            user_id=result.get("user_id"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao validar OAuth token: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao validar token OAuth")


### >> Renovar OAuth token do Instagram << ###

@router.get("/refresh", response_model=OAuthCallbackResponse, summary="Renova o token OAuth de longa duração do Instagram")
async def oauth_refresh(
    token: str = Query(..., description="Token de longa duração do Instagram a ser renovado")
):
    """
    Renova um token OAuth de longa duração do Instagram antes de expirar (~60 dias).
    Retorna um novo token com mais 60 dias de validade.
    """
    try:
        new_token = refresh_ig_oauth_token(token)
        if not new_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Falha ao renovar o token OAuth. Ele pode já ter expirado — faça login novamente."
            )

        logger.info("OAuth Token IG renovado com sucesso.")
        return OAuthCallbackResponse(access_token=new_token)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao renovar OAuth token: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao renovar token OAuth")
