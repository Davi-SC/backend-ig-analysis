"""
Endpoints de dados brutos — /data

Expõe os dados coletados e processados pelo ETL para consumo do frontend.
Nenhuma lógica de negócio aqui — apenas leitura do MongoDB.

Endpoints:
  GET /data/profile            → dados estáticos do perfil (ig_profiles)
  GET /data/snapshots          → série temporal de followers/media_count
  GET /data/posts              → lista de posts com último snapshot
  GET /data/engagement/{post_id} → histórico de engagement_metrics de um post
  GET /data/insights/account   → profile_insights (semanal)
  GET /data/comments/{post_id} → comentários de um post

Auth: header obrigatório X-Profile-ID.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from bson import ObjectId

from app.utils.auth import get_authenticated_profile
from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])


def _clean(doc: dict) -> dict:
    """Remove _id do MongoDB para serialização JSON segura."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _clean_list(docs: list) -> list:
    return [_clean(d) for d in docs]


@router.get(
    "/profile",
    summary="Dados do perfil",
    description="Retorna os dados estáticos do perfil Instagram autenticado.",
)
async def get_profile(profile_id: str = Depends(get_authenticated_profile)):
    doc = mongo_repo.ig_profiles.find_one({"profile_id": profile_id})
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil não encontrado. Execute /collect/initial primeiro.",
        )
    return _clean(doc)


@router.get(
    "/snapshots",
    summary="Série temporal do perfil",
    description=(
        "Retorna a série temporal de snapshots diários do perfil: "
        "followers_count, follows_count, media_count. "
        "Parâmetro `days` limita o período (padrão: 30 dias)."
    ),
)
async def get_snapshots(
    days: int = Query(default=30, ge=1, le=365, description="Número de dias de histórico"),
    profile_id: str = Depends(get_authenticated_profile),
):
    from datetime import datetime, timezone, timedelta
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    docs = list(
        mongo_repo.profile_snapshots.find(
            {"profile_id": profile_id, "date": {"$gte": since}},
            sort=[("date", 1)],
        )
    )
    return {"profile_id": profile_id, "days": days, "count": len(docs), "data": _clean_list(docs)}


@router.get(
    "/posts",
    summary="Lista de posts",
    description=(
        "Retorna os posts do perfil com os dados do último snapshot (likes, comments). "
        "Parâmetro `limit` controla quantos posts retornar (padrão: 20, máx: 100)."
    ),
)
async def get_posts(
    limit: int = Query(default=20, ge=1, le=100, description="Número máximo de posts"),
    profile_id: str = Depends(get_authenticated_profile),
):
    posts = list(
        mongo_repo.posts.find(
            {"profile_id": profile_id},
            sort=[("published_at", -1)],
            limit=limit,
        )
    )

    # Enriquece cada post com o snapshot mais recente
    enriched = []
    for post in posts:
        post_id = post["post_id"]
        snap = mongo_repo.post_snapshots.find_one(
            {"post_id": post_id},
            sort=[("date", -1)],
        )
        post_clean = _clean(post)
        post_clean["latest_snapshot"] = _clean(snap) if snap else None
        enriched.append(post_clean)

    return {"profile_id": profile_id, "count": len(enriched), "data": enriched}


@router.get(
    "/engagement/{post_id}",
    summary="Histórico de engajamento de um post",
    description=(
        "Retorna o histórico completo de engagement_metrics de um post específico, "
        "ordenado por data. Inclui er_simple, er_reach, amplification_rate, etc."
    ),
)
async def get_engagement(
    post_id: str,
    profile_id: str = Depends(get_authenticated_profile),
):
    # Valida que o post pertence ao perfil autenticado
    post = mongo_repo.posts.find_one({"post_id": post_id, "profile_id": profile_id})
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post não encontrado ou não pertence ao perfil autenticado.",
        )

    metrics = list(
        mongo_repo.engagement_metrics.find(
            {"post_id": post_id},
            sort=[("date", 1)],
        )
    )

    return {"post_id": post_id, "profile_id": profile_id, "count": len(metrics), "data": _clean_list(metrics)}


@router.get(
    "/insights/account",
    summary="Insights semanais da conta",
    description=(
        "Retorna os registros de profile_insights coletados semanalmente: "
        "reach, accounts_engaged, total_interactions, views e dados demográficos."
    ),
)
async def get_account_insights(
    limit: int = Query(default=12, ge=1, le=52, description="Número de semanas de histórico"),
    profile_id: str = Depends(get_authenticated_profile),
):
    docs = list(
        mongo_repo.profile_insights.find(
            {"profile_id": profile_id},
            sort=[("period_until", -1)],
            limit=limit,
        )
    )
    return {"profile_id": profile_id, "count": len(docs), "data": _clean_list(docs)}


@router.get(
    "/comments/{post_id}",
    summary="Comentários de um post",
    description="Retorna os comentários de um post específico, incluindo replies embutidas.",
)
async def get_comments(
    post_id: str,
    limit: int = Query(default=50, ge=1, le=200, description="Número máximo de comentários"),
    profile_id: str = Depends(get_authenticated_profile),
):
    # Valida que o post pertence ao perfil autenticado
    post = mongo_repo.posts.find_one({"post_id": post_id, "profile_id": profile_id})
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Post não encontrado ou não pertence ao perfil autenticado.",
        )

    comments = list(
        mongo_repo.comments.find(
            {"post_id": post_id},
            sort=[("timestamp", -1)],
            limit=limit,
        )
    )

    return {"post_id": post_id, "count": len(comments), "data": _clean_list(comments)}
