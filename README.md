# 企业知识库 RAG 问答系统

一个面向企业知识库场景的 RAG 项目，采用 `React + FastAPI + PostgreSQL/pgvector + Redis + MinIO + 阿里云百炼`。系统支持多角色权限、文档异步入库、向量检索、流式回答、引用来源、问答历史、反馈和审计日志。

当前 Docker 版本采用“模块化单体 API + 独立 Worker + 共享基础设施”：API 与 Worker 可以独立扩容，不依赖进程内 FAISS 索引或生产服务器本地文件。

## 核心功能

- 问答端：登录、SSE 流式回答、引用来源展开、个人历史记录和回答反馈
- 管理端：知识库管理、文档上传、异步入库、失败重试、归档、删除和重建索引
- 权限控制：JWT 鉴权，支持四种角色、部门范围、指定用户名单和 0—3 级安全等级
- RAG 链路：PDF/DOCX/TXT/MD 解析、结构化切分、百炼 Embedding、pgvector 检索、`qwen-plus` 回答
- 共享存储：PostgreSQL 保存业务数据和向量，MinIO 保存原始文件，Redis 承载入库队列
- 可观测性：健康检查、入库任务进度、失败原因、审计日志和容器日志
- 工程化：Docker Compose 编排、API/Worker 分离、一键启停脚本和自动测试

## 系统架构

```text
浏览器
  │
  ▼
Nginx :8080
  ├─ /        ──► React + Vite 前端 :5176
  └─ /api/*   ──► FastAPI API :8000
                       │
                       ├─► PostgreSQL + pgvector :5432
                       │     用户、角色、知识库、文档版本、chunks、向量、历史、反馈、审计
                       │
                       ├─► MinIO :9000
                       │     原始上传文件和文档版本
                       │
                       └─► Redis :6379
                              入库任务队列
                                │
                                ▼
                         独立 Worker
                         解析 → 切块 → Embedding → pgvector 入库
```

文档入库状态机：

```text
pending → parsing → chunking → embedding → indexing → completed
                                                        └─ failed（可重试）
```

## 技术栈

| 层级 | 技术 | 作用 |
| --- | --- | --- |
| 前端 | React、Vite | 登录、问答、文档和系统管理界面 |
| 网关 | Nginx | 统一入口、前端/API 反向代理、SSE 转发 |
| API | FastAPI、Pydantic | 鉴权、知识库、文档、问答、历史、反馈和审计接口 |
| Worker | Python Worker | 从 Redis 消费任务，完成解析、切块、向量化和入库 |
| 数据库 | PostgreSQL 16 | 用户、权限、知识库、文档、任务和问答业务数据 |
| 向量检索 | pgvector | 1024 维 Embedding 保存和余弦相似度检索 |
| 队列 | Redis 7 | API 与 Worker 之间的异步入库任务队列 |
| 对象存储 | MinIO | 原始文件和版本文件存储 |
| 模型服务 | 阿里云百炼 | `text-embedding-v4` 向量化和 `qwen-plus` 问答 |

## 项目结构

```text
rag-bailian-demo/
├─ backend/
│  ├─ app/
│  │  ├─ main.py              FastAPI 应用、路由和生命周期
│  │  ├─ database.py          SQLite/PostgreSQL 兼容访问、表结构和默认数据
│  │  ├─ rag.py               文档入库、检索、问答、权限过滤和业务逻辑
│  │  ├─ worker.py            Redis 入库任务消费者
│  │  ├─ queue.py             Redis 队列封装
│  │  ├─ object_storage.py    本地文件/MinIO 对象存储适配
│  │  ├─ vector_store.py      SQLite 测试回退/pgvector 向量读写
│  │  ├─ document_loader.py   PDF、DOCX、TXT、MD 文档解析
│  │  ├─ splitter.py          文本切分
│  │  ├─ security.py          密码哈希、JWT 和鉴权
│  │  ├─ schemas.py           API 请求与响应模型
│  │  └─ config.py            环境变量配置
│  ├─ scripts/
│  │  └─ migrate_sqlite_to_postgres.py  旧 SQLite 数据迁移工具
│  ├─ tests/                  后端自动测试
│  ├─ Dockerfile
│  └─ requirements.txt
├─ frontend/
│  ├─ src/                    React 页面、组件、状态和 API 调用
│  ├─ vite.config.js          开发服务器和 API 代理
│  └─ Dockerfile
├─ ops/
│  └─ nginx.conf              Docker 内统一入口和反向代理
├─ docker-compose.yml         七个容器服务及数据卷编排
├─ start-docker.ps1           Windows 一键启动
├─ stop-docker.ps1            Windows 一键关闭
└─ docker-reset.ps1           删除容器和数据卷（危险操作）
```

