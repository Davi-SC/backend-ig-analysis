"""
Transform Service 2.5 — qualification_service

Implementa o Índice de Qualidade de Audiência (IQA) sobre dados reais coletados
pelo pipeline ELT, portando a metodologia validada no TCC (influencers_kim) para
o contexto de dados em tempo real via Meta Graph API.

Metodologia (replicando perfil_qualificacao.ipynb do TCC):

    1. Lê as métricas de engajamento acumuladas na collection `engagement_metrics`
       para todos os posts do perfil nos últimos `lookback_days` dias.

    2. Calcula, em nível de perfil:
       - TE mediana  = mediana(er_simple) de todos os posts do período
       - CV da TE    = std(er_simple) / mean(er_simple)   [dispersão relativa]

    3. Score composto (mesmos pesos validados no TCC):
       score = W_ER × rank_percentil(TE) + W_CV × (1 − rank_percentil(CV))
       Onde W_ER = 0.60 e W_CV = 0.40.

    Nota: com um único perfil coletado, rank_percentil não pode ser calculado
    intra-segmento (exige grupo de pares). Neste caso, o serviço retorna os
    valores absolutos (TE mediana e CV) sem rank — suficiente para o relatório.
    Quando múltiplos perfis estiverem coletados, o ranking intra-segmento pode
    ser adicionado sem alterar a interface.

    4. Classificação em tiers por quartis do score (ou por limiares absolutos
       quando há apenas um perfil):
         A (≥ 0.75) — alta qualificação
         B (≥ 0.50) — qualificação moderada-alta
         C (≥ 0.25) — qualificação moderada-baixa
         D (< 0.25) — baixa qualificação

    5. Upsert em `audience_qualification` (índice único: profile_id + calculated_date).

Referências:
    - Cruz, D.S.; Santos, F.A.O. (2026). Indicador Multidimensional para
      Qualificação de Audiência de Perfis no Instagram. TCC — IFMA.
    - Kim, S. et al. (2020). Multimodal Post Attentive Profiling for
      Influencer Marketing. WWW '20.
"""

import logging
import statistics
from datetime import datetime, date, timezone, timedelta

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)

# Pesos do score composto — validados no TCC via análise de sensibilidade
W_ER = 0.60
W_CV = 0.40

# Limiares absolutos de tier quando não há grupo de pares para ranking relativo
TIER_THRESHOLDS = {
    "A": 0.75,
    "B": 0.50,
    "C": 0.25,
}


def _assign_tier(score: float) -> str:
    """
    Classifica o score composto em um tier (A/B/C/D).
    Usa limiares absolutos. Quando múltiplos perfis estiverem disponíveis,
    substituir por quartis globais para comparabilidade.
    """
    if score >= TIER_THRESHOLDS["A"]:
        return "A"
    if score >= TIER_THRESHOLDS["B"]:
        return "B"
    if score >= TIER_THRESHOLDS["C"]:
        return "C"
    return "D"


def _compute_profile_metrics(er_values: list[float]) -> dict:
    """
    Calcula as métricas em nível de perfil a partir de uma lista de ER simples.

    Retorna:
        te_median  — mediana da TE (robusta a outliers)
        te_mean    — média da TE
        te_std     — desvio padrão da TE
        te_cv      — coeficiente de variação (std / mean)
        score      — score composto IQA
        tier       — classificação A/B/C/D
    """
    if not er_values:
        return {}

    te_median = statistics.median(er_values)
    te_mean = statistics.mean(er_values)
    te_std = statistics.pstdev(er_values)  # população (todos os posts do período)

    # CV — previne divisão por zero
    te_cv = (te_std / te_mean) if te_mean > 0 else 0.0

    # Score composto:
    # Normalizamos TE e CV para [0, 1] usando limiares práticos.
    # ER_simple típico no Instagram: 1%–10% (0.01–0.10 em decimal).
    # CV típico: 0.0 (perfeito) a 2.0+ (muito volátil).
    # Estas normalizações permitem comparação consistente.
    te_norm = min(te_median / 0.10, 1.0)   # 10% de ER como teto "excelente"
    cv_norm = min(te_cv / 2.0, 1.0)        # CV = 2.0 como teto "muito instável"

    score = W_ER * te_norm + W_CV * (1.0 - cv_norm)
    score = max(0.0, min(1.0, score))       # clamp [0, 1]

    return {
        "te_median": round(te_median, 6),
        "te_mean": round(te_mean, 6),
        "te_std": round(te_std, 6),
        "te_cv": round(te_cv, 6),
        "score": round(score, 4),
        "tier": _assign_tier(score),
    }


