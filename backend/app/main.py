import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.logging_config import configure_logging
from app.database import Base, SessionLocal, engine, get_db
from app.models import DetectionRule, Integration, User
from app.routes import router
from app.security import hash_password


configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.service_role in {"ingestion", "assistant"}:
        yield
        return
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if not db.query(User).first():
            db.add_all([
                User(username="admin", password_hash=hash_password("DemoAdmin!2026"), role="admin"),
                User(username="analyst", password_hash=hash_password("DemoAnalyst!2026"), role="analyst"),
                User(username="manager", password_hash=hash_password("DemoManager!2026"), role="soc_manager"),
            ])
        if not db.query(DetectionRule).first():
            db.add(DetectionRule(key="auth-failure-burst", name="Rafale d’échecs d’authentification", event_type="auth_failure",
                                 threshold=3, window_minutes=15, severity="high", enabled=True))
        if not db.query(Integration).first():
            db.add_all([
                Integration(key="edr-sim", name="EDR synthétique", kind="event-source", mode="simulated", enabled=True),
                Integration(key="iam-sim", name="Identité synthétique", kind="event-source", mode="simulated", enabled=True),
                Integration(key="intel-offline", name="Threat intel hors ligne", kind="enrichment", mode="offline", enabled=True),
            ])
        db.commit()
    yield

app = FastAPI(
    title="Sentinel SOC API",
    version="1.0.0",
    description="Plateforme SOC d’apprentissage: événements synthétiques et réponses simulées.",
    lifespan=lifespan,
)

if settings.otel_enabled:
    from app.telemetry import instrument_api

    instrument_api(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

# One image, independently deployed HTTP services; authorization stays centralized.
service_tags = {"ingestion": {"ingestion", "demo"}, "assistant": {"assistant"}}
if settings.service_role != "all":
    allowed = service_tags.get(settings.service_role)
    router.routes = [route for route in router.routes
                     if (bool(set(route.tags) & allowed) if allowed is not None
                         else not set(route.tags) & {"ingestion", "demo", "assistant"})]
app.include_router(router)
request_times: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def local_rate_limit(request: Request, call_next):
    if request.url.path not in {"/health", "/ready", "/metrics", "/openapi.json", "/docs"}:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        history = request_times[client]
        while history and now - history[0] > 60:
            history.popleft()
        if len(history) >= settings.rate_limit_per_minute:
            return JSONResponse(status_code=429, content={"detail": "Limite de requêtes dépassée"}, headers={"Retry-After": "60"})
        history.append(now)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": f"sentinel-{settings.service_role}"}


@app.get("/ready", tags=["health"])
def ready(db=Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        if not db.query(User.id).first():
            raise HTTPException(status_code=503, detail="Database is not initialized")
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready", "database": "ok"}
