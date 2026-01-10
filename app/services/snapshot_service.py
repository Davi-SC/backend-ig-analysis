"""
Servico e análise e processamento dos snapshots
"""

from typing import List, Dict, Any

from app.domain.schemas.snapshot_schemas import PostData



def calcular_engagement_rate(likes: int, comments:int, followers_count: int) -> float:
    """ 
    Calcula o engajamento com base na formula:
     (likes+comments)/followers_count * 100

    Args: likes, comments e followers_count
    Returns: Taxa de engajamento em porcentage
    """

    if followers_count == 0:
        return 0.0
    return ((likes + comments) / followers_count) * 100.0

def filtrar_posts_por_data(
        posts: List[PostData],
        data_inicial: str,
        data_final: str
) -> List[PostData]:
    """ 
    Filtrar posts por intervalo de datas
    """

    posts_filtrados = []
    for post in posts:
        #Extrair a data do timestamp(exemplo 2025-11-17T18:45:30+0000)
        post_date_str = post.timestamp.split('T')[0]
        if data_inicial <= post_date_str <= data_final:
            posts_filtrados.append(post)

    return posts_filtrados    