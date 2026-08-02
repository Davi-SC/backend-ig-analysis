"""
Transform Service 2.4 — video_metrics_service

Lê os dados acumulados (post_insights) dos posts do tipo VIDEO (Reels)
para calcular e normalizar as métricas de retenção em formato de série.

Métricas calculadas:
- watch_time_per_view (em ms) = ig_reels_video_view_total_time / views
- reel_retention_score (0.0 a 1.0) = retenção normalizada em relação aos outros Reels do mesmo perfil

As métricas são atualizadas no próprio `engagement_metrics`.
"""

import logging
from datetime import datetime, date, timezone

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)


def run_video_metrics_service(profile_id: str, target_date: date | None = None) -> dict:
    """
    Calcula o score de retenção relativo para todos os vídeos ('VIDEO') do perfil.
    A retenção é baseada no tempo médio assistido ('watch_time_per_view').
    Salva os resultados na collection 'engagement_metrics' (upsert para a data alvo).
    """
    calc_date = target_date or datetime.now(timezone.utc).date()
    date_str = calc_date.isoformat()
    
    logger.info(f"[video_metrics_service] Processando retain scores para profile_id={profile_id} na data {calc_date}")

    # 1. Obter todos os IDs de vídeo deste perfil
    video_posts = list(mongo_repo.posts.find(
        {"profile_id": profile_id, "media_type": "VIDEO"},
        {"post_id": 1, "_id": 0}
    ))
    
    if not video_posts:
        return {
            "status": "ok", "profile_id": profile_id, "processed": 0,
            "message": "Nenhum post do tipo VIDEO encontrado."
        }
        
    video_ids = [vp["post_id"] for vp in video_posts]

    # 2. Resgatar os insights MAIS RECENTES (pois post_insights é append-like series temporais) de cada vídeo
    # Como não podemos fazer um subquery fácil para o mais recente de cada um sem Agreggation Pipeline,
    # agrupamos na memória.
    # A query de agregação mais eficiente para buscar o último insight de cada vídeo:
    pipeline = [
        {"$match": {"post_id": {"$in": video_ids}}},
        {"$sort": {"collected_at": -1}},
        {"$group": {
            "_id": "$post_id",
            "ig_reels_video_view_total_time": {"$first": "$ig_reels_video_view_total_time"},
            "views": {"$first": "$views"},
            "collected_at": {"$first": "$collected_at"}
        }}
    ]
    
    latest_insights = list(mongo_repo.post_insights.aggregate(pipeline))

    # 3. Calcular watch_time_per_view
    videometrics = {}
    max_watch_time = 0.0
    min_watch_time = float("inf")
    
    for ins in latest_insights:
        post_id = ins["_id"]
        total_time = ins.get("ig_reels_video_view_total_time", 0)
        views = ins.get("views", 0)
        
        # Só processamos se houver views para evitar divisão por zero
        if views > 0 and total_time > 0:
            wt_per_view = total_time / views
            videometrics[post_id] = wt_per_view
            
            if wt_per_view > max_watch_time:
                max_watch_time = wt_per_view
            if wt_per_view < min_watch_time:
                min_watch_time = wt_per_view

    # Trata caso de não haver mínimo útil ou ter um único valor
    if not videometrics:
        return {
            "status": "ok", "profile_id": profile_id, "processed": 0,
            "message": "Nenhum dado válido de watch time/views para calcular retenção."
        }

    # Range para normalização (Min-Max Scaler acadêmico de retenção 0-1)
    amplitude = max_watch_time - min_watch_time
    # Se todos vídeos tem exatamente a mesma métrica, amplitude = 0
    if amplitude == 0:
        amplitude = 1.0 

    operations = []
    
    # 4. Normalizar e montar as operações Bulk
    for post_id, wt_per_view in videometrics.items():
        # Min max scaler = (X - min) / (max - min)
        # Se amplitude fosse zero, deixamos o valor no meio: 0.5 (ou 1.0 dependendo da preferência)
        if max_watch_time == min_watch_time:
            retention_score = 1.0
        else:
            retention_score = (wt_per_view - min_watch_time) / amplitude
            
        operations.append(
            UpdateOne(
                {"post_id": post_id, "date": date_str},
                {"$set": {
                    "watch_time_per_view": wt_per_view,
                    "reel_retention_score": round(retention_score, 4),
                    "profile_id": profile_id  # fallback se engagement doc for upserted "cego"
                }},
                upsert=True
            )
        )
        
    # 5. Efetivar no banco
    if operations:
        try:
            result = mongo_repo.engagement_metrics.bulk_write(operations, ordered=False)
            logger.info(f"[video_metrics_service] Bulk update finalizado. Modificados={result.modified_count}, Upserted={result.upserted_count}")
        except BulkWriteError as e:
            logger.error(f"[video_metrics_service] Erro BulkWrite: {e.details}")
            
    return {
        "status": "ok", 
        "profile_id": profile_id, 
        "date": date_str, 
        "processed": len(operations),
        "message": f"Retenção calculada para {len(operations)} vídeos."
    }
