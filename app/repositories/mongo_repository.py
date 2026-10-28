"""
Repositório central do MongoDB para o projeto Instagram Analytics ELT.

Este módulo é o único ponto de contato entre os services Python e o MongoDB Atlas.
Todos os services importam `mongo_repo` daqui — nunca instanciam MongoClient diretamente.

Arquitetura ELT — todas as camadas ficam no mesmo banco, separadas por collection:
  - Extract+Load (dados brutos da API): ig_profiles, profile_snapshots, profile_insights,
    posts, post_snapshots, post_insights, comments
  - Transform (dados derivados, calculados a partir das coleções brutas):
    engagement_metrics, audience_qualification
  - Exceção conhecida: growth_service grava o campo derivado `growth` dentro de
    profile_snapshots (coleção bruta). Melhoria futura: mover para `growth_metrics`.
    Detalhes na docstring de app/services/growth_service.py.

Nomenclatura das collections:
  'ig_profiles'           ->  perfis Instagram conectados
  'profile_snapshots'     ->  série temporal diária do perfil (+ campo derivado `growth`, ver exceção)
  'profile_insights'      ->  métricas semanais + dados demográficos
  'posts'                 ->  metadados imutáveis de posts
  'post_snapshots'        ->  série temporal diária de posts
  'post_insights'         ->  métricas acumuladas lifetime de posts
  'comments'              ->  comentários e replies embutidas
  'engagement_metrics'    ->  calculadas pelo Transform ELT (engagement_service)
  'audience_qualification'->  IQA calculado pelo qualification_service
  'oauth_tokens'          ->  tokens de acesso OAuth

Collections e seus índices:

    ig_profiles             -> profile_id (unique), username, is_active
    profile_snapshots       -> (profile_id, date) unique
    posts                   -> post_id (unique), profile_id, published_at
    post_snapshots          -> (post_id, date) unique
    post_insights           -> (post_id, collected_at) - série temporal acumulada
    comments                -> comment_id (unique), post_id, profile_id
    profile_insights        -> (profile_id, period_until) unique
    engagement_metrics      -> (post_id, date) unique, profile_id, date
    audience_qualification  -> (profile_id, calculated_date) unique
    oauth_tokens            -> profile_id (unique), long_lived_token (unique), is_valid

Nota sobre inicialização:
    O singleton `mongo_repo` usa lazy initialization via _LazyProxy.
    A conexão com o MongoDB só é estabelecida na primeira chamada a uma collection,
    não no import do módulo. Isso evita que o Airflow falhe ao carregar DAGs
    quando o MongoDB Atlas estiver temporariamente indisponível.
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure
from app.config.settings import settings

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class MongoRepository:
    """
    Repositório central do MongoDB.

    Instanciado uma vez como singleton global (`mongo_repo`).
    Os services usam as properties para acessar as collections.
    """

    def __init__(self):
        self.client = MongoClient(settings.MONGO_URI)
        self.db = self.client[settings.DB_NAME]

        try:
            self.client.admin.command("ping")
            logger.info("MongoDB conectado com sucesso.")
        except ConnectionFailure as e:
            logger.error(f"Falha ao conectar no MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"Erro inesperado ao conectar no MongoDB: {e}")
            raise

    # ─── OAuth ───────────────────────────────────────────────────────────────

    @property
    def oauth_tokens(self):
        """Tokens de acesso OAuth — gerenciados pelo oauth_service."""
        return self.db["oauth_tokens"]

    # ─── Extract layer ────────────────────────────────────────────────────────

    @property
    def ig_profiles(self):
        """
        Perfis Instagram conectados via OAuth.
        Criado no login com dados básicos; enriquecido pelo profile_service DAG.

        Nomenclatura: 'ig_profiles'
        """
        return self.db["ig_profiles"]

    @property
    def profile_snapshots(self):
        """
        Série temporal diária do perfil (followers, following, media_count).
        Escrito pelo snapshot_service. Índice único: (profile_id, date).

        Exceção ELT: o growth_service (Transform) também escreve aqui, no campo
        `growth`. Melhoria futura: mover para uma collection `growth_metrics`.
        """
        return self.db["profile_snapshots"]

    @property
    def posts(self):
        """
        Metadados imutáveis dos posts. Write-once na descoberta.
        Escrito pelo media_discovery_service.
        """
        return self.db["posts"]

    @property
    def post_snapshots(self):
        """
        Série temporal diária de performance de cada post.
        Escrito pelo snapshot_service. Índice único: (post_id, date).
        """
        return self.db["post_snapshots"]

    @property
    def post_insights(self):
        """
        Métricas acumuladas (lifetime) de posts via API de Insights.
        Escrito pelo insights_service. Append-only.
        """
        return self.db["post_insights"]

    @property
    def comments(self):
        """
        Comentários e replies embutidas.
        Escrito pelo comments_service. Insert-only.
        Atualizado pelo sentiment_service.
        """
        return self.db["comments"]

    @property
    def profile_insights(self):
        """
        Métricas semanais de perfil + dados demográficos da audiência.
        Escrito pelo insights_service.
        """
        return self.db["profile_insights"]

    # ─── Transform layer ──────────────────────────────────────────────────────

    @property
    def engagement_metrics(self):
        """
        Métricas calculadas de engajamento (er_simple, er_reach, velocity, etc.).
        NÃO vem da API — é calculada pelo engagement_service.
        Ref: Cruz & Santos (2026); Kim et al. (2020); Hootsuite (er_views)
        """
        return self.db["engagement_metrics"]

    @property
    def audience_qualification(self):
        """
        IQA (Índice de Qualidade de Audiência) por perfil e data.
        Calculado pelo qualification_service com base nos engagement_metrics.
        Porta a metodologia validada no TCC para dados reais em tempo real.
        Índice único: (profile_id, calculated_date).
        """
        return self.db["audience_qualification"]

    # ─── Index Management ─────────────────────────────────────────────────────

    def create_indexes(self):
        """
        Cria todos os índices das collections do projeto.
        Índices compostos únicos = garantia se um DAG rodar duas vezes no mesmo dia, o upsert não cria duplicatas.
        Seguro chamar repetidamente — MongoDB ignora índices já existentes.
        """

        # --- oauth_tokens ---
        self.oauth_tokens.create_index([("profile_id", ASCENDING)], unique=True)
        self.oauth_tokens.create_index([("long_lived_token", ASCENDING)], unique=True)
        self.oauth_tokens.create_index([("is_valid", ASCENDING)])

        # --- ig_profiles ---
        self.ig_profiles.create_index([("profile_id", ASCENDING)], unique=True)
        self.ig_profiles.create_index([("username", ASCENDING)])
        self.ig_profiles.create_index([("is_active", ASCENDING)])

        # --- profile_snapshots ---
        # Índice composto único: UM snapshot por perfil por dia
        self.profile_snapshots.create_index(
            [("profile_id", ASCENDING), ("date", ASCENDING)],
            unique=True,
            name="profile_snapshots_profile_date_unique",
        )
        # Índice para queries de série temporal (buscar por período)
        self.profile_snapshots.create_index(
            [("profile_id", ASCENDING), ("date", DESCENDING)],
            name="profile_snapshots_profile_date_desc",
        )

        # --- posts ---
        self.posts.create_index([("post_id", ASCENDING)], unique=True)
        self.posts.create_index([("profile_id", ASCENDING)])
        self.posts.create_index(
            [("profile_id", ASCENDING), ("published_at", DESCENDING)],
            name="posts_profile_published_at",
        )
        self.posts.create_index([("caption", "text")], name="posts_caption_text")

        # --- post_snapshots ---
        # Índice composto único: UM snapshot por post por dia
        self.post_snapshots.create_index(
            [("post_id", ASCENDING), ("date", ASCENDING)],
            unique=True,
            name="post_snapshots_post_date_unique",
        )
        self.post_snapshots.create_index(
            [("profile_id", ASCENDING), ("date", ASCENDING)],
            name="post_snapshots_profile_date",
        )

        # --- post_insights ---
        # Append-only — sem índice único
        self.post_insights.create_index([("post_id", ASCENDING)])
        self.post_insights.create_index(
            [("post_id", ASCENDING), ("collected_at", DESCENDING)],
            name="post_insights_post_collected_at",
        )

        # --- comments ---
        self.comments.create_index([("comment_id", ASCENDING)], unique=True)
        self.comments.create_index([("post_id", ASCENDING)])
        self.comments.create_index([("profile_id", ASCENDING)])
        # Índice sparse para sentiment_service encontrar comentários não processados
        self.comments.create_index(
            [("sentiment_score", ASCENDING)],
            sparse=True,
            name="comments_sentiment_score_sparse",
        )

        # --- profile_insights ---
        # Único por perfil + período (evita duplicar a mesma semana)
        self.profile_insights.create_index(
            [("profile_id", ASCENDING), ("period_until", ASCENDING)],
            unique=True,
            name="profile_insights_profile_period_unique",
        )

        # --- engagement_metrics ---
        # Único por post + dia
        self.engagement_metrics.create_index(
            [("post_id", ASCENDING), ("date", ASCENDING)],
            unique=True,
            name="engagement_metrics_post_date_unique",
        )
        self.engagement_metrics.create_index(
            [("profile_id", ASCENDING), ("date", DESCENDING)],
            name="engagement_metrics_profile_date_desc",
        )

        # --- audience_qualification ---
        # Único por perfil + data de cálculo (idempotência dos DAGs)
        self.audience_qualification.create_index(
            [("profile_id", ASCENDING), ("calculated_date", ASCENDING)],
            unique=True,
            name="audience_qualification_profile_date_unique",
        )
        # Índice para buscar a qualificação mais recente de um perfil
        self.audience_qualification.create_index(
            [("profile_id", ASCENDING), ("calculated_date", DESCENDING)],
            name="audience_qualification_profile_date_desc",
        )

        logger.info("Todos os índices criados/verificados com sucesso.")


# ─── Lazy Singleton ───────────────────────────────────────────────────────────
# A instância só é criada na primeira chamada a uma collection, não no import.
# Isso evita que o Airflow falhe ao carregar os DAGs quando o MongoDB Atlas
# estiver temporariamente indisponível (ex: cold start, variável de ambiente
# não configurada no ambiente de testes).

_mongo_repo_instance: "MongoRepository | None" = None


def get_mongo_repo() -> MongoRepository:
    """Retorna o singleton do MongoRepository, inicializando-o na primeira chamada."""
    global _mongo_repo_instance
    if _mongo_repo_instance is None:
        _mongo_repo_instance = MongoRepository()
        _mongo_repo_instance.create_indexes()
    return _mongo_repo_instance


class _LazyProxy:
    """
    Proxy transparente para MongoRepository.
    Permite que os services façam `from app.repositories.mongo_repository import mongo_repo`
    sem alterar nenhuma chamada existente, enquanto a conexão é feita de forma lazy.
    """
    def __getattr__(self, name: str):
        return getattr(get_mongo_repo(), name)


mongo_repo = _LazyProxy()