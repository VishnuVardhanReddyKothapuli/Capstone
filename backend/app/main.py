"""FastAPI application: routers, CORS, and static hosting for the built SPA."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import settings
from app.database import init_db
from app.routers import admin, auth, explain, history, meta, moderate

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
)
logger = logging.getLogger("sentinal")

DIST = Path(settings.FRONTEND_DIST)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info("SQL ready; Chroma will persist to %s", settings.CHROMA_PERSIST_DIR)
    if settings.jwt_secret_is_default:
        logger.warning(
            "JWT_SECRET is the built-in development value. Set a random JWT_SECRET in "
            "backend/.env before exposing this service to anyone else."
        )
    elif len(settings.JWT_SECRET.encode()) < 32:
        logger.warning(
            "JWT_SECRET is shorter than the 32 bytes recommended for HMAC-SHA256 "
            "(RFC 7518 3.2). Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    if not settings.gemini_configured:
        logger.info(
            "GEMINI_API_KEY is unset, so verdict explanations are switched off and "
            "POST /api/checks/{id}/explain answers 503."
        )
    # Models stay unloaded until the first check that needs them.
    yield


app = FastAPI(
    title=f"{settings.APP_NAME} API",
    version=__version__,
    description=(
        "NSFW image classification (Falconsai/nsfw_image_detection) and CLIP + ChromaDB "
        "image-similarity checking. SQL stores images and verdicts; Chroma stores vectors."
    ),
    lifespan=lifespan,
)


def _public_error(status_code: int) -> str:
    """A stable public vocabulary; detailed diagnostics stay in server logs."""
    return {
        400: "Please check the submitted information.",
        401: "Please sign in to continue.",
        403: "You do not have access to this resource.",
        404: "The requested item was not found.",
        409: "That username or email is already in use.",
        413: "The selected file is too large.",
        415: "Please choose a supported image file.",
        422: "Please check the submitted information.",
        429: "Please wait a moment and try again.",
        503: "The service is temporarily unavailable. Please try again.",
        504: "The request took too long. Please try again.",
    }.get(status_code, "Something went wrong. Please try again.")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code >= 500:
        logger.warning("Handled API error status=%s path=%s", exc.status_code, request.url.path)
    return JSONResponse(status_code=exc.status_code, content={"detail": _public_error(exc.status_code)}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.info("Invalid request path=%s errors=%s", request.url.path, exc.errors())
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": _public_error(422)})


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server error path=%s method=%s", request.url.path, request.method)
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": _public_error(500)})


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(moderate.router)
app.include_router(explain.router)
app.include_router(history.router)
app.include_router(meta.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": __version__,
        "frontend_built": DIST.is_dir(),
    }


@app.get("/api", tags=["meta"])
def api_index() -> dict[str, object]:
    return {
        "app": settings.APP_NAME,
        "version": __version__,
        "docs": "/docs",
        "endpoints": [
            "POST /api/auth/register",
            "POST /api/auth/login",
            "GET /api/auth/me",
            "POST /api/moderate",
            "POST /api/checks/{id}/explain",
            "GET /api/history",
            "GET /api/checks/{id}",
            "GET /api/checks/{id}/image",
            "GET /api/checks/{id}/thumbnail",
            "GET /api/models",
            "GET /health",
        ],
    }


# --------------------------------------------------------------------------- #
# Frontend. Registered last so nothing here can shadow /api, /docs or /health.
# --------------------------------------------------------------------------- #
if DIST.is_dir():
    assets = DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    _dist_root = DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """Serve real files when they exist, otherwise index.html for client routing."""
        candidate = (DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_dist_root):
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")

else:

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "app": settings.APP_NAME,
            "version": __version__,
            "docs": "/docs",
            "frontend": "Not built. Run `npm install && npm run build` in frontend/.",
        }
