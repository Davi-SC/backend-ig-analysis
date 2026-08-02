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
    title="Instagram Analytics API",
    description=(
        "API para coleta, processamento e análise de dados de perfis Instagram. "
        "Autenticação via header **X-Profile-ID** (retornado após o login OAuth)."
    ),
    version="1.0.0",
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