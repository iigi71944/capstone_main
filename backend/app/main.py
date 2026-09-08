from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes.analyze import router as analyze_router
from app.api.routes.improve_code import router as improve_router
from app.api.routes.style_apply import router as style_apply_router

app = FastAPI(
    title="Code Style Analyzer API",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "backend is running"}


app.include_router(analyze_router, prefix="/api/v1")
app.include_router(improve_router, prefix="/api/v1")
app.include_router(style_apply_router, prefix="/api/v1")