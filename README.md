# 企业知识库 RAG 问答系统

一个作品集：企业级 RAG 项目，使用 `FastAPI + React + Vite + PostgreSQL/pgvector + Redis + MinIO + 阿里云百炼 OpenAI 兼容接口` 实现。系统区分普通员工和管理员：员工负责提问，管理员负责维护企业知识库。

## 核心功能

- 员工端：登录、流式问答、引用来源展开、个人历史问答
- 管理员端：文档上传、后台入库、文档状态、失败重试、删除文档、重建索引
- 权限控制：JWT 鉴权，`admin / user` 两种角色，普通用户无法访问管理接口
- RAG 链路：PDF/DOCX/TXT/MD 解析、文本切分、百炼 embedding、FAISS 检索、qwen-plus 回答
- 稳定存储：PostgreSQL 保存用户、文档元数据、chunk 向量、问答历史；MinIO 保存原始文件
- 工程化：Redis 异步入库队列、独立 Worker、Docker Compose、一键启动说明、基础测试用例

## 演示账号

```text
系统管理员：admin / admin123
知识库管理员：kbadmin / kbadmin123
编辑者：editor / editor123
普通员工：user / user123
```

## 架构

```text
React + Vite
  ├─ 员工问答端：只提问、看引用、看自己的历史
  └─ 管理员端：上传、删除、重试、重建索引、看文档状态

FastAPI API（可横向扩展）
  ├─ JWT 鉴权与角色权限
  ├─ 文档解析与后台入库
  ├─ RAG 检索与流式问答
  └─ PostgreSQL + pgvector 元数据与向量检索

Storage
  ├─ MinIO                     原始上传文件与版本
  ├─ PostgreSQL + pgvector     用户、文档、chunks、历史与向量
  └─ Redis                     入库任务队列
```

## 本地启动

### 后端

```powershell
cd E:\CodexWorkspace\rag-bailian-demo\backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`：

```env
DASHSCOPE_API_KEY=你的阿里云百炼API Key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_CHAT_MODEL=qwen-plus
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
TOP_K=5
CHUNK_SIZE=800
CHUNK_OVERLAP=120
SIMILARITY_THRESHOLD=0.2
JWT_SECRET_KEY=请改成一个足够长的随机字符串
ACCESS_TOKEN_MINUTES=720
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:5176
```

启动：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

### 前端

```powershell
cd E:\CodexWorkspace\rag-bailian-demo\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5176
```

访问：

```text
http://127.0.0.1:5176
```

## Docker Compose

先安装并启动 Docker Desktop for Windows，确认 Docker Desktop 状态为 Running。

一键启动：

```powershell
cd E:\CodexWorkspace\rag-bailian-demo
.\start-docker.ps1 -Build
```

停止：

```powershell
.\stop-docker.ps1
```

需要清空 Docker 容器卷并重来：

```powershell
.\docker-reset.ps1
```

访问：

```text
Frontend:     http://localhost:5176
Backend docs: http://localhost:8000/docs
Nginx entry:  http://localhost:8080
MinIO:        http://localhost:9001
```

## API 概览

- `POST /api/auth/login` 登录
- `GET /api/auth/me` 当前用户
- `GET /api/health` 健康检查
- `GET /api/documents` 查看文档列表，需要登录
- `POST /api/upload` 上传文档，仅管理员
- `POST /api/rebuild` 重建索引，仅管理员
- `POST /api/documents/{id}/retry` 重新入库，仅管理员
- `DELETE /api/documents/{id}` 删除文档，仅管理员
- `POST /api/chat` 普通问答，需要登录
- `POST /api/chat/stream` 流式问答，需要登录
- `GET /api/history` 历史问答，普通用户只看自己的历史

## 测试

```powershell
cd E:\CodexWorkspace\rag-bailian-demo\backend
.venv\Scripts\activate
python -m pytest
```

当前测试覆盖：

- 未登录访问受保护接口返回 `401`
- 演示账号可登录
- 普通用户访问管理员接口返回 `403`
- 文本切分 overlap 行为

## 展示流程

1. 使用 `admin / admin123` 登录。
2. 上传企业制度、简历、产品手册或任意 PDF/DOCX/TXT/MD。
3. 在管理员端查看文档状态，必要时点击重建索引。
4. 退出后使用 `user / user123` 登录。
5. 在员工问答端提问，观察流式回答和引用来源。
6. 回到管理员端删除文档，再验证相关内容不再被检索。

## 注意

- `.env`、上传文件、SQLite 数据库、FAISS 索引未提交到 Git。
- 默认账号仅用于作品集演示，真实部署前应改为注册/后台创建用户。
- Docker 部署时，入库由 Redis 队列和独立 Worker 处理；本地 SQLite 仅用于不依赖基础设施的测试回退。
