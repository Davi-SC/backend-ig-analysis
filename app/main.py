from fastapi import FastAPI
from dotenv import load_dotenv

from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.oauth import router as oauth_router
from app.api.routes.collect import router as collect_router
from app.api.routes.data import router as data_router
from app.api.routes.analytics import router as analytics_router
from app.config.cors_config import configure_cors

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Criar aplicativo FastAPI
app = FastAPI(
    title="Instagram Analytics API — PIBIC/IFMA",
    description=(
        "**Pipeline ELT para Qualificação de Audiência em Redes Sociais**\n\n"
        "API desenvolvida como parte da pesquisa PIBIC 2025/2026 no "
        "Instituto Federal do Maranhão (IFMA) — Campus Coelho Neto.\n\n"
        "**Pesquisador:** Davi Silva da Cruz  \n"
        "**Orientador:** Francisco Alan de Oliveira Santos  \n\n"
        "---\n\n"
        "**Resumo do projeto:**  \n"
        "Implementa um processo sistemático de coleta, transformação e qualificação "
        "de dados públicos de perfis Instagram Business via Meta Graph API v25.0. "
        "O **IQA (Índice de Qualidade de Audiência)** combina a mediana da Taxa de "
        "Engajamento (TE) e o Coeficiente de Variação (CV) num score composto [0–1], "
        "classificando o perfil em tiers **A/B/C/D**.\n\n"
        "**Referência metodológica:**  \n"
        "Cruz, D.S.; Santos, F.A.O. (2026). *Indicador Multidimensional para "
        "Qualificação de Audiência de Perfis no Instagram*. TCC — IFMA.\n\n"
        "**Autenticação:** header `X-Profile-ID` (retornado após fluxo OAuth em `/oauth`)."
    ),
    version="1.0.0",
    contact={
        "name": "Davi Silva da Cruz — IFMA Campus Coelho Neto",
        "email": "davi.cruz@academico.ifma.edu.br",
    },
    license_info={
        "name": "Acadêmico — Uso restrito a fins de pesquisa (IFMA/PIBIC)",
    },
)

# Configurar CORS
configure_cors(app)

# ── Rotas OAuth e Webhook (não requerem X-Profile-ID) ──
app.include_router(oauth_router)
app.include_router(webhooks_router)

# ── Rotas de coleta on-demand (requerem X-Profile-ID) ──
app.include_router(collect_router)

# ── Rotas de dados brutos (requerem X-Profile-ID) ──
app.include_router(data_router)

# ── Rotas analíticas (requerem X-Profile-ID) ──
app.include_router(analytics_router)