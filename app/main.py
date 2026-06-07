from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.firebase import db
from app.routers import users, matches, predictions, ranking
from app.services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar el servidor
    start_scheduler()
    yield
    # Al apagar el servidor
    stop_scheduler()


app = FastAPI(
    title="Polla Mundialista API",
    description="Backend para la plataforma de predicciones del Mundial 2026",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://polla-mundialista-393f8.web.app",
        "https://polla-mundialista-393f8.firebaseapp.com",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(matches.router)
app.include_router(predictions.router)
app.include_router(ranking.router)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "message": "Polla Mundialista API corriendo",
        "scheduler": "activo"
    }