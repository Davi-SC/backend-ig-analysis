"""
Model Pydantic para a collection 'profile_snapshots'.

Fotografia diária do estado de um perfil Instagram (followers, following, media_count).
O conjunto de snapshots forma a série temporal de crescimento de audiência.

Índice composto único: { profile_id: 1, date: 1 }
Um snapshot por perfil por dia.
"""

from datetime import date as DateType, datetime, timezone

from pydantic import BaseModel, Field


class ProfileSnapshot(BaseModel):
    """
    Fotografia diária de métricas de crescimento de um perfil Instagram.

    Por que separar de IgProfile?
        IgProfile guarda o que é estrutural (bio, tipo de conta) - muda raramente.
        ProfileSnapshot guarda o que oscila: followers_count, following_count, media_count.
        Permite analisar curvas de crescimento sem poluir o documento principal.
    """

    profile_id: str = Field(
        ...,
        description="ID do perfil. Referência para 'ig_profiles'.",
    )
    date: DateType = Field(
        ...,
        description="Data do snapshot (YYYY-MM-DD). Com profile_id forma a chave única.",
    )
    followers_count: int = Field(
        ...,
        ge=0,
        description="Número de seguidores na data do snapshot.",
    )
    follows_count: int = Field(
        ...,
        ge=0,
        description="Número de contas que o perfil segue na data do snapshot.",
    )
    media_count: int = Field(
        ...,
        ge=0,
        description="Total de posts publicados até a data do snapshot.",
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp exato da coleta pelo snapshot_service.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "profile_id": "17841477255589822",
                "date": "2026-03-17",
                "followers_count": 4821,
                "follows_count": 312,
                "media_count": 198,
                "collected_at": "2026-03-17T03:00:00Z",
            }
        }
    }
