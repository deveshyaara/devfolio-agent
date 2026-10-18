"""Optional health sidecar: uvicorn health:app --host 0.0.0.0 --port 8000."""

import asyncio
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from devfolio.logging import configure_logging

load_dotenv()
configure_logging()
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def correlation(request, call_next):
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    from devfolio.runtime import get_runtime

    try:
        usable = await asyncio.wait_for(asyncio.to_thread(lambda: get_runtime().reader.ready()), timeout=6)
        if usable:
            return {"status": "ready"}
    except Exception:
        pass
    return JSONResponse({"status": "unavailable"}, status_code=503)
