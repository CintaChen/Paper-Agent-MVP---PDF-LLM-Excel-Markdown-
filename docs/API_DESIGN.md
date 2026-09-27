# Backend API 设计文档

> 面向前端（其他 Agent）的接口规范，定义了 FastAPI 路由、请求/响应格式、数据模型。

---

## 1. 架构概览

```
Frontend (其他 Agent)
    │
    │ HTTP / WebSocket
    ▼
FastAPI (api/routes/*.py)
    │
    ├── /api/v1/ingest      ← 论文导入
    ├── /api/v1/documents   ← 文档管理
    ├── /api/v1/search      ← 混合检索
    ├── /api/v1/agents      ← 单次调用型 Agent（大纲/润色/风格/分析）
    ├── /api/v1/agent       ← 工具化主 Agent（Orchestrator，含 WS 流式）
    ├── /api/v1/ws          ← 流式聊天
    ├── /api/v2/tags        ← 内容标签管理
    └── /api/v1/health      ← 健康检查
```

---

## 2. 基础信息

| 项目 | 说明 |
|------|------|
| Base URL | `http://localhost:8000/api/v1` |
| 数据格式 | JSON |
| 认证 | 暂不需要（本地工具） |
| CORS | 允许所有来源（开发模式） |

---

## 3. 数据模型

### 3.1 Document（论文）

```json
{
  "id": "string",
  "title": "string",
  "authors": ["string"],
  "year": "string | null",
  "journal": "string | null",
  "doi": "string | null",
  "file_path": "string",
  "total_pages": 0,
  "chunk_count": 0,
  "created_at": "2024-01-01T00:00:00",
  "metadata": {}
}
```

### 3.2 Chunk（文本块）

```json
{
  "id": "string",
  "doc_id": "string",
  "text": "string",
  "page": 0,
  "metadata": {}
}
```

### 3.3 SearchResult（检索结果）

```json
{
  "chunk": { ... },
  "score": 0.95,
  "source": "bm25 | vector | fusion | rerank",
  "rank": 1
}
```

### 3.4 AgentResponse（Agent 响应）

```json
{
  "status": "success | error",
  "data": { ... },
  "message": "string",
  "duration_ms": 1234
}
```

---

## 4. API 接口

### 4.1 健康检查

```
GET /api/v1/health
```

**响应：**
```json
{
  "status": "ok",
  "version": "0.1.0",
  "services": {
    "milvus": "connected | disconnected",
    "bm25": "ready | not_ready",
    "llm": "ready | not_ready"
  }
}
```

---

### 4.2 论文导入

#### 4.2.1 导入单个 PDF

```
POST /api/v1/ingest/file
```

**请求：**
```json
{
  "file_path": "string"
}
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "id": "string",
    "title": "string",
    "total_pages": 10,
    "chunk_count": 25
  }
}
```

#### 4.2.2 批量导入目录

```
POST /api/v1/ingest/directory
```

**请求：**
```json
{
  "dir_path": "string",
  "recursive": false
}
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "total_files": 10,
    "success_count": 8,
    "failed_count": 2,
    "documents": [
      { "id": "...", "title": "...", "status": "success" },
      { "id": "...", "title": "...", "status": "failed", "error": "..." }
    ]
  }
}
```

#### 4.2.3 上传 PDF

```
POST /api/v1/ingest/upload
```

**请求：** `multipart/form-data`
- `file`: PDF 文件

**响应：**
```json
{
  "status": "success",
  "data": {
    "id": "string",
    "title": "string",
    "file_size": 1024000
  }
}
```

---

### 4.3 文档管理

#### 4.3.1 列出所有文档

```
GET /api/v1/documents?page=1&page_size=20&search=keyword
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "total": 100,
    "page": 1,
    "page_size": 20,
    "documents": [
      {
        "id": "string",
        "title": "string",
        "authors": ["string"],
        "year": "2024",
        "journal": "string",
        "doi": "string",
        "total_pages": 10,
        "chunk_count": 25,
        "created_at": "2024-01-01T00:00:00"
      }
    ]
  }
}
```