## 演示账号

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 系统管理员 | `admin` | `admin123` |
| 知识库管理员 | `kbadmin` | `kbadmin123` |
| 编辑者 | `editor` | `editor123` |
| 普通员工 | `user` | `user123` |

这些账号仅用于本地演示，正式部署前必须更换。

## 文档权限模型

用户和文档分别保存 `clearance_level` 与 `security_level`：

| 等级 | 名称 | 典型用途 |
| --- | --- | --- |
| 0 | 公开 | 可公开的制度和资料 |
| 1 | 内部 | 普通企业内部资料 |
| 2 | 机密 | 部门经理、核心项目成员可见 |
| 3 | 绝密 | 高管或显式授权人员可见 |

公开（0级）文档对所有启用状态的已登录用户可见，不再受部门、角色和指定用户范围限制。内部及以上文档必须同时满足：

```text
用户安全等级 >= 文档密级
AND 用户角色在文档可见角色中（非空时）
AND 用户部门在文档部门范围中（非空时）
AND 用户在文档指定用户列表中（非空时）
```

权限条件会进入 PostgreSQL/pgvector 的向量查询，并在返回来源前再次校验。系统管理员可在用户管理中调整员工安全等级，在上传和文档列表中设置文档密级。`position` 仍是岗位展示字段，不直接参与权限计算。

## Docker 一键启动

### 1. 准备配置

安装并启动 Docker Desktop。第一次运行前，复制环境变量示例：

```powershell
cd E:\CodexWorkspace\rag-bailian-demo
copy backend\.env.example backend\.env
```

编辑 `backend/.env`，至少填写：

```env
DASHSCOPE_API_KEY=你的阿里云百炼API Key
JWT_SECRET_KEY=请替换成足够长的随机字符串
```

`backend/.env` 已被 `.gitignore` 排除，不会提交到 GitHub。

### 2. 首次构建并启动

使用一键脚本：

```powershell
.\start-docker.ps1 -Build
```

或者直接使用 Docker Compose：

```powershell
docker compose up -d --build
```

后续代码没有变化时，可以快速启动：

```powershell
.\start-docker.ps1
```

或者：

```powershell
docker compose up -d
```

### 3. 访问系统

| 服务 | 地址 | 说明 |
| --- | --- | --- |
| 统一系统入口 | http://localhost:8080 | 推荐使用，Nginx 统一代理前端和 API |
| 前端直连 | http://localhost:5176 | Vite 开发服务 |
| API 文档 | http://localhost:8000/docs | FastAPI Swagger UI |
| 健康检查 | http://localhost:8000/api/health | 数据库、队列、对象存储和向量状态 |
| MinIO 控制台 | http://localhost:9001 | 本地默认账号 `ragminio / ragminio123` |

### 4. 查看状态和日志

```powershell
docker compose ps
docker compose logs -f
```

只看 API 和 Worker：

```powershell
docker compose logs -f backend worker
```

### 5. 一键关闭

```powershell
.\stop-docker.ps1
```

等价命令：

```powershell
docker compose down
```

`docker compose down` 会删除容器和网络，但会保留 PostgreSQL 与 MinIO 数据卷。关闭完成后可以退出 Docker Desktop。

### 6. 清空全部 Docker 数据

```powershell
.\docker-reset.ps1
```

脚本会要求输入 `RESET`，随后执行 `docker compose down -v`。这会永久删除 PostgreSQL 和 MinIO 数据，只应在确定需要重新初始化时使用。

