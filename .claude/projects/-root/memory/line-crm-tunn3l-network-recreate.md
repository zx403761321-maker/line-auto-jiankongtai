---
name: line-crm-tunn3l-network-recreate
description: 重建 api 容器会断掉 tunn3l 隧道，必须同时 force-recreate tunn3l
metadata: 
  node_type: memory
  type: project
  originSessionId: 6d9a2de0-f3cb-4b9c-b8c3-221b333357bd
  modified: 2026-09-07T09:27:44.051Z
---

中央监控 docker-compose 里 `tunn3l` 用 `network_mode: "service:api"`，和 api **共享网络命名空间**。只 `docker compose up -d api` 重建 api 后，tunn3l 仍挂在旧的（已销毁的）命名空间上，连不到 `localhost:8000`，公网 `line-monitor.tunn3l.sh` 会打不开（本机 localhost:8000 仍正常，只有隧道断）。

**正确姿势**：改完前端/后端后，`docker compose build api && docker compose up -d --force-recreate api tunn3l`（两个一起 force-recreate，让 tunn3l 重新挂到新 api 容器）。

排查提示：tunn3l 镜像里没有 wget/curl，别用 `docker exec tunn3l wget ...` 测连通性（会误报 UNREACHABLE），直接 `curl https://line-monitor.tunn3l.sh/` 测公网即可。
