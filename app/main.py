"""OfferLoop FastAPI 服务入口。

用法：
  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

部署形态：
  单进程部署 —— 前端（Next.js）build 静态导出到 frontend/out，由本服务托管，
  8000 一个端口同时提供页面与 /api/*。开发时前端也可用 next dev（3000，rewrites 代理）。
"""
import os

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat, dashboard, diagnose, items, mock, profile, record

app = FastAPI(
    title="OfferLoop",
    description="记得你的面试错题本 Agent —— Web 版",
    version="1.0.0",
)

app.include_router(chat.router, prefix="/api")
app.include_router(record.router, prefix="/api")
app.include_router(mock.router, prefix="/api")
app.include_router(items.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(diagnose.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── 前端静态托管（frontend/out，存在才挂载；不存在则纯 API 模式）──
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "out")

if os.path.isdir(OUT_DIR):
    app.mount("/_next", StaticFiles(directory=os.path.join(OUT_DIR, "_next")), name="next-static")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """页面路由：文件 → 目录 index.html → 404。API 路由已在上方优先匹配。"""
        candidate = os.path.join(OUT_DIR, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
        if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "index.html")):
            return FileResponse(os.path.join(candidate, "index.html"))
        if os.path.isfile(candidate + ".html"):
            return FileResponse(candidate + ".html")
        not_found = os.path.join(OUT_DIR, "404.html")
        if os.path.isfile(not_found):
            return FileResponse(not_found, status_code=404)
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
