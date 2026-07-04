"""FastAPI приложение — точка входа uvicorn."""

from app.api import create_app

app = create_app()
