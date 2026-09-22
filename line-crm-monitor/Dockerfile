# ── 阶段 1：构建 Vue 前端（部署机无需安装 Node/npm）──
FROM node:20-alpine AS build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ── 阶段 2：运行 FastAPI + 托管前端 dist ──
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY schema.sql ./
COPY --from=build /web/dist ./web/dist
ENV PORT=8000
EXPOSE 8000
# 监听 0.0.0.0（Server 模式，局域网/Tailscale 可访问）；PORT 由环境变量覆盖
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
