import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from givenergy_modbus.exceptions import CommunicationError, ExceptionBase

from api import router as api_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(title="GivEnergy Local")
app.include_router(api_router)


@app.exception_handler(ExceptionBase)
async def givenergy_exception_handler(request: Request, exc: ExceptionBase) -> JSONResponse:
    """Surface library errors (e.g. a write the connected model doesn't permit, or a
    connection drop) as a clean 4xx/502 response instead of a raw 500 traceback."""
    status = 502 if isinstance(exc, CommunicationError) else 400
    return JSONResponse(status_code=status, content={"detail": str(exc)})


@app.exception_handler(TimeoutError)
async def timeout_exception_handler(request: Request, exc: TimeoutError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": "device did not respond in time"})

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
