# 企业知识库 RAG 问答系统

这是一个适合求职作品集展示的本地 RAG 项目，使用 `FastAPI + React + Vite + FAISS + 阿里云百炼 OpenAI 兼容接口` 实现。

## 功能

- 支持上传 `PDF / DOCX / TXT / MD`
- 自动解析、切分、Embedding 并写入本地 FAISS
- FAISS 索引、metadata、文档清单、问答历史本地持久化
- 支持普通问答接口和 SSE 流式问答接口
- 回答返回引用来源：文件名、分块序号、原文片段
- 前端分为员工问答端和管理员知识库管理端
- 员工端支持流式聊天、引用卡片、历史问答
- 管理员端支持文档上传、文档列表、重新构建索引和索引状态查看

## 目录结构

```text
rag-bailian-demo/
  backend/
    app/
      main.py
      config.py
      llm.py
      embeddings.py
      document_loader.py
      splitter.py
      vector_store.py
      rag.py
      schemas.py
    data/
      uploads/
      indexes/
    requirements.txt
    .env.example
    README.md
  frontend/
    src/
      App.jsx
      api.js
      main.jsx
      styles.css
    package.json
    index.html
  README.md
```

## 后端启动

```bash
cd rag-bailian-demo/backend
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
```

启动服务：

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

接口文档地址：

- http://localhost:8000/docs
- http://localhost:8000/api/health

## 前端启动

```bash
cd rag-bailian-demo/frontend
npm install
npm run dev
```

浏览器打开 Vite 输出的地址，通常是：

```text
http://localhost:5173
```

如需修改后端地址，可在前端创建 `.env`：

```env
VITE_API_BASE=http://localhost:8000
```

## API

- `POST /api/upload` 上传文件并入库
- `POST /api/rebuild` 重新构建向量索引
- `POST /api/chat` 普通问答
- `POST /api/chat/stream` 流式问答
- `GET /api/documents` 查看已上传文档
- `GET /api/history` 查看历史问答
- `GET /api/health` 健康检查

## RAG 流程

1. 上传文档后保存到 `backend/data/uploads`
2. 解析文本并按 `CHUNK_SIZE`、`CHUNK_OVERLAP` 切分
3. 调用百炼 `text-embedding-v4` 生成向量
4. 向量写入 FAISS，metadata 写入 `backend/data/indexes/metadata.json`
5. 提问时对问题生成 embedding
6. 从 FAISS 检索 top-k 相关片段
7. 将片段拼接进 prompt
8. 调用 `qwen-plus` 生成答案
9. 前端展示答案和引用来源卡片

## Prompt 模板

```text
你是企业知识库问答助手。请严格基于回答用户问题。
如果资料中没有答案，请说“根据当前知识库资料，无法确定答案”，不要编造。
回答要结构清晰，必要时使用列表。
每个关键结论后标注引用，例如：[来源1]、[来源2]。
```
