"""
Extract Service 1.5 + 1.6 — insights_service

Duas funções de entrada neste módulo:
  run_post_insights_service(profile_id)   -> 1.5 — métricas de posts individuais
  run_profile_insights_service(profile_id) -> 1.6 — métricas semanais do perfil

    1.5 Post Insights 
  Endpoint: GET /{media_id}/insights?metric={...}
  Collection: post_insights (append-only)

  Por que append-only?
    Ao contrário dos snapshots (que representam o estado de UM dia), os insights acumulados crescem ao longo do tempo.
    Armazenar múltiplas coletas permite analisar a curva de crescimento de `reach` e `saves` ao longo de dias/semanas — útil para o modelo de ML.

  Métricas por tipo de mídia (v25.0 - impressions removido desde v22):
    IMAGE / CAROUSEL_ALBUM : reach, saved, shares, total_interactions, views, profile_activity
    VIDEO                  : reach, saved, shares, total_interactions, views, ig_reels_avg_watch_time, ig_reels_video_view_total_time
    STORY                  : reach, shares, replies, total_interactions, navigation, views, profile_activity

  Nota: posts publicados ANTES da conversão para Business/Creator retornam erro na API. 
  Esse comportamento é esperado e documentado - o service registra o erro e continua para o próximo post.

    1.6 Profile Insights 
  Duas chamadas à API por execução:

  A) Métricas de interação (por período de 7 dias):
      GET /{ig_user_id}/insights
          ?metric=reach,profile_views,total_interactions[,follows_and_unfollows]
          &period=day&metric_type=total_value&since={ts}&until={ts}

      Nota: follows_and_unfollows disponível apenas no fluxo facebook.

  B) Dados demográficos (breakdown por country, city, age, gender):
      GET /{ig_user_id}/insights
          ?metric=engaged_audience_demographics,follower_demographics
          &period=lifetime&metric_type=total_value
          &timeframe=this_month&breakdown={breakdown}

      Retorna data:[] se a conta tiver < 100 seguidores no período - esperado.

  Collection: profile_insights (upsert por profile_id + period_until - único por semana)
"""

import time
import logging
import requests
from datetime import datetime, date, timedelta, timezone
from dateutil import parser as dateutil_parser

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v25.0"

# Métricas disponíveis por tipo de mídia (v25.0)
METRICS_MAP = {
    "IMAGE":          "reach,saved,shares,total_interactions,views,profile_activity",
    "CAROUSEL_ALBUM": "reach,saved,shares,total_interactions,views,profile_activity",
    "VIDEO":          "reach,saved,shares,total_interactions,views,ig_reels_avg_watch_time,ig_reels_video_view_total_time",
    "STORY":          "reach,shares,replies,total_interactions,navigation,views,profile_activity",
}
DEFAULT_METRICS = "reach,saved,shares,total_interactions"

AUDIENCE_BREAKDOWNS = ("country", "city", "age", "gender")


def _get_token_doc(profile_id: str) -> dict | None:
    """Busca token válido no MongoDB. Retorna None se inválido/expirado."""
    doc = mongo_repo.oauth_tokens.find_one({"profile_id": profile_id})
    if not doc:
        logger.error(f"[insights_service] Token não encontrado para profile_id={profile_id}")
        return None
    if not doc.get("is_valid", False):
        logger.error(f"[insights_service] Token inválido para profile_id={profile_id}")
        return None
    expires_at = doc.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        logger.error(f"[insights_service] Token expirado para profile_id={profile_id}")
        return None
    return doc


def _get_base_url(auth_method: str) -> str:
    return (
        "https://graph.facebook.com" if auth_method == "facebook"
        else "https://graph.instagram.com"
    )


# 1.5 — Post Insights

def fetch_post_insights(base_url: str, post: dict, access_token: str) -> dict | None:
    """
    Coleta insights de um post individual.

    Returna dict com as métricas achatadas (name → value),
    ou None se o post for inelegível (pré-Business, privado, etc.)
    """
    media_id   = post["post_id"]
    media_type = post.get("media_type", "IMAGE")
    metrics    = METRICS_MAP.get(media_type, DEFAULT_METRICS)

    url = (
        f"{base_url}/{GRAPH_VERSION}/{media_id}/insights"
        f"?metric={metrics}&access_token={access_token}"
    )

    try:
        response = requests.get(url, timeout=15)
    except requests.RequestException as e:
        logger.error(f"[insights_service] Erro de rede no post {media_id}: {e}")
        return None

    if response.status_code != 200:
        error_msg = response.json().get("error", {}).get("message", response.text)
        logger.warning(f"[insights_service] Post inelegível {media_id} ({media_type}): {error_msg}")
        return None

    # Achata: [{name, values:[{value}]}] → {name: value}
    raw_data = response.json().get("data", [])
    return {
        item["name"]: (
            item["values"][0]["value"] if item.get("values")
            else item.get("value")
        )
        for item in raw_data
    }


