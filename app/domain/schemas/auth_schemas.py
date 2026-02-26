from typing import Optional, List
from pydantic import BaseModel, Field

class AuthUrlResponse(BaseModel):
    """
    Classe Pydantic para URL de autenticação(auth/ig/url e auth/fb/url)
    """
    url: str

class CallbackResponse(BaseModel):
    """Classe pydantic para a resposta do callback(auth/callback)"""
    access_token: str

class TokenValidationResponse(BaseModel):
    """
    Classe Pydantic para a resposta de validação de token(auth/validate)
    """
    is_valid: bool
    expires_at: int
    scopes: List[str]
    user_id: Optional[str]