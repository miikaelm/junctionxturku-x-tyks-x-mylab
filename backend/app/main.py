import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.alerts import engine
from app.api.cds import router as cds_router
from app.api.routes import router
from app.data.store import get_store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load the data and run the detectors in the background so the first page is fast.
    threading.Thread(
        target=lambda: engine.warm(get_store().dataset, get_store().today()), daemon=True
    ).start()
    yield


app = FastAPI(title="AEI – Antibiotic Efficacy Indicator", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(cds_router)
