import logging
import re
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.dbcheck import explain, redact, run_check
from app.core.errors import DomainError
from app.modules.audit.router import router as audit_router
from app.modules.catalogue.router import router as catalogue_router
from app.modules.consignment.router import router as consignment_router
from app.modules.customers.router import router as customers_router
from app.modules.identity.router import router as identity_router
from app.modules.inventory.router import router as inventory_router
from app.modules.invoicing.router import router as invoicing_router
from app.modules.partner.router import router as partner_router
from app.modules.pilot.router import router as pilot_router
from app.modules.platform.router import router as platform_router
from app.modules.proofs.router import router as proofs_router
from app.modules.purchasing.router import router as purchasing_router
from app.modules.replenishment.router import router as replenishment_router
from app.modules.reporting.router import router as reporting_router
from app.modules.sales.router import router as sales_router
from app.modules.search.router import router as search_router
from app.modules.stock_requests.router import notifications_router
from app.modules.stock_requests.router import router as stock_requests_router
from app.modules.stocktakes.router import router as stocktakes_router
from app.modules.transfers.router import router as transfers_router

log = logging.getLogger("app")

# Release version (see RELEASE_NOTES.md); shown by /api/health.
APP_VERSION = "1.11.0"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=f"{settings.app_display_name} API", version=APP_VERSION, openapi_url="/api/openapi.json",
                  docs_url="/api/docs", redoc_url=None)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, exc: IntegrityError):
        # Constraint backstops (e.g. available stock never negative) surface as conflicts.
        log.warning("Integrity error: %s", exc.orig)
        return JSONResponse(status_code=409, content={
            "detail": "The operation conflicts with current data (a database constraint was violated)",
            "code": "constraint_violation",
        })

    @app.exception_handler(OperationalError)
    async def operational_error(_: Request, exc: OperationalError):
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate in ("40001", "40P01"):  # serialization failure / deadlock
            return JSONResponse(status_code=409, content={
                "detail": "A concurrent update conflicted with this request; please retry", "code": "retry",
            })
        return _database_failure(exc)

    @app.exception_handler(DBAPIError)
    async def dbapi_error(_: Request, exc: DBAPIError):
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate in ("40001", "40P01"):
            return JSONResponse(status_code=409, content={
                "detail": "A concurrent update conflicted with this request; please retry", "code": "retry",
            })
        if sqlstate and sqlstate.startswith("23"):
            return JSONResponse(status_code=409, content={
                "detail": "The operation conflicts with current data", "code": "constraint_violation",
            })
        return _database_failure(exc)

    def _database_failure(exc: DBAPIError) -> JSONResponse:
        log.error("Database error: %s", redact(str(exc.orig)))
        info = explain(exc, settings)
        return JSONResponse(status_code=503, content={"detail": "Database problem: " + info["hint"], **info})

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception):
        log.exception("Unhandled error")
        return JSONResponse(status_code=500, content={
            "detail": "Unexpected server error; see the runtime logs.", "code": "internal_error",
            "error_type": type(exc).__name__,
        })

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": "Invalid request", "code": "validation",
                                                      "errors": jsonable_errors(exc)})

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": f"{settings.app_display_name} API", "health": "/api/health", "docs": "/api/docs"}

    @app.get("/api/health/db", tags=["system"])
    def health_db():
        """Database connectivity, migration and data check (no secrets in the output)."""
        report = run_check(get_engine(), settings)
        return JSONResponse(status_code=200 if report["status"] != "error" else 503, content=report)

    @app.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok", "name": settings.app_display_name, "env": settings.app_env, "version": APP_VERSION}

    for r in (identity_router, catalogue_router, customers_router, consignment_router, inventory_router,
              purchasing_router, sales_router, replenishment_router, transfers_router, stocktakes_router,
              invoicing_router, reporting_router, audit_router, pilot_router, stock_requests_router, notifications_router,
              proofs_router, partner_router, search_router, platform_router):
        app.include_router(r, prefix="/api")
    return app


def jsonable_errors(exc: RequestValidationError) -> list[dict]:
    out = []
    for err in exc.errors():
        out.append({"loc": list(err.get("loc", [])), "msg": err.get("msg", ""), "type": err.get("type", "")})
    return out


def _startup_error_app(exc: Exception) -> FastAPI:
    """Fallback when configuration is invalid: answer every request with the reason (secrets redacted).

    Without this, a serverless host only reports an opaque invocation failure.
    """
    reason = re.sub(r"input_value=[^\]\n]*", "input_value=<hidden>", f"{type(exc).__name__}: {exc}")
    body = {
        "status": "error",
        "detail": "The API could not start. Check the environment variables, then redeploy.",
        "reason": reason,
    }
    fallback = FastAPI(title="API (startup error)", openapi_url=None, docs_url=None, redoc_url=None)

    @fallback.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
    def startup_error(path: str):
        return JSONResponse(status_code=500, content=body)

    return fallback


def build_app() -> FastAPI:
    try:
        return create_app()
    except Exception as exc:  # configuration errors (e.g. weak JWT_SECRET in staging/production)
        log.error("API startup failed:\n%s", traceback.format_exc())
        return _startup_error_app(exc)


# Must stay a plain top-level assignment: Vercel statically checks app/main.py for a top-level "app".
app = build_app()
