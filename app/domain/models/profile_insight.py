"""
Model Pydantic para a collection 'profile_insights'.

Armazena métricas agregadas do perfil, coletadas
semanalmente pela API de insights do Instagram.

Diferença para profile_snapshots:
    profile_snapshots -> métricas simples e diárias (followers_count, etc.)
    profile_insights  -> métricas complexas e semanais: reach, dados demográficos,
                        distribuição geográfica. Requerem permissão especial.

Os dicionários de audiência usam contagens absolutas do período.
Ex: audience_country = {"BR": 412, "US": 38} -> 412 seguidores do Brasil no período.
"""

from typing import Dict, Optional
from datetime import date as DateType, datetime, timezone

from pydantic import BaseModel, Field


class ProfileInsight(BaseModel):
    """
    Métricas agregadas semanais de um perfil Instagram.
    """

    profile_id: str = Field(
        ...,
        description="ID do perfil. Referência para 'ig_profiles'.",
    )
    period_since: DateType = Field(
        ...,
        description="Data de início do período de 7 dias dessa coleta.",
    )
    period_until: DateType = Field(
        ...,
        description="Data de fim do período de 7 dias dessa coleta.",
    )
    reach: Optional[int] = Field(default=None, ge=0, description="Contas únicas alcançadas no período.")
    profile_views: Optional[int] = Field(default=None, ge=0, description="Visitas ao perfil no período.")
    total_interactions: Optional[int] = Field(default=None, ge=0, description="Total de interações no período.")
    follows_and_unfollows: Optional[int] = Field(
        default=None,
        description="Saldo de novos seguidores no período. Pode ser negativo.",
    )
    audience_country: Optional[Dict[str, int]] = Field(
        default=None,
        description="Contagem de seguidores por país (código ISO 2 letras).",
    )
    audience_city: Optional[Dict[str, int]] = Field(
        default=None,
        description="Contagem de seguidores por cidade.",
    )
    audience_age: Optional[Dict[str, int]] = Field(
        default=None,
        description="Contagem de seguidores por faixa etária (ex: '18-24').",
    )
    audience_gender: Optional[Dict[str, int]] = Field(
        default=None,
        description="Contagem de seguidores por gênero ('M', 'F', 'U').",
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp da coleta pelo insights_service.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "profile_id": "17841477255589822",
                "period_since": "2026-03-10",
                "period_until": "2026-03-17",
                "reach": 8420,
                "profile_views": 310,
                "total_interactions": 940,
                "follows_and_unfollows": 27,
                "audience_country": {"BR": 412, "US": 38, "PT": 21},
                "audience_city": {"São Luís": 180, "Coelho Neto": 95},
                "audience_age": {"18-24": 230, "25-34": 140},
                "audience_gender": {"M": 280, "F": 210},
                "collected_at": "2026-03-17T03:00:00Z",
            }
        }
    }
