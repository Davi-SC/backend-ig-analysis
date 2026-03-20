"""
Model Pydantic para a collection 'post_snapshots'.

É o coração da análise temporal. Um documento por post por dia.
Enquanto 'posts' guarda o que o post é, 'post_snapshots' guarda como ele performava
em cada dia específico.

Índice composto único no MongoDB: { post_id: 1, date: 1 }

Nota sobre followers_at_date (desnormalização):
    followers_at_date é duplicado aqui propositalmente — ele também existe em
    account_snapshots. A razão: no pipeline de ML, calcular ER normalizado por
    audiência exigiria um JOIN a cada query. Ao desnormalizar, o engagement_service
    pode calcular o ER diretamente lendo apenas esta collection.
"""

from typing import Optional
from datetime import date as DateType, datetime, timezone

from pydantic import BaseModel, Field


class PostSnapshot(BaseModel):
    """
    Foto do desempenho de um post em um dia específico.

    Contadores (like_count, comments_count, etc.) vêm diretamente
    dos campos do objeto de mídia ou das chamadas de insights da API.
    """

    post_id: str = Field(
        ...,
        description="ID do post. Referência para a collection 'posts'.",
    )
    profile_id: str = Field(
        ...,
        description="ID do perfil dono do post. Denormalizado para facilitar queries por perfil.",
    )
    date: DateType = Field(
        ...,
        description="Data do snapshot (YYYY-MM-DD). Com post_id forma a chave única.",
    )
    like_count: int = Field(..., ge=0, description="Número de likes no momento da coleta.")
    comments_count: int = Field(..., ge=0, description="Número de comentários no momento da coleta.")
    shares: Optional[int] = Field(default=None, ge=0, description="Número de compartilhamentos.")
    saved: Optional[int] = Field(default=None, ge=0, description="Número de salvamentos.")
    reach: Optional[int] = Field(default=None, ge=0, description="Alcance único do post nesse dia.")
    total_interactions: Optional[int] = Field(default=None, ge=0, description="Soma de todas as interações.")
    followers_at_date: Optional[int] = Field(
        default=None,
        ge=0,
        description=(
            "Seguidores do perfil nesse dia, copiado de account_snapshots. "
            "Desnormalizado para calcular ER sem JOIN no pipeline de ML."
        ),
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp exato da coleta pelo snapshot_service.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "post_id": "18406296661186436",
                "profile_id": "17841477255589822",
                "date": "2026-03-17",
                "like_count": 247,
                "comments_count": 34,
                "shares": 12,
                "saved": 89,
                "reach": 1520,
                "total_interactions": 382,
                "followers_at_date": 4821,
                "collected_at": "2026-03-17T03:00:00Z",
            }
        }
    }