## Docker 服务

| Compose 服务 | 端口 | 持久化/职责 |
| --- | --- | --- |
| `nginx` | `8080` | 统一入口 |
| `frontend` | `5176` | React/Vite 前端 |
| `backend` | `8000` | FastAPI API，带健康检查 |
| `worker` | 无宿主机端口 | Redis 异步任务消费者 |
| `postgres` | `5432` | `postgres-data` 数据卷，含 pgvector |
| `redis` | `6379` | 入库任务队列 |
| `minio` | `9000/9001` | `minio-data` 数据卷，对象 API/控制台 |

## 旧 SQLite 数据迁移

如果 `backend/data/rag.db` 中存在旧版演示数据，在 Docker 服务启动后执行一次：

```powershell
docker compose exec -T backend python scripts/migrate_sqlite_to_postgres.py /app/data/rag.db
```

迁移工具会：

1. 将用户、知识库、文档、历史、反馈和审计元数据导入 PostgreSQL。
2. 将可读取的旧上传文件写入 MinIO。
3. 为文档创建 Redis 入库任务，由 Worker 重新解析和生成向量。
4. 不复制旧 FAISS 文件；生产检索统一使用 pgvector。

这是一次性迁移命令，不要在没有需要时重复执行。

## 非 Docker 本地开发

SQLite 仅作为轻量测试和本地开发回退，不是生产存储方案。

后端：

```powershell
cd E:\CodexWorkspace\rag-bailian-demo\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
$env:DATABASE_URL = "sqlite:///data/rag.db"
$env:INGESTION_MODE = "inline"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd E:\CodexWorkspace\rag-bailian-demo\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5176
```

## API 概览

- `POST /api/auth/login`：登录
- `GET /api/auth/me`：当前用户
- `GET /api/health`：系统健康检查
- `GET/POST /api/knowledge-bases`：知识库查询和创建
- `GET /api/documents`：文档列表
- `POST /api/documents/upload`：上传文件并创建入库任务
- `POST /api/documents/{id}/retry`：失败任务重试
- `PATCH /api/documents/{id}/permissions`：修改文档密级和访问范围，仅系统管理员
- `POST /api/documents/{id}/archive`：归档文档
- `DELETE /api/documents/{id}`：删除文档、元数据和对象
- `GET /api/ingestion-jobs`：入库任务列表和进度
- `POST /api/chat`：普通问答
- `POST /api/chat/stream`：SSE 流式问答
- `GET /api/history`：个人/管理员历史记录
- `POST /api/feedback`：回答反馈
- `GET /api/audit-logs`：管理员审计日志

完整接口定义请查看 http://localhost:8000/docs。

## 测试

本地测试：

```powershell
cd E:\CodexWorkspace\rag-bailian-demo\backend
.venv\Scripts\activate
python -m pytest -q
```

当前测试覆盖登录鉴权、角色权限、知识库接口、文本切分、引用过滤、数据库游标和 SQLite/PostgreSQL JSON 数据兼容。

## 生产上线前仍需完成

- 将数据库、MinIO、JWT 和演示账号密码移出 Compose，使用密钥管理服务
- 关闭 PostgreSQL、Redis、MinIO API 等不必要的宿主机公网端口
- 配置域名、HTTPS、证书续期、CORS 白名单和可信代理
- 增加数据库/对象存储备份、恢复演练、日志采集、指标监控和告警
- 使用正式数据库迁移工具管理表结构版本
- 增加限流、文件安全扫描、OCR、任务死信队列和更完整的重试策略
- 增加检索质量评测、端到端测试、压力测试和 CI/CD
- 将默认账号改为企业身份源或完善的用户管理流程

## 注意事项

- `.env`、SQLite 数据库、上传文件、索引和日志不会提交到 Git。
- Docker 生产路径使用 PostgreSQL/pgvector、Redis 和 MinIO，不再依赖本地 FAISS 索引。
- Docker Desktop 必须先运行，容器启动后才可访问系统；执行 `docker compose down` 后可以关闭 Docker Desktop。
- 默认密码和暴露端口仅适用于本机演示环境。
