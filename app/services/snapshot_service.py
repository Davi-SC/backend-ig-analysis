"""
Servico e análise e processamento dos snapshots
"""


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

