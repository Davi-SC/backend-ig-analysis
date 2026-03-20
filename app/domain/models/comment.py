"""
Models Pydantic para a collection 'comments'.

Cada documento representa um comentário em um post.
Replies são EMBUTIDAS como array dentro do documento do comentário.

Por que embeds e não collection separada?
    A relação comentário → replies é 1:N pequena (raramente mais de 10 por comentário).
    Embutir evita JOINs e torna a leitura de um comentário com suas respostas
    uma operação de documento único — muito mais eficiente no MongoDB.

Regra de imutabilidade:
    Após inserção, o conteúdo do comentário NÃO é atualizado mesmo que o usuário
    edite no Instagram — a API não expõe histórico de edições. O campo 'text'
    representa o conteúdo no momento da coleta.
    Exceção: campos sentiment_* são preenchidos DEPOIS pelo sentiment_service.
"""

from typing import List, Optional
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Reply(BaseModel):
    """
    Representa uma resposta a um comentário (reply embutida).
    """

    reply_id: str = Field(
        ...,
        description="ID da reply na API do Instagram.",
    )
    username: str = Field(
        ...,
        description="Username do autor da reply.",
    )
    text: str = Field(
        ...,
        description="Conteúdo da reply no momento da coleta.",
    )
    published_at: datetime = Field(
        ...,
        description="Quando a reply foi publicada no Instagram.",
    )


class Comment(BaseModel):
    """
    Representa um comentário em um post Instagram.
    """

    comment_id: str = Field(
        ...,
        description="ID do comentário na API do Instagram. Chave primária.",
    )
    post_id: str = Field(
        ...,
        description="ID do post ao qual pertence. Referência para 'posts'.",
    )
    profile_id: str = Field(
        ...,
        description="ID do perfil dono do post. Denormalizado para queries por perfil.",
    )
    username: str = Field(
        ...,
        description="Username do autor do comentário.",
    )
    text: str = Field(
        ...,
        description="Conteúdo do comentário no momento da coleta. Imutável após inserção.",
    )
    like_count: int = Field(
        default=0,
        ge=0,
        description="Likes no comentário. 0 se a API não retornar esse campo.",
    )
    published_at: datetime = Field(
        ...,
        description="Quando o comentário foi publicado no Instagram.",
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Quando o comments_service coletou esse comentário.",
    )
    replies: List[Reply] = Field(
        default_factory=list,
        description="Replies embutidas. Vazio se o comentário não tiver respostas.",
    )
    # Campos preenchidos pelo sentiment_service (fase Transform)
    sentiment_score: Optional[float] = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="Score de sentimento entre -1 (negativo) e 1 (positivo).",
    )
    sentiment_label: Optional[str] = Field(
        default=None,
        description="Rótulo: 'positive', 'negative' ou 'neutral'.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "comment_id": "17858893269000001",
                "post_id": "18406296661186436",
                "profile_id": "17841477255589822",
                "username": "usuario_exemplo",
                "text": "Muito bom esse conteúdo!",
                "like_count": 3,
                "published_at": "2025-11-17T20:10:00Z",
                "collected_at": "2026-01-10T03:00:00Z",
                "replies": [
                    {
                        "reply_id": "17858893269000099",
                        "username": "outro_usuario",
                        "text": "Concordo!",
                        "published_at": "2025-11-17T20:45:00Z",
                    }
                ],
                "sentiment_score": None,
                "sentiment_label": None,
            }
        }
    }
