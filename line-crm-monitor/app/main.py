"""中央监控 FastAPI 入口。Server 模式：监听 0.0.0.0，供本机/局域网/Tailscale 访问。

同时托管 Vue 构建产物（web/dist），并提供 SPA history 回退。
"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, cleanup, config, ingest, query
from .db import close_pool, init_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_public_safe()   # PUBLIC_MODE=true 时 fail-closed 校验（启动前）
    await init_schema()
    cleanup_task = asyncio.create_task(cleanup.cleanup_loop())
    yield
    cleanup_task.cancel()
    await close_pool()


app = FastAPI(title="LINE CRM 中央监控", version="0.1.0", lifespan=lifespan)

# 登录会话：httpOnly + SameSite 签名 cookie（itsdangerous，Starlette 自带）
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SESSION_SECRET or os.urandom(24).hex(),
    session_cookie="monitor_session",
    same_site="lax",
    https_only=config.PUBLIC_MODE,  # 公网模式强制 Secure cookie（本地 http 将无法登录）
    max_age=86400,  # 24 小时
)

_origins = [o.strip() for o in config.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router, prefix="/api")
app.include_router(query.router, prefix="/api")
app.include_router(auth.router, prefix="/api")


@app.get("/health")
async def health():
    return {"ok": True}


# ── 前端静态托管（Vue 构建产物 dist，由 Dockerfile 阶段 2 COPY 进镜像）──
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "web", "dist")


@app.get("/")
async def index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


app.mount("/assets", StaticFiles(directory=os.path.join(_STATIC_DIR, "assets")), name="assets")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """SPA history 回退：非 /api、非 /health、非 /assets 的 GET 返回 index.html。"""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
