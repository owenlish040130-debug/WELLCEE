"""
Wellcee 个人资料 AI 增强 — 后端入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.profile import router as profile_router
from app.services.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化数据库"""
    await init_db()
    yield


app = FastAPI(
    title="Wellcee Profile AI",
    version="0.1.0",
    description="Wellcee 个人资料 AI 增强完善流程 API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
