"""FastAPI 应用入口"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config.logging import setup_logging
from api.routes.ingest import router as ingest_router
from api.routes.documents import router as documents_router
from api.routes.search import router as search_router
from api.routes.agents import router as agents_router
from api.routes.websocket import router as ws_router
from api.routes.tags import router as tags_router
from api.routes.agent import router as agent_router

logger = setup_logging(__name__)

app = FastAPI(
    title="scholarAgent API",
    description="论文辅助 Agent 系统 API",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(ingest_router, prefix="/api/v1/ingest", tags=["导入"])
app.include_router(documents_router, prefix="/api/v1/documents", tags=["文档"])
app.include_router(search_router, prefix="/api/v1/search", tags=["检索"])
app.include_router(agents_router, prefix="/api/v1/agents", tags=["Agent"])
app.include_router(ws_router, prefix="/api/v1/ws", tags=["WebSocket"])
app.include_router(tags_router, prefix="/api/v2/tags", tags=["标签管理"])
app.include_router(agent_router, prefix="/api/v1/agent", tags=["主 Agent"])


@app.get("/api/v1/health", tags=["系统"])
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.1.0"}


# ======================================================================
# 前端静态托管（可选）
#
# web/dist 存在时同源托管构建产物，浏览器直接访问 http://localhost:8000 即可，
# 无需单独跑前端服务。未构建时跳过，不影响纯 API 使用。
# ======================================================================
WEB_DIST = (Path(__file__).resolve().parent.parent / "web" / "dist").resolve()


def _safe_static_file(relative: str) -> Path | None:
    """把请求路径映射到 dist 内的真实文件，并阻止路径穿越"""
    candidate = (WEB_DIST / relative).resolve()
    if candidate != WEB_DIST and WEB_DIST in candidate.parents and candidate.is_file():
        return candidate
    return None


if WEB_DIST.is_dir():
    assets_dir = WEB_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def spa_root():
        return FileResponse(WEB_DIST / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """前端路由回退：静态资源直出，其余交给 index.html 交由前端路由处理"""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        target = _safe_static_file(full_path)
        if target is not None:
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