def run_post_insights_service(profile_id: str) -> dict:
    """
    Ponto de entrada 1.5 — chamado pelo DAG do Airflow.

    Append-only: cada execução diária adiciona um novo documento em post_insights.

    Retorna:
        {
            "status": "ok" | "error",
            "profile_id": str,
            "posts_total": int,
            "posts_with_insights": int,
            "posts_ineligible": int,   # pré-Business, privado, etc.
            "message": str,
        }
    """
    logger.info(f"[insights_service] Iniciando post insights para profile_id={profile_id}")

    token_doc = _get_token_doc(profile_id)
    if not token_doc:
        return {"status": "error", "profile_id": profile_id,
                "message": "Token não encontrado, inválido ou expirado"}

    access_token = token_doc["long_lived_token"]
    auth_method  = token_doc.get("auth_method", "facebook")
    base_url     = _get_base_url(auth_method)
    collected_at = datetime.now(timezone.utc)

    # Lê posts do banco (com media_type para selecionar métricas corretas)
    posts = list(mongo_repo.posts.find(
        {"profile_id": profile_id},
        {"post_id": 1, "media_type": 1, "_id": 0},
    ))

    if not posts:
        return {"status": "ok", "profile_id": profile_id, "posts_total": 0,
                "posts_with_insights": 0, "posts_ineligible": 0,
                "message": "Nenhum post no banco. Execute media_discovery_service primeiro."}

    posts_with_insights = 0
    posts_ineligible    = 0

    for post in posts:
        metrics = fetch_post_insights(base_url, post, access_token)

        if metrics is None:
            posts_ineligible += 1
            continue

        insight_doc = {
            "post_id":      post["post_id"],
            "profile_id":   profile_id,
            "media_type":   post.get("media_type"),
            "collected_at": collected_at,
            **metrics,   # achata todas as métricas no nível do documento
        }

        mongo_repo.post_insights.insert_one(insight_doc)
        posts_with_insights += 1

    logger.info(
        f"[insights_service] Post insights concluído: "
        f"total={len(posts)} | com_insights={posts_with_insights} | inelegíveis={posts_ineligible}"
    )

    return {
        "status": "ok",
        "profile_id": profile_id,
        "posts_total": len(posts),
        "posts_with_insights": posts_with_insights,
        "posts_ineligible": posts_ineligible,
        "message": f"{posts_with_insights} posts com insights coletados",
    }


# 1.6 — Profile Insights (semanal)

def fetch_interaction_metrics(
    base_url: str,
    profile_id: str,
    access_token: str,
    auth_method: str,
    since: datetime,
    until: datetime,
) -> dict:
    """
    Coleta métricas de interação do perfil para o período especificado.

    facebook:  reach, profile_views, total_interactions, follows_and_unfollows
    instagram: reach, profile_views, total_interactions
              (follows_and_unfollows não disponível neste fluxo)

    Retorna dict {metric_name: total_value}.
    """
    if auth_method == "facebook":
        metrics = "accounts_engaged,views,reach,profile_views,total_interactions,follows_and_unfollows"
    else:
        metrics = "accounts_engaged,views,reach,profile_views,total_interactions"

    since_ts = int(time.mktime(since.timetuple()))
    until_ts = int(time.mktime(until.timetuple()))

    url = (
        f"{base_url}/{GRAPH_VERSION}/{profile_id}/insights"
        f"?metric={metrics}"
        f"&period=day"
        f"&metric_type=total_value"
        f"&since={since_ts}"
        f"&until={until_ts}"
        f"&access_token={access_token}"
    )

    try:
        response = requests.get(url, timeout=15)
    except requests.RequestException as e:
        logger.error(f"[insights_service] Erro de rede em profile insights: {e}")
        return {}

    if response.status_code != 200:
        error_msg = response.json().get("error", {}).get("message", response.text)
        logger.error(f"[insights_service] Erro {response.status_code} em interaction metrics: {error_msg}")
        return {}

    # Achata: [{name, values:[{value}]}] → {name: total_value}
    result = {}
    for item in response.json().get("data", []):
        name = item["name"]
        # total_value vem como object quando metric_type=total_value
        total = item.get("total_value", {})
        result[name] = total.get("value") if isinstance(total, dict) else total
    return result


