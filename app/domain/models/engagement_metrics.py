"""
Model Pydantic para a collection 'engagement_metrics'.

Esta collection NÃO vem da API do Instagram.
É 100% calculada pelo engagement_service a partir dos dados já coletados
(post_snapshots, account_snapshots). É o produto da fase TRANSFORM do ETL.

É a collection que alimenta diretamente o pipeline de ML do TCC.

Índice composto único no MongoDB: { post_id: 1, date: 1 }
"""

from typing import Optional
from datetime import date as DateType, datetime, timezone

from pydantic import BaseModel, Field


class EngagementMetrics(BaseModel):
    """
    Métricas calculadas de engajamento de um post em um dia específico.
    """

    post_id: str = Field(
        ...,
        description="ID do post. Referência para 'posts'.",
    )
    profile_id: str = Field(
        ...,
        description="ID do perfil. Denormalizado para queries por perfil.",
    )
    date: DateType = Field(
        ...,
        description="Data do cálculo. Com post_id forma a chave única.",
    )
    er_simple: Optional[float] = Field(
        default=None,
        ge=0,
        description="ER simples: (likes + comments) / followers. Decimal (ex: 0.051 = 5,1%).",
    )
    er_weighted: Optional[float] = Field(
        default=None,
        ge=0,
        description="ER ponderado Arman & Sidik (2019): (likes×1 + comments×2) / followers.",
    )
    er_reach: Optional[float] = Field(
        default=None,
        ge=0,
        description="ER por alcance: total_interactions / reach. Mais preciso para comparações entre perfis.",
    )
    velocity_likes_24h: Optional[int] = Field(
        default=None,
        description="Delta de likes nas últimas 24h (hoje - ontem).",
    )
    velocity_comments_24h: Optional[int] = Field(
        default=None,
        description="Delta de comentários nas últimas 24h (hoje - ontem).",
    )
    loyalty_rate: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Taxa de fidelidade: interações únicas / total de seguidores. Entre 0 e 1.",
    )
    days_since_published: Optional[int] = Field(
        default=None,
        ge=0,
        description="Dias passados desde a publicação do post até essa data.",
    )
    calculated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp de quando o engagement_service calculou esses valores.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "post_id": "18406296661186436",
                "profile_id": "17841477255589822",
                "date": "2026-03-17",
                "er_simple": 0.051,
                "er_weighted": 0.078,
                "er_reach": 0.251,
                "velocity_likes_24h": 12,
                "velocity_comments_24h": 2,
                "loyalty_rate": 0.034,
                "days_since_published": 120,
                "calculated_at": "2026-03-17T04:00:00Z",
            }
        }
    }
