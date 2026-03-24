"""
Transform Service 2.3 — sentiment_service

Aplica a biblioteca `pysentimiento` (Modelo BERT treinado em PT-BR e outras linguagens virtuais) para analisar comentários não processados da base.
Gera uma polaridade contínua (-1.0 a 1.0) para cada comentário e depois agrega a média desse sentimento no documento de `engagement_metrics` de cada post afetado.

Requisito de dependência: 
pip install pysentimiento torch transformers emoji
"""

import logging
from datetime import datetime, timezone
import math

from pymongo import UpdateOne, UpdateMany
from pymongo.errors import BulkWriteError

from app.repositories.mongo_repository import mongo_repo

logger = logging.getLogger(__name__)

# Variável global para cachear o modelo gigantesco na memória durante a execução em lote
_analyzer = None

def get_analyzer():
    """Lazy load do modelo RoBERTa do pysentimiento para poupar memória se o serviço não for chamado."""
    global _analyzer
    if _analyzer is None:
        try:
            from pysentimiento import create_analyzer
            logger.info("[sentiment_service] Carregando modelo NLP pysentimiento (pt)... (Isso pode demorar na primeira vez)")
            _analyzer = create_analyzer(task="sentiment", lang="pt")
        except ImportError:
            logger.error("[sentiment_service] pysentimiento não instalado. Execute: pip install pysentimiento")
            raise
    return _analyzer


def _calculate_continuous_score(probas: dict) -> float:
    """
    Converte as probabilidades (POS, NEG, NEU) em um score linear único de -1.0 a 1.0.
    Fórmula: p(POS) - p(NEG)
    """
    pos = probas.get("POS", 0.0)
    neg = probas.get("NEG", 0.0)
    # neu = probas.get("NEU", 0.0) - Neutro atrai o score pro centro 0.0 indiretamente
    
    return float(pos - neg)


def run_sentiment_service(profile_id: str = None, limit: int = 500) -> dict:
    """
    Busca comentários ainda não pontuados (onde sentiment_score não existe),
    aplica IA neles e depois re-calcula o sentimento médio dos posts afetados.
    
    Se profile_id for passado, filtra os posts do perfil (via junção na layer app),
    senão processa os primeiros `limit` comentários de qualquer perfil.
    """
    logger.info("[sentiment_service] Iniciando processamento de NLP nos comentários pendentes...")
    
    # Monta query de comentários pendentes. Se houver profile_id, precisamos dos post_ids
    query = {"sentiment_score": {"$exists": False}}
    post_ids_affected = set()
    
    if profile_id:
        posts = list(mongo_repo.posts.find({"profile_id": profile_id}, {"post_id": 1}))
        if not posts:
            return {"status": "ok", "processed": 0, "message": "Nenhum post do perfil."}
            
        profile_post_ids = [p["post_id"] for p in posts]
        query["post_id"] = {"$in": profile_post_ids}

    # Busca em batch
    pending_comments = list(mongo_repo.comments.find(query).limit(limit))
    
    if not pending_comments:
        return {
            "status": "ok", "processed": 0, 
            "message": "Nenhum comentário pendente de análise de sentimento no momento."
        }

    # Carrega Analisador (apenas se houver comentários)
    analyzer = get_analyzer()
    
    operations = []
    
    for c in pending_comments:
        comment_id = c["id"]
        post_id = c.get("post_id")
        text = c.get("text", "")
        
        if not text.strip():
            # Texto vazio, classifica neutral absoluto
            score = 0.0
            label = "NEU"
        else:
            try:
                # Usa max_length pra prevenir crash com comentários gigantes (spam)
                result = analyzer.predict(text)
                label = result.output
                score = _calculate_continuous_score(result.probas)
            except Exception as e:
                logger.error(f"[sentiment_service] Erro inferindo comentário {comment_id}: {e}")
                continue
                
        # Bulk para atualizar o comentário com a nota
        operations.append(
            UpdateOne(
                {"id": comment_id},
                {"$set": {
                    "sentiment_score": round(score, 4),
                    "sentiment_label": label,
                    "sentiment_analyzed_at": datetime.now(timezone.utc)
                }}
            )
        )
        if post_id:
            post_ids_affected.add(post_id)

    # Executa Bulk dos Comentários
    if operations:
        try:
            res = mongo_repo.comments.bulk_write(operations, ordered=False)
            logger.info(f"[sentiment_service] {res.modified_count} comentários atualizados com NLP.")
        except BulkWriteError as e:
            logger.error(f"[sentiment_service] Erro bulk update comments: {e.details}")

    # Aggregation para re-calcular o sentimento médio por Post
    post_operations = []
    if post_ids_affected:
        pipeline = [
            {"$match": {"post_id": {"$in": list(post_ids_affected)}, "sentiment_score": {"$exists": True}}},
            {"$group": {
                "_id": "$post_id",
                "avg_sentiment": {"$avg": "$sentiment_score"},
                "scored_comments": {"$sum": 1}
            }}
        ]
        
        agg_results = list(mongo_repo.comments.aggregate(pipeline))
        for res in agg_results:
            pid = res["_id"]
            avg_score = res["avg_sentiment"]
            
            # Atualiza todos os registros históricos deste post_id em engagement_metrics
            post_operations.append(
                UpdateMany(
                    {"post_id": pid},
                    {"$set": {"avg_sentiment_score": round(avg_score, 4)}}
                )
            )
            
    # Para ser compatível com a modelagem do arquivo mongo_repository sem lock complexo:
    if post_operations:
         try:
            # Executamos o aggregate update na collection "engagement_metrics"
            mongo_repo.engagement_metrics.bulk_write(post_operations, ordered=False)
            logger.info(f"[sentiment_service] Sentimento médio consolidado para {len(post_operations)} posts em engagement_metrics.")
         except BulkWriteError as e:
             logger.error(f"[sentiment_service] Erro agregando em posts: {e.details}")

    return {
        "status": "ok", 
        "processed": len(operations), 
        "posts_affected": len(post_ids_affected),
        "message": f"{len(operations)} comentários analisados via pysentimiento."
    }
