import uvicorn
import logging
from dotenv import load_dotenv

load_dotenv()

from app.config import settings

logger = logging.getLogger("stock_intelligence.launcher")

if __name__ == "__main__":
    logger.info(f"Launching Stock Intelligence Platform from root on {settings.host}:{settings.port}")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
