"""
Endpoints analíticos — /analytics

Fornece análises pré-computadas sobre os dados coletados.
Toda a lógica de agregação fica aqui (aggregation pipelines MongoDB),
o frontend apenas exibe os resultados.

Endpoints:
  GET /analytics/top-posts          → ranking de posts por métrica
  GET /analytics/best-hours         → melhores horários para publicar
  GET /analytics/by-format          → engajamento médio por tipo de mídia
  GET /analytics/engagement-trend   → tendência de engajamento ao longo do tempo

Auth: header obrigatório X-Profile-ID.
"""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.utils.auth import get_authenticated_profile
from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Métricas disponíveis para ranking
VALID_METRICS = {"er_simple", "er_reach", "er_followers", "er_views", "amplification_rate", "relative_reach"}


def _clean(doc: dict) -> dict:
    """Remove _id do MongoDB para serialização JSON segura."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.get(
    "/top-posts",
    summary="Ranking de posts por métrica",
    description=(
        "Retorna os posts com maior valor para a métrica especificada. "
        "Métricas disponíveis: er_simple, er_reach, er_followers, er_views, "
        "amplification_rate, relative_reach. "
        "Usa o registro de engagement_metrics mais recente de cada post."
    ),
)
async def top_posts(
    metric: str = Query(default="er_simple", description="Métrica para ranquear os posts"),
    limit: int = Query(default=10, ge=1, le=50, description="Número de posts no ranking"),
    profile_id: str = Depends(get_authenticated_profile),
):
    if metric not in VALID_METRICS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Métrica '{metric}' inválida. Disponíveis: {sorted(VALID_METRICS)}",
        )

    # Aggregation: último engagement_metrics por post → ordena pela métrica
    pipeline = [
        {"$match": {"profile_id": profile_id, metric: {"$exists": True, "$gt": 0}}},
        {"$sort": {"post_id": 1, "date": -1}},
        {"$group": {
            "_id": "$post_id",
            "post_id": {"$first": "$post_id"},
            "date": {"$first": "$date"},
            "er_simple": {"$first": "$er_simple"},
            "er_reach": {"$first": "$er_reach"},
            "er_followers": {"$first": "$er_followers"},
            "er_views": {"$first": "$er_views"},
            "amplification_rate": {"$first": "$amplification_rate"},
            "relative_reach": {"$first": "$relative_reach"},
            "days_since_published": {"$first": "$days_since_published"},
        }},
        {"$sort": {metric: -1}},
        {"$limit": limit},
    ]

    results = list(mongo_repo.engagement_metrics.aggregate(pipeline))

    # Enriquece com metadados do post (caption, media_type, permalink)
    enriched = []
    for r in results:
        post_id = r.get("post_id") or r.get("_id")
        post = mongo_repo.posts.find_one(
            {"post_id": post_id},
            {"_id": 0, "caption": 1, "media_type": 1, "permalink": 1, "published_at": 1, "thumbnail_url": 1},
        )
        r["_id"] = str(r["_id"]) if "_id" in r else None
        r["post_meta"] = post or {}
        enriched.append(r)

    return {
        "profile_id": profile_id,
        "metric": metric,
        "limit": limit,
        "count": len(enriched),
        "data": enriched,
    }


@router.get(
    "/best-hours",
    summary="Melhores horários para publicar",
    description=(
        "Agrupa os posts pelo horário de publicação (hora do dia, 0–23) e calcula "
        "o er_simple médio de cada faixa horária. Útil para identificar o melhor "
        "momento do dia para publicar no perfil."
    ),
)
async def best_hours(profile_id: str = Depends(get_authenticated_profile)):
    # Busca todos os posts do perfil com published_at
    posts = list(
        mongo_repo.posts.find(
            {"profile_id": profile_id, "published_at": {"$exists": True}},
            {"_id": 0, "post_id": 1, "published_at": 1},
        )
    )

    if not posts:
        return {"profile_id": profile_id, "message": "Nenhum post encontrado.", "data": []}

    # Monta lookup post_id → hora do dia
    hour_map: dict[str, int] = {}
    for post in posts:
        try:
            from dateutil import parser as dateutil_parser
            dt = dateutil_parser.isoparse(post["published_at"])
            hour_map[post["post_id"]] = dt.hour
        except Exception:
            pass

    if not hour_map:
        return {"profile_id": profile_id, "message": "Não foi possível parsear horários dos posts.", "data": []}

    # Agrega métricas por hora usando aggregation pipeline
    pipeline = [
        {"$match": {"profile_id": profile_id, "er_simple": {"$exists": True, "$gt": 0}}},
        # Último snapshot por post
        {"$sort": {"post_id": 1, "date": -1}},
        {"$group": {
            "_id": "$post_id",
            "er_simple": {"$first": "$er_simple"},
        }},
    ]

    metric_results = {r["_id"]: r["er_simple"] for r in mongo_repo.engagement_metrics.aggregate(pipeline)}

    # Acumula por hora
    hour_buckets: dict[int, list[float]] = {h: [] for h in range(24)}
    for post_id, hour in hour_map.items():
        if post_id in metric_results:
            hour_buckets[hour].append(metric_results[post_id])

    data = []
    for hour in range(24):
        values = hour_buckets[hour]
        if values:
            data.append({
                "hour": hour,
                "avg_er_simple": round(sum(values) / len(values), 6),
                "post_count": len(values),
            })

    data.sort(key=lambda x: x["avg_er_simple"], reverse=True)

    return {"profile_id": profile_id, "count": len(data), "data": data}


@router.get(
    "/by-format",
    summary="Engajamento por tipo de mídia",
    description=(
        "Calcula o engajamento médio (er_simple, er_reach, amplification_rate) "
        "agrupado por tipo de mídia: IMAGE, CAROUSEL_ALBUM e VIDEO. "
        "Útil para comparar o desempenho de diferentes formatos de conteúdo."
    ),
)
async def engagement_by_format(profile_id: str = Depends(get_authenticated_profile)):
    # Aggregation: junta engagement_metrics com posts pelo post_id para ter o media_type
    pipeline = [
        {"$match": {"profile_id": profile_id}},
        # Último engagement por post
        {"$sort": {"post_id": 1, "date": -1}},
        {"$group": {
            "_id": "$post_id",
            "er_simple": {"$first": "$er_simple"},
            "er_reach": {"$first": "$er_reach"},
            "amplification_rate": {"$first": "$amplification_rate"},
            "relative_reach": {"$first": "$relative_reach"},
        }},
        # Lookup para pegar media_type do post
        {"$lookup": {
            "from": "posts",
            "localField": "_id",
            "foreignField": "post_id",
            "as": "post_info",
        }},
        {"$unwind": {"path": "$post_info", "preserveNullAndEmptyArrays": False}},
        {"$group": {
            "_id": "$post_info.media_type",
            "avg_er_simple": {"$avg": "$er_simple"},
            "avg_er_reach": {"$avg": "$er_reach"},
            "avg_amplification_rate": {"$avg": "$amplification_rate"},
            "avg_relative_reach": {"$avg": "$relative_reach"},
            "post_count": {"$sum": 1},
        }},
        {"$sort": {"avg_er_simple": -1}},
    ]

    results = list(mongo_repo.engagement_metrics.aggregate(pipeline))

    data = []
    for r in results:
        data.append({
            "media_type": r["_id"],
            "avg_er_simple": round(r.get("avg_er_simple") or 0, 6),
            "avg_er_reach": round(r.get("avg_er_reach") or 0, 6),
            "avg_amplification_rate": round(r.get("avg_amplification_rate") or 0, 8),
            "avg_relative_reach": round(r.get("avg_relative_reach") or 0, 4),
            "post_count": r.get("post_count", 0),
        })

    return {"profile_id": profile_id, "count": len(data), "data": data}


@router.get(
    "/engagement-trend",
    summary="Tendência de engajamento ao longo do tempo",
    description=(
        "Retorna a série temporal do er_simple médio diário do perfil, "
        "permitindo visualizar tendências de engajamento ao longo do período. "
        "Parâmetro `days` define a janela de análise (padrão: 30 dias)."
    ),
)
async def engagement_trend(
    days: int = Query(default=30, ge=7, le=365, description="Janela de análise em dias"),
    profile_id: str = Depends(get_authenticated_profile),
):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()

    pipeline = [
        {"$match": {
            "profile_id": profile_id,
            "date": {"$gte": since},
            "er_simple": {"$exists": True, "$gt": 0},
        }},
        {"$group": {
            "_id": "$date",
            "avg_er_simple": {"$avg": "$er_simple"},
            "avg_er_reach": {"$avg": "$er_reach"},
            "post_count": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
        {"$project": {
            "_id": 0,
            "date": "$_id",
            "avg_er_simple": {"$round": ["$avg_er_simple", 6]},
            "avg_er_reach": {"$round": ["$avg_er_reach", 6]},
            "post_count": 1,
        }},
    ]

    results = list(mongo_repo.engagement_metrics.aggregate(pipeline))

    return {"profile_id": profile_id, "days": days, "count": len(results), "data": results}