#### 4.3.2 获取单个文档

```
GET /api/v1/documents/{doc_id}
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "id": "string",
    "title": "string",
    "authors": ["string"],
    "year": "2024",
    "journal": "string",
    "doi": "string",
    "file_path": "string",
    "total_pages": 10,
    "chunks": [
      {
        "id": "string",
        "text": "string",
        "page": 1
      }
    ]
  }
}
```

#### 4.3.3 删除文档

```
DELETE /api/v1/documents/{doc_id}
```

**响应：**
```json
{
  "status": "success",
  "message": "文档已删除"
}
```

#### 4.3.4 获取文档统计

```
GET /api/v1/documents/stats
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "total_documents": 100,
    "total_chunks": 2500,
    "total_pages": 5000,
    "storage_size_mb": 1024.5
  }
}
```

---

### 4.4 混合检索

#### 4.4.1 基础检索

```
POST /api/v1/search
```

**请求：**
```json
{
  "query": "string",
  "top_k": 10,
  "use_bm25": true,
  "use_vector": true,
  "use_rerank": true,
  "filters": {
    "year": "2024",
    "journal": "string"
  }
}
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "query": "string",
    "results": [
      {
        "chunk": {
          "id": "string",
          "text": "string",
          "page": 1,
          "metadata": {
            "doc_id": "string",
            "source": "string"
          }
        },
        "score": 0.95,
        "source": "fusion",
        "rank": 1
      }
    ],
    "total_found": 25,
    "duration_ms": 150
  }
}
```

#### 4.4.2 仅向量检索

```
POST /api/v1/search/vector
```

**请求：**
```json
{
  "query": "string",
  "top_k": 10
}
```

#### 4.4.3 仅关键词检索

```
POST /api/v1/search/keyword
```

**请求：**
```json
{
  "query": "string",
  "top_k": 10
}
```

---

### 4.5 Agent 调用

#### 4.5.1 写作思路 Agent

```
POST /api/v1/agents/writing/outline
```

**请求：**
```json
{
  "topic": "string",
  "context_query": "string | null",
  "top_k": 5
}
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "topic": "string",
    "outline": "string (markdown)",
    "references": [
      {
        "doc_id": "string",
        "title": "string",
        "relevant_chunks": ["string"]
      }
    ]
  },
  "duration_ms": 3000
}
```

#### 4.5.2 段落润色 Agent

```
POST /api/v1/agents/writing/paragraph
```

**请求：**
```json
{
  "topic": "string",
  "draft": "string",
  "context_query": "string | null",
  "top_k": 3
}
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "original": "string",
    "polished": "string",
    "changes": ["string"]
  }
}
```

#### 4.5.3 风格优化 Agent

```
POST /api/v1/agents/style/polish
```

**请求：**
```json
{
  "text": "string",
  "mode": "polish | simplify | academic"
}
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "original": "string",
    "optimized": "string",
    "mode": "polish"
  }
}
```

#### 4.5.4 论文分析 Agent

```
POST /api/v1/agents/analysis/analyze
```

**请求：**
```json
{
  "doc_id": "string",
  "analysis_type": "full | method | results | limitations"
}
```

**响应：**
```json
{
  "status": "success",
  "data": {
    "doc_id": "string",
    "analysis": {
      "title": "string",
      "authors": ["string"],
      "year": "string",
      "journal": "string",
      "research_method": { "text": "string", "evidence_pages": [1, 2] },
      "key_findings": [{ "text": "string", "evidence_pages": [5, 6] }],
      "limitations": ["string"]
    }
  }
}
```

---

### 4.6 流式输出（WebSocket）

```
WS /api/v1/ws/chat
```

**客户端发送：**
```json
{
  "type": "chat",
  "message": "string",
  "session_id": "string | null"
}
```

