from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.public import router as public_router
from app.api.v1.product import router as product_router
from app.api.v1.authority import router as authority_router
from app.api.v1.simulation import router as simulation_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(public_router)
api_v1_router.include_router(product_router)
api_v1_router.include_router(authority_router)
api_v1_router.include_router(simulation_router)

__all__ = ["api_v1_router"]
