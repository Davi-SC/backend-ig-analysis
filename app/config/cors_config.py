from fastapi.middleware.cors import CORSMiddleware

ALLOWED_ORIGINS = [
    "https://socialdatalab.vercel.app",  # produção
    "http://localhost:3000",             # desenvolvimento local
]

def configure_cors(app):
    """Registra o middleware de CORS no app FastAPI."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
