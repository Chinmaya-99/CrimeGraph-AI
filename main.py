import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_base.database import init_db
from routes.fir_route import router as fir_router
from routes.graph_route import router as graph_router
from routes.auth_route import router as auth_router
from services.auth import ensure_bootstrap_admin


app = FastAPI(
    title="SIH26189 - Criminal Network Analysis System"
)


CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "*").split(",")
    if origin.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(fir_router)
app.include_router(graph_router)
app.include_router(auth_router)


@app.on_event("startup")
def startup():
    init_db()
    ensure_bootstrap_admin()


@app.get("/")
async def root():
    return {
        "message": "backend is running."
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }