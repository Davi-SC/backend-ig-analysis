"""
Transform Service 2.3 — sentiment_service

Análise de sentimento via NLP nos comentários coletados.

[DESABILITADO] pysentimiento temporariamente desativado — dependência pesada
(pysentimiento + torch + transformers) não incluída no escopo atual.
Para reativar: instale `pip install pysentimiento torch transformers emoji`
e restaure a implementação completa a partir do histórico git.

Interface pública mantida para compatibilidade com os DAGs do Airflow.
"""

import logging

logger = logging.getLogger(__name__)


def run_sentiment_service(profile_id: str = None, limit: int = 500) -> dict:
    """
    [DESABILITADO] pysentimiento temporariamente desativado.

    Para reativar: instale as dependências e substitua este stub pela
    implementação completa (git history preserva a versão original).
    """
    logger.info("[sentiment_service] Serviço desabilitado (pysentimiento). Retornando skipped.")
    return {
        "status": "skipped",
        "processed": 0,
        "posts_affected": 0,
        "message": "pysentimiento desabilitado. Reative instalando: pip install pysentimiento torch transformers emoji",
    }