**服务端推送：**
```json
{
  "type": "token",
  "content": "string",
  "done": false
}
```

**完成时：**
```json
{
  "type": "done",
  "session_id": "string",
  "duration_ms": 3000
}
```

---

### 4.7 主 Agent（工具化写作）

> 与 `/api/v1/agents/*`（单次同步调用）不同，`/api/v1/agent/chat` 调用的是
> **Orchestrator**：主 Agent 在推理循环中自主决定调用 `rag_search` /
> `draft_expand` / `style_polish` / `self_critique`，生成后自评、不达标则重写。

#### 4.7.1 同步对话

```
POST /api/v1/agent/chat
```

**请求：**
```json
{
  "message": "请扩写《相关工作》，重点对比已有方法的两点不足",
  "context": {
    "topic": "AI 赋能个性化学习",
    "framework": "1 引言  2 相关工作  3 方法  4 实验  5 结论",
    "ideas": "引言突出个性化学习痛点与本文贡献",
    "requirements": "本节约 800 字，需对比至少两种方法",
    "sections": [
      { "title": "引言", "content": "（已写好的引言……）" }
    ]
  },
  "history": [
    { "role": "user", "content": "上一轮的问题" },
    { "role": "assistant", "content": "上一轮的回复" }
  ],
  "max_iterations": 8
}
```

> `context` 与 `context_text` 二选一：前者为结构化上下文（推荐），后者为纯文本。

**响应：**
```json
{
  "status": "success",
  "data": {
    "content": "生成的正文……",
    "iterations": 5,
    "stopped_reason": "completed",
    "steps": [
      {
        "iteration": 1,
        "tool": "rag_search",
        "arguments": { "query": "个性化学习 对比方法" },
        "output": "{\"query\": \"...\", \"count\": 3, \"results\": [...]}"
      },
      {
        "iteration": 2,
        "tool": "draft_expand",
        "arguments": { "section_title": "相关工作", "user_ideas": "..." },
        "output": "（草稿正文）"
      },
      {
        "iteration": 3,
        "tool": "self_critique",
        "arguments": { "content": "（草稿正文）", "requirements": "..." },
        "output": "{\"passed\": false, \"score\": 6, \"issues\": [...]}"
      }
    ]
  },
  "duration_ms": 12000
}
```

- `stopped_reason`：`completed`（主 Agent 主动交付）或 `max_iterations`（达上限强制结束）。
- `steps`：主 Agent 自主选择的工具轨迹，可用于前端展示推理过程。

#### 4.7.2 流式对话

```
WS /api/v1/agent/chat/ws
```

**客户端发送**（JSON 对象，或直接发送裸文本消息）：
```json
{
  "message": "请扩写《相关工作》",
  "context": { "topic": "...", "framework": "...", "ideas": "..." },
  "max_iterations": 8
}
```

**服务端推送事件序列：**

```json
{ "type": "tool_call",   "iteration": 1, "tool": "rag_search", "arguments": { "query": "..." } }
```
```json
{ "type": "tool_result", "iteration": 1, "tool": "rag_search", "output": "..." }
```
```json
{ "type": "token", "content": "正文片段", "done": false }
```
```json
{
  "type": "done",
  "content": "完整正文",
  "iterations": 5,
  "stopped_reason": "completed",
  "steps": [ { "iteration": 1, "tool": "rag_search", "arguments": {}, "output": "..." } ],
  "duration_ms": 12000
}
```
```json
{ "type": "error", "message": "错误说明" }
```

> 工具调用事件实时推送；最终正文先分片以 `token` 事件推送，再以 `done` 事件给出完整结果与工具轨迹。

---

## 5. 错误处理

### 5.1 错误响应格式

```json
{
  "status": "error",
  "error": {
    "code": "VALIDATION_ERROR | NOT_FOUND | INTERNAL_ERROR",
    "message": "string",
    "details": {}
  }
}
```

### 5.2 HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 422 | 验证错误 |
| 500 | 服务器内部错误 |

