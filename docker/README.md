# Docker 部署（推荐：单容器 + SQLite）

> 说明：容器会同时运行 **FastAPI 后端**，并托管 `frontend/dist` 的静态资源（无需单独跑前端）。  
> 默认使用 SQLite（数据落在 `.jetlinks-ai/jetlinks_ai.db`），适合快速自托管与演示。

## 1) 准备配置

在仓库根目录：

```bash
cp .env.example .env
```

至少配置一个模型 Key：

- `OPENAI_API_KEY=...`（或配置 GLM：`GLM_API_KEY=...`）

## 2) 启动

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

默认端口：

- Web/UI + API：`http://127.0.0.1:8001`
- Health：`http://127.0.0.1:8001/health`

首次启动后，在页面完成 `Setup` 初始化（创建管理员账号与团队）。

## 3) 数据与目录

`docker/docker-compose.yml` 默认挂载到仓库根目录（已在 `.gitignore` 忽略）：

- `../.jetlinks-ai` → `/data/.jetlinks-ai`（SQLite、JWT secret、运行态数据）
- `../outputs` → `/data/outputs`（生成的文档/原型等产物）
- `../workspace` → `/workspace`（团队项目/工作区根目录，可自行替换为真实代码目录）

如需自定义宿主机路径，直接修改 `docker/docker-compose.yml` 的 `volumes` 即可。

