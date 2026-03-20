"""
Serviço de snapshot — fase Extract do ETL.

Responsável por coletar e persistir "fotografias" diárias do estado de
perfis e posts Instagram.

Escopo deste service:
  - account_snapshots: followers, follows, media_count do perfil neste dia
  - post_snapshots:    like_count, comments_count de cada post neste dia

Este módulo será expandido na próxima etapa (Extract Services).
"""

from typing import List
from datetime import date


def calcular_engagement_rate(likes: int, comments: int, followers_count: int) -> float:
    """
    Calcula o engagement rate simples.

    Fórmula: (likes + comments) / followers_count × 100
    """
    if followers_count == 0:
        return 0.0
    return ((likes + comments) / followers_count) * 100.0


def filtrar_posts_por_data(
    post_dates: List[date],
    data_inicial: date,
    data_final: date,
) -> List[date]:
    """
    Filtra uma lista de datas de posts dentro de um intervalo.
    """
    return [d for d in post_dates if data_inicial <= d <= data_final]