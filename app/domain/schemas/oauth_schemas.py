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


class OAuthTokenValidationResponse(BaseModel):
    """Resposta da rota /oauth/validate — retorna informações sobre a validade do token."""
    is_valid: bool
    expires_at: int
    scopes: List[str]
    user_id: Optional[str] = None
