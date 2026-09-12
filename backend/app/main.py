import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import api_v1_router
from app.core.config import settings
from app.services.ml_service import ml_service
from app.services.mqtt_service import mqtt_service

logger = logging.getLogger("hydrasense.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load ML models safely (verify artifacts + feature contracts).
    # Never retrains; a missing artifact marks ML unavailable — ingestion
    # continues and readings keep NULL ML fields (no fabricated results).
    logger.info("Starting HydraSense Phase 6 API: loading ML models...")
    try:
        if ml_service.load_models():
            logger.info("ML service available (Isolation Forest + Random Forest).")
        else:
            logger.warning(
                "ML service UNAVAILABLE — telemetry ingestion continues "
                "without ML results; no fabricated predictions will be stored."
            )
    except Exception as err:
        logger.error(f"ML model startup error: {err}")

    # Startup: connect MQTT subscriber cleanly
    logger.info("Starting HydraSense Phase 4 API and initializing MQTT subscriber...")
    try:
        mqtt_service.start()
    except Exception as err:
        logger.error(f"MQTT subscriber startup error: {err}")
    
    yield
    
    # Shutdown: stop MQTT loop and disconnect
    logger.info("Shutting down HydraSense API and stopping MQTT subscriber...")
    try:
        mqtt_service.stop()
    except Exception as err:
        logger.error(f"MQTT subscriber shutdown error: {err}")


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-Powered Water Quality Intelligence and Predictive Response System - Phase 4 API",
    version="0.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Enable CORS for local development and frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api")


@app.get("/")
def root():
    return {
        "status": "online",
        "project": "HydraSense",
        "phase": 4,
        "description": "AI-Powered Water Quality Intelligence and Predictive Response System",
        "docs": "/docs"
    }

