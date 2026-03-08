from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    "https://socialdatalab.vercel.app",  # produção
    "http://localhost:3000",
    "http://localhost:8000",   # desenvolvimento local
    "https://www.socialdatalab.online", # produção
    "https://socialdatalab.online", # produção
]

def configure_cors(app):
    """Registra o middleware de CORS no app FastAPI."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
