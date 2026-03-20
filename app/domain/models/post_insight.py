"""
Model Pydantic para a collection 'post_insights'.

Separado de post_snapshots porque tem semântica DIFERENTE:
  - post_snapshots → contadores PONTUAIS (como estava naquele dia)
  - post_insights  → métricas ACUMULADAS LIFETIME retornadas pela API de insights

A API de insights retorna valores acumulados desde a publicação do post —
não são deltas diários. Ex: reach de 1520 = 1520 pessoas únicas alcançadas
desde a publicação, não apenas hoje.

Documentos são APPEND-ONLY: cada coleta gera um novo documento com seu próprio
collected_at. Assim é possível ver como o acumulado evolui ao longo do tempo.
"""

from typing import Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class PostInsight(BaseModel):
    """
    Métricas acumuladas (lifetime) de um post, coletadas via API de Insights.

    ig_reels_avg_watch_time: disponível só para Reels. None para IMAGE e CAROUSEL_ALBUM.
    """

    post_id: str = Field(
        ...,
        description="ID do post. Referência para a collection 'posts'.",
    )
    profile_id: str = Field(
        ...,
        description="ID do perfil dono do post.",
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp da coleta. É a 'data' dessa série temporal acumulada.",
    )
    reach: Optional[int] = Field(default=None, ge=0, description="Contas únicas que viram o post (acumulado).")
    saved: Optional[int] = Field(default=None, ge=0, description="Vezes que o post foi salvo (acumulado).")
    shares: Optional[int] = Field(default=None, ge=0, description="Vezes que o post foi compartilhado (acumulado).")
    total_interactions: Optional[int] = Field(default=None, ge=0, description="Soma de todas as interações (acumulado).")
    views: Optional[int] = Field(default=None, ge=0, description="Total de visualizações, incluindo repetições (acumulado).")
    ig_reels_avg_watch_time: Optional[float] = Field(
        default=None,
        ge=0,
        description="Tempo médio de assistir ao Reel em milissegundos. Só disponível para Reels.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "post_id": "18406296661186436",
                "profile_id": "17841477255589822",
                "collected_at": "2026-03-17T03:00:00Z",
                "reach": 1520,
                "saved": 89,
                "shares": 12,
                "total_interactions": 382,
                "views": 3100,
                "ig_reels_avg_watch_time": None,
            }
        }
    }
