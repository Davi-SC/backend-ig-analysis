from fastapi import FastAPI
from dotenv import load_dotenv

from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.oauth import router as oauth_router
from app.config.cors_config import configure_cors

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Criar aplicativo FastAPI
app = FastAPI(
    title="Instagram Analytics API",
    description="API para análise de audiência em perfis do Instagram",
    version="0.0.1"
)

# Configurar CORS
configure_cors(app)

# Registrar rotas de webhook
app.include_router(webhooks_router)

# Registrar rotas de OAuth da Meta (Instagram e Facebook)
app.include_router(oauth_router)