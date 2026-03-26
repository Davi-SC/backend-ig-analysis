"""
DAG: dag_weekly_insights

Orquestra o pipeline semanal de métricas de conta e crescimento de perfil Instagram.
Este DAG complementa o dag_instagram_etl, focando nas métricas que fazem sentido numa janela de 7 dias:

  - Coleta de profile insights da Graph API (accounts_engaged, views, reach,
    demographics), que a Meta só disponibiliza com aggregação de período.
  - Cálculo de crescimento de seguidores (7d) e Loyalty Rate, que dependem dos profile_insights coletados acima.
  - Qualificação da audiência — a implementar quandoqualification_service estiver pronto.

Fluxo de execução (bitshift >>):

    [EXTRACT]
    extract_profile_insights

    [TRANSFORM — métricas de perfil]
        >> transform_growth
        >> transform_qualification  (placeholder — ativado quando qualification_service existir)

Pré-requisito: dag_instagram_etl deve ter rodado pelo menos uma vez antes, para que profile_snapshots e posts existam no banco.

Configuração:
    - AIRFLOW_VAR_IG_PROFILE_ID : profile_id do usuário Instagram a processar
    - AIRFLOW_CONN_MONGO_DEFAULT : URI de conexão MongoDB (usado pelos services)
"""

import logging
from datetime import datetime

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator

from app.services.insights_service import run_profile_insights_service
from app.services.growth_service import run_growth_service

logger = logging.getLogger(__name__)

# Configuração central
DAG_ID = "dag_weekly_insights"
SCHEDULE_INTERVAL = "0 4 * * 0"      # domingos às 04:00
START_DATE = datetime(2025, 1, 1)
CATCHUP = False
DEFAULT_ARGS = {
    "owner": "etl",
    "retries": 1,
    "retry_delay_seconds": 300,
    "email_on_failure": False,
}

PROFILE_INSIGHTS_PERIOD_DAYS = 7     # janela de coleta da Graph API

# Helpers
def _get_profile_id() -> str:
    profile_id = Variable.get("ig_profile_id", default_var=None)
    if not profile_id:
        raise ValueError(
            "Airflow Variable 'ig_profile_id' não configurada. "
            "Acesse Admin > Variables e adicione a chave 'ig_profile_id'."
        )
    return profile_id


def _log_result(service_name: str, result: dict) -> None:
    if result.get("status") == "error":
        raise RuntimeError(
            f"[{service_name}] falhou: {result.get('message', 'erro desconhecido')}"
        )
    logger.info(f"[{service_name}] concluído: {result}")


# Funções de task
def task_fn_profile_insights(**context):
    """
    Coleta métricas de conta (reach, accounts_engaged, views, demographics) para a janela de 7 dias encerrada em data_interval_end.
    """
    profile_id = _get_profile_id()
    target_until = context["data_interval_end"].date()
    result = run_profile_insights_service(
        profile_id=profile_id,
        period_days=PROFILE_INSIGHTS_PERIOD_DAYS,
        target_until=target_until,
    )
    _log_result("profile_insights_service", result)


def task_fn_growth(**context):
    """
    Calcula crescimento semanal de seguidores (7d) e Loyalty Rate.

    Depende de:
      - profile_snapshots coletados diariamente pelo dag_instagram_etl
      - profile_insights coletado pela task anterior (extract_profile_insights)
    """
    profile_id = _get_profile_id()
    target_date = context["data_interval_end"].date()
    result = run_growth_service(profile_id=profile_id, target_date=target_date)
    _log_result("growth_service", result)


def task_fn_qualification(**context):
    """
    Placeholder — ativado quando qualification_service estiver implementado (task 2.5).
    """
    logger.info(
        "[qualification_service] Ainda não implementado. "
        "Task reservada para quando qualification_service estiver pronto"
    )
    # from app.services.qualification_service import run_qualification_service
    # profile_id = _get_profile_id()
    # result = run_qualification_service(profile_id=profile_id)
    # _log_result("qualification_service", result)


# Definição do DAG
with DAG(
    dag_id=DAG_ID,
    schedule_interval=SCHEDULE_INTERVAL,
    start_date=START_DATE,
    catchup=CATCHUP,
    default_args=DEFAULT_ARGS,
    tags=["instagram", "etl", "insights", "weekly", "growth"],
    doc_md=__doc__,
) as dag:

    # ------ EXTRACT ------
    t_profile_insights = PythonOperator(
        task_id="extract_profile_insights",
        python_callable=task_fn_profile_insights,
    )

    # ------ TRANSFORM ------
    t_growth = PythonOperator(
        task_id="transform_growth",
        python_callable=task_fn_growth,
    )

    t_qualification = PythonOperator(
        task_id="transform_qualification",
        python_callable=task_fn_qualification,
    )

    # ------ DEPENDÊNCIAS ------
    (
        t_profile_insights
        >> t_growth
        >> t_qualification
    )