---

## 6. 前端交互流程

### 6.1 导入论文

```
1. 用户选择文件/目录
2. POST /api/v1/ingest/file 或 /api/v1/ingest/directory
3. 显示进度（轮询或 WebSocket）
4. 导入完成后刷新文档列表
```

### 6.2 检索与问答

```
1. 用户输入问题
2. POST /api/v1/search
3. 展示检索结果（高亮相关片段）
4. 用户可选择调用 Agent 进一步处理
```

### 6.3 写作辅助

```
1. 用户选择 Agent 类型（outline / paragraph / style）
2. 输入主题/草稿
3. POST /api/v1/agents/...
4. 展示结果（支持流式输出）
5. 用户可编辑并保存
```

---

## 7. 文件结构（Backend）

```
api/
├── __init__.py
├── app.py              # FastAPI 应用入口
├── routes/
│   ├── __init__.py
│   ├── ingest.py       # 导入相关路由
│   ├── documents.py    # 文档管理路由
│   ├── search.py       # 检索路由
│   ├── agents.py       # Agent 路由
│   └── websocket.py    # WebSocket 路由
├── schemas/
│   ├── __init__.py
│   ├── document.py     # Pydantic 请求/响应模型
│   ├── search.py
│   └── agent.py
└── middleware/
    ├── __init__.py
    ├── cors.py         # CORS 中间件
    └── error.py        # 错误处理中间件
```

---

## 8. 关键实现要点

### 8.1 FastAPI 应用入口

```python
# api/app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="scholarAgent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router, prefix="/api/v1/ingest")
app.include_router(documents_router, prefix="/api/v1/documents")
app.include_router(search_router, prefix="/api/v1/search")
app.include_router(agents_router, prefix="/api/v1/agents")
```

### 8.2 依赖注入

```python
# 全局服务实例
from rag.ingest import IngestPipeline
from rag.retrieve import HybridRetriever
from agent.writing_agent import WritingAgent
from agent.style_agent import StyleAgent

ingest_pipeline = IngestPipeline()
retriever = HybridRetriever()
writing_agent = WritingAgent()
style_agent = StyleAgent()
```

### 8.3 异步处理

- 文件上传使用 `UploadFile`
- 长时间任务使用 `BackgroundTasks`
- 流式输出使用 `WebSocket` 或 `StreamingResponse`

---

## 9. 前端需知

### 9.1 环境变量

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_WS_URL=ws://localhost:8000/api/v1/ws
```

### 9.2 关键页面建议

| 页面 | 功能 | 主要 API |
|------|------|----------|
| 导入页 | 上传/批量导入 PDF | `/ingest/*` |
| 文档列表页 | 查看/删除文档 | `/documents` |
| 检索页 | 输入问题、查看结果 | `/search` |
| 写作助手页 | 调用写作 Agent | `/agents/writing/*` |
| 风格优化页 | 调用风格 Agent | `/agents/style/*` |
| 分析页 | 查看论文分析结果 | `/agents/analysis/*` |

### 9.3 状态管理建议

- 文档列表：全局缓存，导入后刷新
- 检索结果：页面级状态
- Agent 调用：支持取消、重试

---

## 10. 开发优先级

| 优先级 | 功能 | 接口 |
|--------|------|------|
| P0 | 健康检查 | `GET /health` |
| P0 | 论文导入 | `POST /ingest/*` |
| P0 | 文档列表 | `GET /documents` |
| P0 | 基础检索 | `POST /search` |
| P1 | 写作 Agent | `POST /agents/writing/*` |
| P1 | 风格 Agent | `POST /agents/style/*` |
| P1 | 文档详情 | `GET /documents/{id}` |
| P2 | 流式输出 | `WS /ws/chat` |
| P2 | 论文分析 | `POST /agents/analysis/*` |
| P3 | 高级过滤 | `POST /search` (filters) |

---

**文档版本：** v1.0  
**最后更新：** 2026-09-03
