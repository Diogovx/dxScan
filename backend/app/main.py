import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.access_log import AccessLogMiddleware
from app.core.config import settings
from app.core.database import Base, engine
from app.core.log_config import setup_logging
from app.models import audit, scanner_data  # noqa: F401 - registers the models on Base.metadata
from app.routes import auth, dashboard, inventory
from app.services.auth import LdapAuthenticator

setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("dxscan")


async def log_directory_status() -> None:
    """Reports at startup whether the AD is reachable. Never blocks startup: scanner ingestion does not need AD."""
    check = await LdapAuthenticator(settings).check_connection()
    if check.ok:
        logger.info("Conexão com o AD ok: %s (%d ms)", settings.LDAP_SERVER_URI, check.elapsed_ms)
    else:
        logger.error(
            "Não foi possível conectar ao AD em %s: %s. O login no dashboard vai falhar até isso ser resolvido.",
            settings.LDAP_SERVER_URI, check.detail,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = settings.missing_auth_settings()
    if missing:
        raise RuntimeError(f"Configuração de autenticação ausente no .env: {', '.join(missing)}")
    if not settings.SCANNER_API_KEY:
        logger.warning("SCANNER_API_KEY vazio: POST /api/v1/inventory/ aceita envios sem autenticação (modo legado).")
    if settings.LDAP_SERVER_URI.lower().startswith("ldap://"):
        logger.warning("LDAP_SERVER_URI usa ldap:// sem TLS: as senhas trafegam em texto puro. Use ldaps://.")
    await log_directory_status()

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

app.include_router(auth.router)
app.include_router(inventory.router)
app.include_router(dashboard.router)


@app.get("/")
async def read_root():
    return {"message": "DXSCAN API is online and ready to receive data!"}
