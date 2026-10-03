"""Hosting entry point: settings validate before the server accepts requests."""
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT,
                log_level=settings.LOG_LEVEL.lower(), reload=False)
