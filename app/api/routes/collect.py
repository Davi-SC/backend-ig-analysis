"""
Rota de coleta on-demand — /collect

Permite disparar manualmente a coleta de dados do Instagram para um perfil.
Útil para:
  - Coleta inicial após o primeiro login do usuário
  - Atualização pontual fora do ciclo diário do Airflow

Endpoints:
  POST /collect/initial  — pipeline completo (descoberta + snapshots + métricas)
  POST /collect/refresh  — atualização rápida (snapshots + métricas, sem redescoberta)

Auth: header obrigatório X-Profile-ID (validado via oauth_tokens no MongoDB).
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status

from app.utils.auth import get_authenticated_profile
from app.services.profile_service import run_profile_service
from app.services.media_discovery_service import run_media_discovery_service
from app.services.snapshot_service import run_snapshot_service
from app.services.insights_service import run_post_insights_service
from app.services.comments_service import run_comments_service
from app.services.engagement_service import run_engagement_service
from app.services.video_metrics_service import run_video_metrics_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collect", tags=["collect"])


def _run_step(name: str, fn, *args, **kwargs) -> dict:
    """Executa um service e retorna um dict de step padronizado."""
    try:
        result = fn(*args, **kwargs)
        return {"service": name, "status": result.get("status", "ok"), "message": result.get("message", "")}
    except Exception as e:
        logger.error(f"[collect] Erro em {name}: {e}")
        return {"service": name, "status": "error", "message": str(e)}


@router.post(
    "/initial",
    summary="Coleta inicial completa",
    description=(
        "Executa o pipeline completo de coleta para o perfil autenticado: "
        "perfil → descoberta de posts → snapshot → insights de posts → "
        "comentários → métricas de engajamento → métricas de vídeo. "
        "Deve ser chamado após o primeiro login do usuário."
    ),
)
async def collect_initial(profile_id: str = Depends(get_authenticated_profile)):
    """
    Pipeline completo de coleta (chamado no primeiro login).

    Roda os services em sequência. Se um step falhar, os seguintes ainda são tentados.
    Retorna um resumo detalhado de cada etapa.
    """
    logger.info(f"[collect/initial] Iniciando coleta completa para profile_id={profile_id}")

    steps = [
        _run_step("profile_service",          run_profile_service,          profile_id),
        _run_step("media_discovery_service",  run_media_discovery_service,  profile_id),
        _run_step("snapshot_service",         run_snapshot_service,         profile_id),
        _run_step("post_insights_service",    run_post_insights_service,    profile_id),
        _run_step("comments_service",         run_comments_service,         profile_id),
        _run_step("engagement_service",       run_engagement_service,       profile_id),
        _run_step("video_metrics_service",    run_video_metrics_service,    profile_id),
    ]

    errors = [s for s in steps if s["status"] == "error"]
    overall_status = "partial" if errors else "ok"

    logger.info(f"[collect/initial] Concluído — {len(steps) - len(errors)}/{len(steps)} steps ok")

    return {
        "status": overall_status,
        "profile_id": profile_id,
        "steps": steps,
        "message": f"Coleta completa: {len(steps) - len(errors)}/{len(steps)} etapas concluídas com sucesso.",
    }


@router.post(
    "/refresh",
    summary="Atualização rápida (sem redescoberta de posts)",
    description=(
        "Executa apenas as etapas de atualização de dados existentes: "
        "snapshot → insights de posts → métricas de engajamento → métricas de vídeo. "
        "Não redescobre posts novos. Use para atualizar dados de forma recorrente "
        "entre execuções do Airflow."
    ),
)
async def collect_refresh(profile_id: str = Depends(get_authenticated_profile)):
    """
    Atualização rápida — apenas dados recentes, sem redescoberta de posts.

    Indicado para execuções recorrentes. O Airflow (dag_instagram_etl) faz
    a mesma coisa automaticamente @daily — este endpoint é para atualizações manuais.
    """
    logger.info(f"[collect/refresh] Iniciando atualização rápida para profile_id={profile_id}")

    steps = [
        _run_step("snapshot_service",         run_snapshot_service,         profile_id),
        _run_step("post_insights_service",    run_post_insights_service,    profile_id),
        _run_step("engagement_service",       run_engagement_service,       profile_id),
        _run_step("video_metrics_service",    run_video_metrics_service,    profile_id),
    ]

    errors = [s for s in steps if s["status"] == "error"]
    overall_status = "partial" if errors else "ok"

    logger.info(f"[collect/refresh] Concluído — {len(steps) - len(errors)}/{len(steps)} steps ok")

    return {
        "status": overall_status,
        "profile_id": profile_id,
        "steps": steps,
        "message": f"Atualização: {len(steps) - len(errors)}/{len(steps)} etapas concluídas com sucesso.",
    }
