"""app/api/router.py — aggregates all route modules"""
from fastapi import APIRouter
from app.api.routes.vegetation import router as veg_router

api_router = APIRouter()
api_router.include_router(veg_router)
