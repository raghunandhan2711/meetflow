"""Application composition: middleware, errors, API routers, and web assets."""
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from .config import ROOT, settings
from .lifecycle import lifespan
from .api import router as api_router
from .workspace import router as workspace_router
from . import security

STATIC_ROOT = ROOT / 'static'

app = FastAPI(title='AI-Powered Meeting Analysis & Task Automation System', version='2.0.0', lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.middleware('http')(security.guard)


@app.exception_handler(StarletteHTTPException)
async def safe_http_error(request, exc):
    return JSONResponse({'detail': security.redact(exc.detail)}, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request, exc):
    return JSONResponse({'detail': security.redact(jsonable_encoder(exc.errors()))}, status_code=422)

app.include_router(api_router)
app.include_router(workspace_router)
app.mount('/static', StaticFiles(directory=STATIC_ROOT), name='static')


@app.get('/')
def index():
    return FileResponse(STATIC_ROOT / 'landing.html')


@app.get('/app')
def workspace():
    return FileResponse(STATIC_ROOT / 'index.html')
