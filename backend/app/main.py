from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.access_log import AccessLogMiddleware
from app.core.database import Base, engine
from app.models import audit, scanner_data  # noqa: F401 - registers the models on Base.metadata
from app.routes import inventory


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_all is a sync API; run_sync executes it on the async connection.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="DXSCAN API",
    description="API for hardware and software inventory collection",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(AccessLogMiddleware)

app.include_router(inventory.router)


@app.get("/")
async def read_root():
    return {"message": "DXSCAN API is online and ready to receive data!"}