def run_qualification_service(
    profile_id: str,
    lookback_days: int = 30,
    target_date: date | None = None,
) -> dict:
    """
    Ponto de entrada do qualification_service.

    Calcula o IQA para o perfil com base nos dados reais coletados
    pelo pipeline ELT nos últimos `lookback_days` dias.

    Args:
        profile_id:    ID do perfil Instagram a qualificar.
        lookback_days: Janela de análise em dias (padrão: 30).
        target_date:   Data de referência. None = hoje (UTC).

    Retorna:
        {
            "status": "ok" | "error",
            "profile_id": str,
            "calculated_date": str,          # YYYY-MM-DD
            "lookback_days": int,
            "posts_analyzed": int,
            "te_median": float,              # mediana do ER simples
            "te_mean": float,
            "te_std": float,
            "te_cv": float,                  # coeficiente de variação
            "score": float,                  # score IQA [0, 1]
            "tier": str,                     # A / B / C / D
            "message": str,
        }
    """
    calc_date = target_date or datetime.now(timezone.utc).date()
    since_date = (calc_date - timedelta(days=lookback_days)).isoformat()
    calc_date_str = calc_date.isoformat()

    logger.info(
        f"[qualification_service] Iniciando qualificação: "
        f"profile_id={profile_id} | janela={lookback_days}d | ref={calc_date_str}"
    )

    # ── Lê engagement_metrics do período ─────────────────────────────────────
    # Para cada post, usa o registro mais recente dentro da janela de análise.
    pipeline = [
        {
            "$match": {
                "profile_id": profile_id,
                "date": {"$gte": since_date, "$lte": calc_date_str},
                "er_simple": {"$exists": True, "$gt": 0},
            }
        },
        # Último registro por post no período
        {"$sort": {"post_id": 1, "date": -1}},
        {
            "$group": {
                "_id": "$post_id",
                "er_simple": {"$first": "$er_simple"},
                "date": {"$first": "$date"},
            }
        },
    ]

    records = list(mongo_repo.engagement_metrics.aggregate(pipeline))

    if not records:
        msg = (
            f"Nenhum dado de engajamento encontrado para o período "
            f"{since_date} → {calc_date_str}. "
            "Execute o dag_instagram_elt por pelo menos 1 dia antes de qualificar."
        )
        logger.warning(f"[qualification_service] {msg}")
        return {
            "status": "ok",
            "profile_id": profile_id,
            "calculated_date": calc_date_str,
            "lookback_days": lookback_days,
            "posts_analyzed": 0,
            "message": msg,
        }

    er_values = [r["er_simple"] for r in records if isinstance(r.get("er_simple"), (int, float))]

    if len(er_values) < 3:
        msg = (
            f"Apenas {len(er_values)} post(s) com dados de ER no período. "
            "Mínimo recomendado: 3 posts para cálculo de CV significativo."
        )
        logger.warning(f"[qualification_service] {msg}")
        # Retorna dados parciais sem score/tier
        return {
            "status": "ok",
            "profile_id": profile_id,
            "calculated_date": calc_date_str,
            "lookback_days": lookback_days,
            "posts_analyzed": len(er_values),
            "te_median": round(statistics.median(er_values), 6) if er_values else None,
            "message": msg,
        }

    # ── Calcula métricas do perfil ────────────────────────────────────────────
    metrics = _compute_profile_metrics(er_values)

    # ── Monta documento final ─────────────────────────────────────────────────
    qualification_doc = {
        "profile_id": profile_id,
        "calculated_date": calc_date_str,
        "lookback_days": lookback_days,
        "posts_analyzed": len(er_values),
        "calculated_at": datetime.now(timezone.utc),
        **metrics,
    }

    # ── Upsert em audience_qualification ─────────────────────────────────────
    mongo_repo.audience_qualification.update_one(
        {"profile_id": profile_id, "calculated_date": calc_date_str},
        {"$set": qualification_doc},
        upsert=True,
    )

    logger.info(
        f"[qualification_service] Qualificação concluída: "
        f"profile_id={profile_id} | posts={len(er_values)} | "
        f"TE_median={metrics['te_median']:.4f} | CV={metrics['te_cv']:.4f} | "
        f"score={metrics['score']:.4f} | tier={metrics['tier']}"
    )

    return {
        "status": "ok",
        "profile_id": profile_id,
        "calculated_date": calc_date_str,
        "lookback_days": lookback_days,
        "posts_analyzed": len(er_values),
        **metrics,
        "message": (
            f"IQA calculado com {len(er_values)} posts | "
            f"Tier {metrics['tier']} | score={metrics['score']:.4f}"
        ),
    }
