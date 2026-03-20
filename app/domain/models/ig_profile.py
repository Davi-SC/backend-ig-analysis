"""
Model Pydantic para a collection 'ig_profiles'.

Representa um perfil Instagram conectado ao sistema via OAuth.

Ciclo de vida:
  1. OAuth login     -> upsert com: profile_id, username, auth_method, is_active
  2. profile_service -> upsert com: biography, website, ig_account_type
  3. DAGs diários    -> leitura de profile_id e auth_method para coleta
"""

from typing import Optional, Literal
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class IgProfile(BaseModel):
    """
    Perfil Instagram conectado ao sistema.

    Campos obrigatórios no OAuth:
        profile_id, username, auth_method

    Campos opcionais preenchidos pelo profile_service DAG:
        biography, website, ig_account_type

    Campos de controle interno:
        is_active  -> se False, DAGs ignoram esse perfil
        created_at -> data de inserção (imutável, via $setOnInsert)
        updated_at -> atualizado em cada upsert
    """

    profile_id: str = Field(
        ...,
        description=(
            "ID numérico do perfil no Instagram Graph API. Imutável e único. "
            "Chave primária da collection."
        ),
    )
    username: str = Field(
        ...,
        description="Username (@ handle) do perfil. Atualizado a cada upsert pois pode mudar.",
    )
    auth_method: Literal["facebook", "instagram"] = Field(
        ...,
        description="Método de autenticação usado no login OAuth.",
    )
    biography: Optional[str] = Field(
        default=None,
        description="Biografia do perfil. Preenchida pelo profile_service DAG.",
    )
    website: Optional[str] = Field(
        default=None,
        description="URL do site externo. Preenchida pelo profile_service DAG.",
    )
    ig_account_type: Optional[Literal["BUSINESS", "MEDIA_CREATOR", "PERSONAL"]] = Field(
        default=None,
        description=(
            "Tipo de conta Instagram ('BUSINESS', 'MEDIA_CREATOR', 'PERSONAL'). "
        ),
    )
    is_active: bool = Field(
        default=True,
        description="Se False, esse perfil é ignorado por todos os DAGs de coleta.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp de criação (primeiro login OAuth). Imutável via $setOnInsert.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp da última atualização (OAuth re-login ou profile_service).",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "profile_id": "12345678912345678",
                "username": "user.oficial",
                "auth_method": "facebook",
                "biography": "User bio",
                "website": "https://user.com",
                "ig_account_type": "BUSINESS",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-03-17T00:00:00Z",
            }
        }
    }
