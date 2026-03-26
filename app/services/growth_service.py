"""
Transform Service 2.2 — growth_service

Rodado pelo dag_weekly_insights (semanal). Lê os profile_snapshots de um perfil
e calcula o crescimento de seguidores e publicações na janela de 7 dias,
além do Loyalty Rate usando profile_insights do mesmo período.

Métricas calculadas e salvas em profile_snapshots:
- followers_growth_7d       (absoluto — delta de 7 dias)
- followers_growth_7d_pct   (percentual)
- media_growth_7d           (posts publicados na semana)
- loyalty_rate              (page_interaction_rate / virality_rate)
- page_interaction_rate     (accounts_engaged / reach)
- virality_rate             (total_interactions / views)

Nota: métricas de 24h (followers_growth_24h, media_growth_24h) foram removidas
pois o service roda semanalmente e as métricas diárias perdem significado nesse contexto.

Destino: campo `growth` dentro do documento em `profile_snapshots` da data-alvo.
"""

import logging
from datetime import datetime, date, timedelta, timezone

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)


def _get_snapshot_for_date(profile_id: str, target_date: date) -> dict | None:
    """Busca o snapshot de uma data exata ou o mais próximo anterior a ela."""
    # Tenta um match exato
    exact = mongo_repo.profile_snapshots.find_one({"profile_id": profile_id, "date": target_date.isoformat()})
    if exact:
        return exact
        
    # Busca o último registro antes dessa data
    closest = mongo_repo.profile_snapshots.find_one(
        {"profile_id": profile_id, "date": {"$lt": target_date.isoformat()}},
        sort=[("date", -1)]
    )
    return closest


def calculate_growth_for_snapshot(current_snap: dict, prev_snap_7d: dict | None) -> dict:
    """
    Calcula crescimento de seguidores e publicações na janela de 7 dias.

    Nota: métricas de 24h foram removidas — o service roda semanalmente
    via dag_weekly_insights, tornando o delta diário sem significado aqui.
    """
    current_followers = current_snap.get("followers_count", 0)
    current_media = current_snap.get("media_count", 0)

    growth_data = {}

    # # Crescimento 24h — omitido: service roda semanalmente
    # if prev_snap_24h:
    #     prev_followers = prev_snap_24h.get("followers_count", current_followers)
    #     prev_media = prev_snap_24h.get("media_count", current_media)
    #     abs_growth = current_followers - prev_followers
    #     pct_growth = (abs_growth / prev_followers) if prev_followers > 0 else 0.0
    #     growth_data["followers_growth_24h"] = abs_growth
    #     growth_data["followers_growth_24h_pct"] = pct_growth
    #     growth_data["media_growth_24h"] = max(0, current_media - prev_media)

    # Crescimento 7d
    if prev_snap_7d:
        prev_followers_7d = prev_snap_7d.get("followers_count", current_followers)
        prev_media_7d = prev_snap_7d.get("media_count", current_media)

        abs_growth_7d = current_followers - prev_followers_7d
        pct_growth_7d = (abs_growth_7d / prev_followers_7d) if prev_followers_7d > 0 else 0.0

        growth_data["followers_growth_7d"] = abs_growth_7d
        growth_data["followers_growth_7d_pct"] = pct_growth_7d
        growth_data["media_growth_7d"] = max(0, current_media - prev_media_7d)
    else:
        growth_data["followers_growth_7d"] = 0
        growth_data["followers_growth_7d_pct"] = 0.0
        growth_data["media_growth_7d"] = 0

    return growth_data


def run_growth_service(profile_id: str, target_date: date | None = None) -> dict:
    """
    Ponto de entrada 2.2 — chamado pelo dag_weekly_insights.

    Calcula crescimento semanal de seguidores/publicações e Loyalty Rate,
    salvando os resultados no campo `growth` do profile_snapshot da data-alvo.

    target_date: data do snapshot alvo (None = hoje UTC, data da execução semanal).
    """
    calc_date = target_date or datetime.now(timezone.utc).date()
    date_str = calc_date.isoformat()

    logger.info(f"[growth_service] Iniciando processamento para profile_id={profile_id} em date={calc_date}")

    # Puxa o snapshot alvo (coletado diariamente pelo dag_instagram_etl)
    current_snap = mongo_repo.profile_snapshots.find_one({"profile_id": profile_id, "date": date_str})
    if not current_snap:
        return {
            "status": "ok", "profile_id": profile_id, "processed": 0,
            "message": f"Nenhum profile_snapshot para {date_str}. Rode o snapshot_service primeiro."
        }

    # Busca snapshot de referência de 7 dias atrás
    date_7d_ago = calc_date - timedelta(days=7)
    prev_snap_7d = _get_snapshot_for_date(profile_id, date_7d_ago)

    growth_data = calculate_growth_for_snapshot(current_snap, prev_snap_7d)
    growth_data["calculated_at"] = datetime.now(timezone.utc)

    # Lógica de Loyalty Rate (Sanches & Ramos, 2025)
    # Requer que o `profile_insights` diário tenha rodado primeiro para coletar accounts_engaged
    insight_doc = mongo_repo.profile_insights.find_one({"profile_id": profile_id, "period_until": date_str})
    if insight_doc:
        reach = insight_doc.get("reach") or 0
        accounts_engaged = insight_doc.get("accounts_engaged") or 0
        total_interactions = insight_doc.get("total_interactions") or 0
        views = insight_doc.get("views") or 0
        
        safe_reach = reach if reach > 0 else 1
        safe_views = views if views > 0 else 1
        
        page_interaction_rate = accounts_engaged / safe_reach
        virality_rate = total_interactions / safe_views
        
        loyalty_rate = page_interaction_rate / virality_rate if virality_rate > 0 else 0.0
        
        growth_data["loyalty_rate"] = loyalty_rate
        growth_data["page_interaction_rate"] = page_interaction_rate
        growth_data["virality_rate"] = virality_rate
    else:
        logger.warning(f"[growth_service] profile_insights não encontrado para {profile_id} em {date_str}. Loyalty Rate omitido.")

    # Aplica o update no próprio profile_snapshots
    try:
        result = mongo_repo.profile_snapshots.update_one(
            {"_id": current_snap["_id"]},
            {"$set": {"growth": growth_data}}
        )
        logger.info(f"[growth_service] Concluído. Modificado={result.modified_count}")
    except Exception as e:
        logger.error(f"[growth_service] Erro ao atualizar profile_snapshot: {e}")
        return {"status": "error", "message": str(e)}

    return {
        "status": "ok", 
        "profile_id": profile_id, 
        "date": date_str, 
        "processed": 1,
        "metrics": growth_data,
        "message": "Crescimento de perfil calculado com sucesso."
    }
