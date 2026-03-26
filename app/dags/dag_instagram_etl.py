"""
DAG: dag_instagram_etl

Orquestra o pipeline ETL de coleta (Extract) e transformações de posts (Transform) para dados Instagram.

Fluxo de execução (bitshift >>):

    [EXTRACT]
    extract_profile
        >> extract_media_discovery
        >> extract_snapshot
        >> extract_post_insights
        >> extract_comments

    [TRANSFORM — métricas de posts]  ← só inicia após toda a cadeia de extração
        >> transform_engagement
        >> transform_video_metrics
        >> transform_sentiment

Nota: transform_growth e loyaty_rate são responsabilidade do dag_weekly_insights,
pois dependem de profile_insights (account-level) que é coletado semanalmente.

Cada task delega para o respectivo run_*_service(profile_id),passando profile_id via Airflow Variable "ig_profile_id".

Configuração:
    - AIRFLOW_VAR_IG_PROFILE_ID : profile_id do usuário Instagram a processar
    - AIRFLOW_CONN_MONGO_DEFAULT : URI de conexão MongoDB (usado pelos services)

Agendamento:
    schedule_interval = "@daily"
    start_date        = datetime(2025, 1, 1)
    catchup           = False
"""

import logging
from datetime import datetime

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

# Import dos serviços ETL
from app.services.profile_service import run_profile_service
from app.services.media_discovery_service import run_media_discovery_service
from app.services.snapshot_service import run_snapshot_service
from app.services.insights_service import run_post_insights_service
from app.services.comments_service import run_comments_service
from app.services.engagement_service import run_engagement_service
from app.services.video_metrics_service import run_video_metrics_service
from app.services.sentiment_service import run_sentiment_service

logger = logging.getLogger(__name__)

# Configuração central
DAG_ID = "dag_instagram_etl"
SCHEDULE_INTERVAL = "@daily"
START_DATE = datetime(2025, 1, 1)
CATCHUP = False                        # não reprocessa dias/semanas anteriores
DEFAULT_ARGS = {
    "owner": "etl",
    "retries": 1,
    "retry_delay_seconds": 300,        # 5 min entre tentativas
    "email_on_failure": False,
}

# Helpers — wrappers que lêem profile_id do Airflow Variables

def _get_profile_id() -> str:
    """
    Lê o profile_id da Airflow Variable 'ig_profile_id'.
    Lança ValueError se não estiver configurada, fazendo a task falhar de forma clara antes de tentar qualquer chamada à API.
    """
    profile_id = Variable.get("ig_profile_id", default_var=None)
    if not profile_id:
        raise ValueError(
            "Airflow Variable 'ig_profile_id' não configurada. "
            "Acesse Admin > Variables e adicione a chave 'ig_profile_id'."
        )
    return profile_id


def _log_result(service_name: str, result: dict) -> None:
    """Loga o resultado de um service e levanta exceção se status == 'error'."""
    if result.get("status") == "error":
        raise RuntimeError(
            f"[{service_name}] falhou: {result.get('message', 'erro desconhecido')}"
        )
    logger.info(f"[{service_name}] concluído: {result}")


# Funções de task — uma por service

def task_fn_profile(**context):
    profile_id = _get_profile_id()
    result = run_profile_service(profile_id=profile_id)
    _log_result("profile_service", result)


def task_fn_media_discovery(**context):
    profile_id = _get_profile_id()
    result = run_media_discovery_service(profile_id=profile_id)
    _log_result("media_discovery_service", result)


def task_fn_snapshot(**context):
    """
    Passa data de execução do Airflow como target_date para snapshot.
    Isso garante que, mesmo rodando semanalmente, o snapshot registra a data correta do período de coleta.
    """
    profile_id = _get_profile_id()
    execution_date = context["data_interval_end"].date()
    result = run_snapshot_service(profile_id=profile_id, target_date=execution_date)
    _log_result("snapshot_service", result)


def task_fn_post_insights(**context):
    profile_id = _get_profile_id()
    result = run_post_insights_service(profile_id=profile_id)
    _log_result("post_insights_service", result)


def task_fn_comments(**context):
    profile_id = _get_profile_id()
    result = run_comments_service(profile_id=profile_id)
    _log_result("comments_service", result)


def task_fn_engagement(**context):
    """
    Usa data_interval_end como target_date para calcular métricas do período correto, independente da frequência do schedule.
    """
    profile_id = _get_profile_id()
    target_date = context["data_interval_end"].date()
    result = run_engagement_service(profile_id=profile_id, target_date=target_date)
    _log_result("engagement_service", result)


def task_fn_video_metrics(**context):
    profile_id = _get_profile_id()
    target_date = context["data_interval_end"].date()
    result = run_video_metrics_service(profile_id=profile_id, target_date=target_date)
    _log_result("video_metrics_service", result)


def task_fn_sentiment(**context):
    """
    Processa TODOS os comentários sem score do perfil.
    Não usa target_date: o serviço já filtra por índice sparse (sem sentiment_score).
    """
    profile_id = _get_profile_id()
    result = run_sentiment_service(profile_id=profile_id)
    _log_result("sentiment_service", result)


# Definição do DAG
with DAG(
    dag_id=DAG_ID,
    schedule_interval=SCHEDULE_INTERVAL,
    start_date=START_DATE,
    catchup=CATCHUP,
    default_args=DEFAULT_ARGS,
    tags=["instagram", "etl", "extract", "transform"],
    doc_md=__doc__,
) as dag:

    # ------ EXTRACT ------
    t_profile = PythonOperator(
        task_id="extract_profile",
        python_callable=task_fn_profile,
    )

    t_media_discovery = PythonOperator(
        task_id="extract_media_discovery",
        python_callable=task_fn_media_discovery,
    )

    t_snapshot = PythonOperator(
        task_id="extract_snapshot",
        python_callable=task_fn_snapshot,
    )

    t_post_insights = PythonOperator(
        task_id="extract_post_insights",
        python_callable=task_fn_post_insights,
    )

    t_comments = PythonOperator(
        task_id="extract_comments",
        python_callable=task_fn_comments,
    )

    # ------ TRANSFORM ------
    t_engagement = PythonOperator(
        task_id="transform_engagement",
        python_callable=task_fn_engagement,
    )

    t_video_metrics = PythonOperator(
        task_id="transform_video_metrics",
        python_callable=task_fn_video_metrics,
    )

    t_sentiment = PythonOperator(
        task_id="transform_sentiment",
        python_callable=task_fn_sentiment,
    )

    # Dependências (pipeline linear)
    # transform_growth está no dag_weekly_insights (requer profile_insights account-level)
    (
        t_profile
        >> t_media_discovery
        >> t_snapshot
        >> t_post_insights
        >> t_comments
        >> t_engagement
        >> t_video_metrics
        >> t_sentiment
    )
