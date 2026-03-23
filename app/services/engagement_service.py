"""
Transform Service 2.1 — engagement_service
Calcula métricas derivadas de engajamento para cada post com base nos 
snapshots diários (post_snapshots) e insights de lifetime (post_insights).

Fórmulas implementadas:
1. er_simple = (likes + comments) / followers
2. er_weighted_post = (shares*1.42 + likes*1.25 + comments*1.0 + saves*1.0) / followers
3. er_reach_weighted_post = (shares*1.42 + likes*1.25 + comments*1.0 + saves*1.0) / reach
4. er_reach = total_interactions / reach
5. er_followers = total_interactions / followers
6. relative_reach = reach / followers
7. amplification_rate = shares / reach
8. loyalty_rate = (unique_accounts_engaged / reach) / (total_interactions / views)  [Sanches & Ramos, 2025]
9. er_views = total_interactions / views  [Substitui er_impressions Hootsuite]
10. velocity_likes_24h = delta de likes no dia
11. velocity_comments_24h = delta de comentários no dia
12. days_since_published = dias entre a publicação e a coleta

Destino: collection `engagement_metrics` (único por post_id + date).
"""

import logging
from datetime import datetime, date, timezone
from dateutil import parser as dateutil_parser

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)


def _calculate_velocity(post_id: str, current_date: date, current_likes: int, current_comments: int) -> tuple[int, int]:
    """
    Busca o snapshot do dia anterior para calcular a velocidade (crescimento no dia).
    Retorna (delta_likes, delta_comments).
    """
    # Para simplificar, buscamos o último snapshot anterior a esta data
    prev_snapshot = mongo_repo.post_snapshots.find_one(
        {"post_id": post_id, "date": {"$lt": current_date.isoformat()}},
        sort=[("date", -1)]
    )

    if not prev_snapshot:
        return 0, 0

    delta_likes = current_likes - prev_snapshot.get("like_count", 0)
    delta_comments = current_comments - prev_snapshot.get("comments_count", 0)

    # Evita deltas negativos por falha de coleta anterior ou exclusão em massa
    return max(0, delta_likes), max(0, delta_comments)


def calculate_metrics_for_post(
    post: dict,
    snapshot: dict,
    insights: dict,
    collected_at: datetime
) -> dict | None:
    """Consolida e calcula todas as métricas de um post para uma data específica."""

    try:
        current_date_str = snapshot["date"]
        current_date = date.fromisoformat(current_date_str)
        published_at_str = post.get("published_at")
        published_at = dateutil_parser.isoparse(published_at_str).date() if published_at_str else current_date
        
        days_since_published = (current_date - published_at).days
        # Nunca negativo
        days_since_published = max(0, days_since_published)

    except Exception as e:
        logger.warning(f"[engagement_service] Erro parseando datas post {post['post_id']}: {e}")
        return None

    # Base counts (do snapshot diário)
    likes = snapshot.get("like_count", 0)
    comments = snapshot.get("comments_count", 0)
    followers = snapshot.get("followers_at_date", 0)

    # Base API Insights (acumulado)
    reach = insights.get("reach", 0)
    shares = insights.get("shares", 0)
    saves = insights.get("saved", 0)
    total_interactions = insights.get("total_interactions", 0)
    views = insights.get("views", 0)
    
    # Prevenção Div/0
    safe_followers = followers if followers > 0 else 1
    safe_reach = reach if reach > 0 else 1
    safe_views = views if views > 0 else 1

    # 1 a 7 - Engajamento Simples e Ponderados
    er_simple = (likes + comments) / safe_followers
    
    weighted_sum = (shares * 1.42) + (likes * 1.25) + (comments * 1.0) + (saves * 1.0)
    er_weighted_post = weighted_sum / safe_followers
    er_reach_weighted_post = weighted_sum / safe_reach
    er_reach = total_interactions / safe_reach
    er_followers = total_interactions / safe_followers
    relative_reach = reach / safe_followers
    amplification_rate = shares / safe_reach

    # 8 - Loyalty Rate (Sanches & Ramos 2025)
    # page_interaction_rate = unique_accounts / reach. A API de Insights retorna total_interactions, 
    # porém profile_activity e interações agregadas muitas vezes são proxies para contas engajadas. 
    # Para fidelidade acadêmica ao "unique accounts", usaremos o reach do post engajado vs total_interactions.
    # Por padrão a Graph API não devolve "número de contas únicas que engajaram" por post, 
    # então usamos total_interactions como melhor proxy computável para a taxa.
    page_interaction_rate = total_interactions / safe_reach
    virality_rate = total_interactions / safe_views
    loyalty_rate = page_interaction_rate / virality_rate if virality_rate > 0 else 0.0

    # 9 - ER Views (Hootsuite proxy para impressions)
    er_views = total_interactions / safe_views

    # 10 e 11 - Velocidade
    vel_likes, vel_comments = _calculate_velocity(post["post_id"], current_date, likes, comments)

    return {
        "post_id": post["post_id"],
        "profile_id": post["profile_id"],
        "date": current_date_str,
        
        "er_simple": er_simple,
        "er_weighted_post": er_weighted_post,
        "er_reach_weighted_post": er_reach_weighted_post,
        "er_reach": er_reach,
        "er_followers": er_followers,
        "relative_reach": relative_reach,
        "amplification_rate": amplification_rate,
        
        "loyalty_rate": loyalty_rate,
        "page_interaction_rate": page_interaction_rate,
        "virality_rate": virality_rate,
        "er_views": er_views,
        
        "velocity_likes_24h": vel_likes,
        "velocity_comments_24h": vel_comments,
        "days_since_published": days_since_published,
        
        "calculated_at": collected_at
    }


