"""
Schemas Pydantic para as rotas OAuth da Meta (Instagram e Facebook).
"""

from typing import Optional, List
from pydantic import BaseModel, Field

class OAuthUrlResponse(BaseModel):
    """Resposta das rotas /oauth/ig/url e /oauth/fb/url — retorna a URL de autorização."""
    url: str


class OAuthCallbackResponse(BaseModel):
    """Resposta da rota /oauth/callback — retorna o token de acesso de longa duração."""
    access_token: str
    user_id: Optional[str] = None  # Presente no fluxo Instagram (retornado pela API)


class OAuthTokenValidationResponse(BaseModel):
    """Resposta da rota /oauth/validate — retorna informações sobre a validade do token."""
    is_valid: bool
    expires_at: int
    scopes: List[str]
    user_id: Optional[str] = None


class FbSaveRequest(BaseModel):
    """Body da rota POST /oauth/fb/save — token recebido pelo frontend via implicit flow do Facebook."""
    access_token: str = Field(..., description="Token de acesso retornado pelo Facebook ao frontend")
    user_id: str = Field(..., description="ID do usuário retornado pelo Facebook ao frontend")


class FbSaveResponse(BaseModel):
    """Resposta da rota POST /oauth/fb/save."""
    profile_id: str
    username: str
