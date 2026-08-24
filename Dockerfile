# syntax=docker/dockerfile:1
# OfferLoop 部署镜像 —— 多阶段构建
#
# 部署形态：单容器。前端（Next.js）静态导出后由 FastAPI 同端口托管，
# 8000 一个端口同时提供页面与 /api/*（见 app/main.py 与 frontend/next.config.ts）。

# ── Stage 1: 前端静态构建（node 只参与构建，不进最终镜像）──
FROM node:22-alpine AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # output: "export" → frontend/out

# ── Stage 2: 后端运行时（Python 3.13 + FastAPI）──
FROM python:3.13-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 依赖与 pyproject.toml [project].dependencies 保持一致。
# 放在最前：不依赖任何 COPY 的文件，依赖层可被 Docker 长期缓存。
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn>=0.30.0" \
    "chromadb>=0.5.0" \
    "openai>=1.50.0" \
    "pandas>=2.2.0" \
    "hdbscan>=0.8.0" \
    "scikit-learn>=1.5.0" \
    "streamlit>=1.38.0" \
    "jinja2>=3.1.0" \
    "pydantic>=2.9.0" \
    "python-dotenv>=1.0.0" \
    "httpx>=0.27.0" \
    "pypdf>=5.0.0" \
    "python-multipart>=0.0.9"

# 源码（.dockerignore 已排除 .env / data / node_modules / .git）
COPY . .

# 前端产物：Stage 1 的 out/ 挂到后端预期路径 frontend/out
COPY --from=frontend /fe/out ./frontend/out

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
