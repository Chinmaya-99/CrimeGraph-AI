from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from data_base.database import init_db
from routes.fir_route import router as fir_router
from routes.graph_route import router as graph_router

app = FastAPI(
    title="SIH26189 - Criminal Network Analysis System"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(fir_router)
app.include_router(graph_router)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")

async def root():
    return {"message": "backend is running."}

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }
