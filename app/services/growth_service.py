"""
Transform Service 2.2 — growth_service

Lê os profile_snapshots de um perfil e calcula o crescimento (variação) de seguidores
e de publicações (media_count) em diferentes janelas de tempo (ex: 24h e 7 dias).

Métricas calculadas e agregadas:
- followers_growth_24h (absoluto)
- followers_growth_24h_pct (percentual)
- media_growth_24h (absoluto - equivalente a frequência de posts no dia)
- followers_growth_7d
- followers_growth_7d_pct
- media_growth_7d

Destino: collection `profile_snapshots` (atualiza o documento do próprio dia com os novos campos de crescimento).
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


def calculate_growth_for_snapshot(current_snap: dict, prev_snap_24h: dict | None, prev_snap_7d: dict | None) -> dict:
    """Retorna um dicionário com os campos de crescimento calculados."""
    
    current_followers = current_snap.get("followers_count", 0)
    current_media = current_snap.get("media_count", 0)
    
    growth_data = {}
    
    # Crescimento 24h
    if prev_snap_24h:
        prev_followers = prev_snap_24h.get("followers_count", current_followers)
        prev_media = prev_snap_24h.get("media_count", current_media)
        
        abs_growth = current_followers - prev_followers
        pct_growth = (abs_growth / prev_followers) if prev_followers > 0 else 0.0
        
        growth_data["followers_growth_24h"] = abs_growth
        growth_data["followers_growth_24h_pct"] = pct_growth
        growth_data["media_growth_24h"] = max(0, current_media - prev_media)
    else:
        growth_data["followers_growth_24h"] = 0
        growth_data["followers_growth_24h_pct"] = 0.0
        growth_data["media_growth_24h"] = 0

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
    Calcula as métricas de crescimento de um perfil em uma determinada data.
    Atualiza o respectivo `profile_snapshots` com as novas propriedades de engajamento do perfil.
    """
    calc_date = target_date or datetime.now(timezone.utc).date()
    date_str = calc_date.isoformat()
    
    logger.info(f"[growth_service] Iniciando processamento para profile_id={profile_id} em date={calc_date}")

    # Puxa o snapshot alvo
    current_snap = mongo_repo.profile_snapshots.find_one({"profile_id": profile_id, "date": date_str})
    if not current_snap:
        return {
            "status": "ok", "profile_id": profile_id, "processed": 0,
            "message": f"Nenhum profile_snapshot para {date_str}. Rode o snapshot_service primeiro."
        }

    # Busca snapshots de referência do passado (-1 dia, -7 dias)
    date_24h_ago = calc_date - timedelta(days=1)
    date_7d_ago = calc_date - timedelta(days=7)

    prev_snap_24h = _get_snapshot_for_date(profile_id, date_24h_ago)
    prev_snap_7d = _get_snapshot_for_date(profile_id, date_7d_ago)

    growth_data = calculate_growth_for_snapshot(current_snap, prev_snap_24h, prev_snap_7d)
    growth_data["calculated_at"] = datetime.now(timezone.utc)

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
