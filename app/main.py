from fastapi import FastAPI
from dotenv import load_dotenv

from app.api.routes.webhooks import router as webhooks_router

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

# Criar aplicativo FastAPI
app = FastAPI(
    title="Instagram Analytics API",
    description="API para análise de audiência em perfis do Instagram",
    version="0.0.1"
)

# Registrar rotas de webhook
app.include_router(webhooks_router)