def fetch_audience_demographics(
    base_url: str,
    profile_id: str,
    access_token: str,
    timeframe: str = "this_month",
) -> dict:
    """
    Coleta dados demográficos da audiência por breakdown.
    Uma chamada à API por breakdown (exigência da API).

    Retorna dict {breakdown: {dimension: count}}, ex:
        {"country": {"BR": 412, "US": 38}, "age": {"18-24": 230}, ...}

    Retorna {} por breakdown se conta tiver < 100 seguidores/engajamentos (esperado).
    """
    results = {}

    for breakdown in AUDIENCE_BREAKDOWNS:
        url = (
            f"{base_url}/{GRAPH_VERSION}/{profile_id}/insights"
            f"?metric=engaged_audience_demographics,follower_demographics"
            f"&period=lifetime"
            f"&metric_type=total_value"
            f"&timeframe={timeframe}"
            f"&breakdown={breakdown}"
            f"&access_token={access_token}"
        )

        try:
            response = requests.get(url, timeout=15)
        except requests.RequestException as e:
            logger.error(f"[insights_service] Erro de rede no breakdown {breakdown}: {e}")
            results[breakdown] = {}
            continue

        if response.status_code != 200:
            error_msg = response.json().get("error", {}).get("message", response.text)
            logger.warning(f"[insights_service] Erro no breakdown {breakdown}: {error_msg}")
            results[breakdown] = {}
            continue

        data = response.json().get("data", [])

        # Extrai follower_demographics para o breakdown atual
        # Estrutura: data[i].total_value.breakdowns[0].results → [{dimension_values:["BR"], value:412}]
        agg: dict[str, int] = {}
        for metric_item in data:
            if metric_item.get("name") != "follower_demographics":
                continue
            for bd in metric_item.get("total_value", {}).get("breakdowns", []):
                for entry in bd.get("results", []):
                    dims  = entry.get("dimension_values", [])
                    value = entry.get("value", 0)
                    key   = dims[0] if dims else "unknown"
                    agg[key] = agg.get(key, 0) + value

        results[breakdown] = agg
        logger.info(f"[insights_service] Demográfico breakdown={breakdown} | entradas={len(agg)}")

    return results


def run_profile_insights_service(
    profile_id: str,
    period_days: int = 7,
    target_until: date | None = None,
) -> dict:
    """
    Ponto de entrada 1.6 — chamado pelo DAG do Airflow (semanal).

    period_days:   janela de coleta de métricas de interação (padrão=7 dias)
    target_until:  data final do período. None = hoje (UTC).

    Upsert por (profile_id, period_until) - re-runs são idempotentes.

    Retorna:
        {
            "status": "ok" | "error",
            "profile_id": str,
            "period_since": str,
            "period_until": str,
            "message": str,
        }
    """
    until_dt  = target_until or datetime.now(timezone.utc).date()
    since_dt  = until_dt - timedelta(days=period_days)
    until_ts  = datetime.combine(until_dt, datetime.min.time())
    since_ts  = datetime.combine(since_dt, datetime.min.time())
    collected_at = datetime.now(timezone.utc)

    logger.info(
        f"[insights_service] Iniciando profile insights: "
        f"profile_id={profile_id} | período={since_dt} → {until_dt}"
    )

    token_doc = _get_token_doc(profile_id)
    if not token_doc:
        return {"status": "error", "profile_id": profile_id,
                "message": "Token não encontrado, inválido ou expirado"}

    access_token = token_doc["long_lived_token"]
    auth_method  = token_doc.get("auth_method", "facebook")
    base_url     = _get_base_url(auth_method)

    # A) Métricas de interação do período
    interaction = fetch_interaction_metrics(
        base_url, profile_id, access_token, auth_method, since_ts, until_ts
    )

    # B) Dados demográficos (sempre this_month para cobrir o período)
    demographics = fetch_audience_demographics(base_url, profile_id, access_token)

    # Upsert em profile_insights (índice único: profile_id + period_until)
    insight_doc = {
        "profile_id":      profile_id,
        "period_since":    since_dt.isoformat(),
        "period_until":    until_dt.isoformat(),
        "collected_at":    collected_at,
        # Métricas de interação (None se não disponíveis)
        "accounts_engaged":       interaction.get("accounts_engaged"),
        "views":                  interaction.get("views"),
        "reach":                  interaction.get("reach"),
        "profile_views":          interaction.get("profile_views"),
        "total_interactions":     interaction.get("total_interactions"),
        "follows_and_unfollows":  interaction.get("follows_and_unfollows"),  # None no fluxo instagram
        # Demográficos (dict vazio se < 100 seguidores no período)
        "audience_country": demographics.get("country", {}),
        "audience_city":    demographics.get("city", {}),
        "audience_age":     demographics.get("age", {}),
        "audience_gender":  demographics.get("gender", {}),
    }

    mongo_repo.profile_insights.update_one(
        {"profile_id": profile_id, "period_until": until_dt.isoformat()},
        {"$set": insight_doc},
        upsert=True,
    )

    logger.info(
        f"[insights_service] Profile insights salvo: "
        f"profile_id={profile_id} | reach={interaction.get('reach')} | "
        f"period={since_dt}→{until_dt}"
    )

    return {
        "status": "ok",
        "profile_id": profile_id,
        "period_since": since_dt.isoformat(),
        "period_until": until_dt.isoformat(),
        "message": f"Profile insights do período {since_dt} → {until_dt} coletados",
    }