def run_engagement_service(profile_id: str, target_date: date | None = None) -> dict:
    """
    Calcula as métricas de engajamento para todos os posts de um perfil em uma dada data.
    Lê os dados de: posts, post_snapshots (da data alvo), e o ÚLTIMO post_insights.
    Upsert na collection: engagement_metrics.
    """
    calc_date = target_date or datetime.now(timezone.utc).date()
    date_str = calc_date.isoformat()
    collected_at = datetime.now(timezone.utc)
    
    logger.info(f"[engagement_service] Iniciando processamento para profile_id={profile_id} em date={calc_date}")

    # Puxa os snapshots do dia
    snapshots = list(mongo_repo.post_snapshots.find({"profile_id": profile_id, "date": date_str}))
    if not snapshots:
        return {
            "status": "ok", "profile_id": profile_id, "processed": 0,
            "message": f"Nenhum post_snapshot para {date_str}. Rode o snapshot_service primeiro."
        }

    # Puxa os meta-dados dos posts correspondentes
    post_ids = [s["post_id"] for s in snapshots]
    posts = list(mongo_repo.posts.find({"post_id": {"$in": post_ids}}))
    post_map = {p["post_id"]: p for p in posts}

    operations = []
    processed = 0

    for snap in snapshots:
        pos_id = snap["post_id"]
        if pos_id not in post_map:
            continue
            
        post = post_map[pos_id]
        
        # Puxa o último insight do post (ordenado por collected_at DESC)
        insight = mongo_repo.post_insights.find_one(
            {"post_id": pos_id},
            sort=[("collected_at", -1)]
        )
        if not insight:
            insight = {}  # Usa defaults se o insights_service ainda não rodou para este post

        metric_doc = calculate_metrics_for_post(post, snap, insight, collected_at)
        if not metric_doc:
            continue

        operations.append(
            UpdateOne(
                {"post_id": pos_id, "date": date_str},
                {"$set": metric_doc},
                upsert=True
            )
        )
        processed += 1

    if operations:
        try:
            result = mongo_repo.engagement_metrics.bulk_write(operations, ordered=False)
            logger.info(f"[engagement_service] Concluído. Upserts={result.upserted_count}, Modified={result.modified_count}")
        except BulkWriteError as e:
            logger.error(f"[engagement_service] BulkWriteError: {e.details}")

    return {
        "status": "ok", "profile_id": profile_id, "date": date_str, "processed": processed,
        "message": f"Métricas de engajamento calculadas para {processed} posts."
    }
