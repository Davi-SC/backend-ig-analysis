"""
Schemas Pydantic para validação de webhooks do IG. 
Baseado na documentação https://developers.facebook.com/docs/instagram-platform/webhooks
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class WebhookVerificationRequest(BaseModel):
    hub_mode: str = Field(...,description="Sempre sera 'subscribe'")
    hub_challenge: str = Field(...,description="Valor a ser retornado para verificacao")
    hub_verify_token: str = Field(...,description="Token de verificacao configurado no app")

class WebhookChange(BaseModel):
    field: str = Field(...,description="Campo alterado(comments, mentions, media, etc)")
    value: Dict[str, Any] = Field(...,description="Valor do campo alterado")

    class Config:
        # exemplo de estrutura de value para diferentes tipos de eventos:
        json_schema_extra = {
            "example": {
                "field": "comments",
                "value": {
                    "verb":"add",
                    "object_id": "17895695668004550",
                    "comment_id":"17895695668004551",
                    "text": "Great post!"
                }
            }
        }

class WebhookEntry(BaseModel):
    id: str = Field(..., description="ID da conta do Instagram")
    time: int = Field(..., description="Timestamp Unix quando a notificação foi enviada")
    changes: List[WebhookChange] = Field(default_factory=list, description="Lista de mudanças")
    
    # Campos opcionais que podem aparecer em alguns eventos
    uid: Optional[str] = Field(None, description="User ID (opcional)")
    changed_fields: Optional[List[str]] = Field(None, description="Campos alterados (se Include Values estiver desabilitado)")

class WebhookPayload(BaseModel):
    object: str = Field(..., description="Objeto que disparou o webhook (ex: 'instagram', sempre esse para Instagram)")
    entry: List[WebhookEntry] = Field(..., description="Lista de entradas do webhook")

    class Config:
        json_schema_extra = {
            "example": {
                "object": "instagram",
                "entry": [
                    {
                        "id": "instagram-account-id",
                        "time": 1520383571,
                        "changes": [
                            {
                                "field": "comments",
                                "value": {
                                    "verb": "add",
                                    "object_id": "post-id",
                                    "comment_id": "comment-id",
                                    "text": "Nice photo!"
                                }
                            }
                        ]
                    }
                ]
            }
        }
        