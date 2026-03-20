"""
Model Pydantic para a collection 'posts'.

Representa os metadados ESTÁTICOS de um post do Instagram.
   Regra fundamental: write-once. Um post é inserido na descoberta e NUNCA sobrescrito.
   Contadores (likes, comments) NÃO vivem aqui — vivem em PostSnapshot.

Por que separar Post de PostSnapshot?
    Post  -> quem é o post (tipo de mídia, legenda, quando foi publicado)
    PostSnapshot -> como o post estava performando em determinado dia
    Essa separação permite analisar a evolução do desempenho de um mesmo post ao longo do tempo.
"""

from typing import List, Optional, Literal
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Post(BaseModel):
    """
    Metadados imutáveis de um post do Instagram.

    Campos:
        post_id      : ID numérico do post na API do Instagram. Chave primária.
        profile_id   : ID do perfil dono do post (FK para 'accounts').
        media_type   : Tipo de mídia conforme a API ("IMAGE" | "VIDEO" | "CAROUSEL_ALBUM").
        caption      : Legenda do post. Capturada na descoberta, não atualizada depois.
        hashtags     : Extraídas do caption no momento da descoberta via regex.
                       São pré-processadas para não precisar parsear toda vez nos pipelines de ML.
        permalink    : URL permanente do post no Instagram.
        published_at : Quando o post foi publicado no Instagram (timestamp da API).
        discovered_at: Quando nosso sistema descobriu esse post pela primeira vez.
    """

    post_id: str = Field(
        ...,
        description="ID numérico do post na API. Chave primária única.",
    )
    profile_id: str = Field(
        ...,
        description="ID do perfil dono do post. Referência para 'accounts'.",
    )
    media_type: Literal["IMAGE", "VIDEO", "CAROUSEL_ALBUM"] = Field(
        ...,
        description="Tipo de mídia conforme retornado pela API do Instagram.",
    )
    caption: Optional[str] = Field(
        default=None,
        description="Legenda do post. Pode ser None se o post não tiver legenda.",
    )
    hashtags: List[str] = Field(
        default_factory=list,
        description=(
            "Hashtags extraídas do caption por regex no momento da descoberta. "
            "Ex: ['#tech', '#ifma']. Pré-processado para agilizar pipelines de ML."
        ),
    )
    permalink: str = Field(
        ...,
        description="URL permanente do post no Instagram.",
    )
    published_at: datetime = Field(
        ...,
        description="Quando o post foi publicado no Instagram (timestamp da API).",
    )
    discovered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Quando nosso pipeline descobriu esse post pela primeira vez.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "post_id": "18406296661186436",
                "profile_id": "17841477255589822",
                "media_type": "IMAGE",
                "caption": "Evento extraordinário no IFMA! #ifma #tech",
                "hashtags": ["#ifma", "#tech"],
                "permalink": "https://www.instagram.com/p/ABC123/",
                "published_at": "2025-11-17T18:45:30Z",
                "discovered_at": "2026-01-10T03:00:00Z",
            }
        }
    }
