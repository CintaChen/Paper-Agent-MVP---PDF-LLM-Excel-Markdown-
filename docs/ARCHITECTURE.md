# scholarAgent 后端架构说明

> 本文档面向架构评审者，说明后端的设计决策、数据流、模块边界与当前实现状态。
> **本次修订（2026-09-14）**：修正旧版与实际实现的偏差，补齐「工具化主 Agent」主线，
> 并如实标注新旧两条 Agent 主线并存的过渡态。

---

## 1. 项目定位

**scholarAgent** 是一个面向科研写作的论文辅助系统，核心能力：

- 批量导入论文 PDF，构建可检索的本地知识库；
- 混合检索（BM25 + 向量 + RRF + 重排序 + 父文档扩展）找相关片段；
- 基于检索结果与用户思路，调用 LLM 完成写作扩写、自评重写、行文润色。

**设计哲学：不做固定工作流，做工具化 Agent。**

> 主 Agent 在推理循环中自主决定调用哪个工具、调用几次；检索是「可选项」，
> 纯润色/纯改写场景不触发任何检索栈初始化。

**不做的事：**

- 不训练模型（调用外部 OpenAI 兼容 LLM API）；
- 不做多用户 / 权限（本地单用户工具）；
- 不做实时协作。

---

## 2. 分层架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                          入口层                                       │
│   cli/main.py (命令行)          api/app.py (FastAPI HTTP + WS)         │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                          Agent 层                                     │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ 主线：orchestrator.py —— 工具调用循环（think→选工具→观察→收敛） │  │
│  │        维护 WritingContext（框架/思路/已完成章节）              │  │
│  └────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │ 旧线：base_agent.py → writing_agent.py / style_agent.py         │  │
│  │        单次同步调用（保留兼容，强制依赖检索器）                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │  统一工具协议
                                │  (name / description / parameters / run)
┌───────────────────────────────▼──────────────────────────────────────┐
│                          工具层 tools/                                │
│  base.py(协议) → registry.py(注册·分发·错误回喂)                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │rag_search│ │draft_    │ │self_     │ │style_    │                │
│  │ (检索)   │ │expand    │ │critique  │ │polish    │                │
│  │          │ │ (扩写)   │ │ (自评)   │ │ (润色)   │                │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘                │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                          RAG 引擎层 rag/                              │
│  ingest(导入) · retrieve(检索) · fusion(RRF) · rerank(重排)          │
│  tag_extractor(标签) · tag_prompts(标签Prompt) · hierarchical(预留)   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                          能力层 core/                                 │
│  llm.py(含 function calling) · embedding.py · document.py(数据模型)   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                          存储层 storage/                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐    │
│  │ Milvus       │  │ BM25 倒排    │  │ SQLite                   │    │
│  │ Child 向量   │  │ 关键词索引   │  │ 文档/标签/Parent 正文    │    │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘    │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│                       处理层 readers/ · processors/                   │
│  pdf_reader(PDF读取+清洗+元信息) · chunker(分块) · cleaner(文本清洗)   │
└──────────────────────────────────────────────────────────────────────┘

配置层贯穿全局：config/ settings.py(.env) + params.py(三层参数规范) + logging.py
```

---

## 3. 三条核心主线

### 3.1 主线 A：RAG 导入管道（离线建库）

```
PDF 文件
   │  readers/pdf_reader.py: read()
   ▼
Document（含按段落切分的 chunks + 标题/DOI/摘要/关键词）
   │  清洗：移除 BiDi 控制字符、零宽字符、纯数字行
   ▼
rag/tag_extractor.py: ContentTagExtractor.extract()
   ├─ PDF 自带关键词 → topic 标签（confidence=1.0, source=pdf_keywords）
   ├─ LLM 兜底：Keywords 质量差时重新解析/从摘要概括（source=llm_fallback）
   └─ LLM 补充：domain + methodology（source=llm_extracted）
   │
   ▼
processors/chunker.py: parent_child_chunking()
   ├─ split_by_sections() 按章节标题切 Parent（语义完整，喂 LLM）
   └─ split_into_children() 将 Parent 切成 Child（用于检索）
   │
   ▼
core/embedding.py: EmbeddingClient.embed(children)
   │  Ollama 原生 /api/embed，分批 8 条，keep_alive=1800，预热+重试
   ▼
三库落盘（通过 chunk_id / parent_id 关联）
   ├─ MilvusStore.insert(children, vectors)   向量
   ├─ BM25Store.build_index + save_index     倒排索引 → JSON
   └─ SQLiteStore.save_parents + save_document   Parent 正文 + 文档 + 标签
```

**断点续传**：SQLite 的 `documents.status` 记录阶段
`pending → reading → tagging → chunking → embedding → completed | failed`。
`ingest_directory()` 遇 `completed` 跳过，`retry_failed()` 重试失败项。

### 3.2 主线 B：混合检索管道（在线查询）

```
用户查询 query
   │
   ├─ BM25 关键词召回 top_k ────────────► storage/keyword_store.py
   └─ 向量召回 top_k ── EmbeddingClient.embed_one ──► storage/vector_store.py
   │                        (Milvus, COSINE 度量)
   ▼
rag/fusion.py: reciprocal_rank_fusion()   RRF 融合  score = Σ 1/(k+rank)
   │
   ▼
rag/rerank.py: Reranker.rerank()          Cross-Encoder 重排
   │  失败/缺依赖时自动跳过（降级不中断）；支持 method="llm" 备选
   ▼
rag/retrieve.py: _expand_to_parents()     Child 命中 → parent_id 回查 SQLite 取整段
   │
   ▼
final_top_k 结果（SearchResult.source = bm25/vector/fusion/rerank/parent_expanded）
```

**参数职责分离**（关键设计）：`RetrievalAPIParams → RetrievalConfig.from_params()` 自动推导
各层 top_k，避免裸 `top_k` 在不同层级含义不一致：

- `final_top_k`：最终返回数
- `bm25_top_k` / `vector_top_k`：各源召回数（保证 ≥ final）
- `rerank_top_k`：重排后保留数
- `rrf_k`：RRF 平滑参数

### 3.3 主线 C：Agent 写作循环（工具化主 Agent，新主线）

`agent/orchestrator.py` 实现「think → 选工具 → 观察结果 → 判断收敛 → 继续/输出」。
对外提供两个入口：`run()`（同步返回最终结果）与 `run_stream()`（逐步产出事件，
供 WebSocket 流式接口使用），前者复用后者的循环逻辑，避免两套实现漂移。

```python
messages = [system_prompt, 【写作上下文】, *history?, user_message]
for iteration in 1..max_iterations(=8):
    response = llm.chat_messages(messages, tools=registry.schemas())
    if not response.has_tool_calls:
        return 结果(content, steps, messages, stopped_reason="completed")
    messages.append(response.as_assistant_message())
    for call in response.tool_calls:
        output = registry.execute(call.name, call.arguments)   # 出错不抛，回喂错误
        steps.append(ToolStep(...))
        messages.append({"role": "tool", "tool_call_id": call.id, "content": output})
# 超限
return 结果(..., stopped_reason="max_iterations")
```

**上下文一致性**由 `agent/context.py: WritingContext.to_prompt()` 保证：

- 主题 / 整体框架 / 作者思路 / 写作要求 → 全量注入；
- 已完成章节 → 最近 2 节保留全文（保证衔接），更早的只保留标题（控制长度）。

**四类工具（统一 Tool 协议）：**

| 工具 | 职责 | 是否依赖检索栈 |
|------|------|----------------|
| `rag_search` | 混合检索原文片段（惰性构造 HybridRetriever） | 是 |
| `draft_expand` | 按作者思路扩写指定章节 | 否（纯 LLM） |
| `self_critique` | 结构化自评：`passed/score/issues/suggestions` | 否（纯 LLM） |
| `style_polish` | 润色 / 简化 / 学术化（无检索） | 否（纯 LLM） |

**「写的达不到要点就重写」** 的实现：主 Agent 生成正文后调用 `self_critique`，
当 `passed=false` 时读取 `issues/suggestions` 重新调用 `draft_expand`，
回环由主 Agent 自主驱动，而非固定管线。

**工具错误处理**：`ToolRegistry.execute()` 捕获异常并返回 `{"error": ...}` 作为工具结果，
不中断主循环，让主 Agent 有机会自行纠正或换用其他工具。

**惰性依赖**：所有工具在 `run()` 被真正调用前不连接 Milvus / BM25 / LLM，
因此纯润色/纯改写场景不触发任何检索栈初始化。

### 3.4 旧 Agent 主线（保留兼容）

`agent/base_agent.py: BaseAgent` → `writing_agent.py` / `style_agent.py`，
为「单次同步调用」形态（`retrieve → build_context → chat`）。

> ⚠️ 旧主线在 `__init__` 中**强制**构造 `HybridRetriever()`，
> 导致纯润色也要初始化 Milvus / BM25 / SQLite。新能力应优先走工具层。

---

## 4. 核心契约

### 4.1 数据模型（`core/document.py`）

```
Chunk         id, text, page, start_pos, end_pos, metadata
ContentTag    tag_type(domain|topic|methodology), value, confidence,
              evidence, source(pdf_keywords|llm_fallback|llm_extracted|manual),
              needs_review
Document      id, title, authors, year, journal, doi, file_path,
              total_pages, chunks[], content_tags[], metadata
SearchResult  chunk, score, source, rank
```

### 4.2 工具协议（`tools/base.py`）

```python
class Tool(ABC):
    name: str
    description: str          # 决定 LLM 何时选它
    parameters: dict          # 参数 JSON Schema
    def run(self, **kwargs) -> Any: ...
    def to_openai_schema(self) -> dict: ...   # 转 OpenAI function calling
```

`tools/registry.py` 负责：`schemas()` 取全部工具 Schema、`execute()` 按名分发并兜底异常。

### 4.3 三层参数体系（`config/params.py`，详见 `docs/PARAMS.md`）

| 层 | 模型 | 用途 |
|----|------|------|
| 第 1 层 API | `RetrievalAPIParams` / `ChunkingAPIParams` / `AgentAPIParams` | 前端请求参数，带范围约束 |
| 第 2 层 内部 | `RetrievalConfig` / `AgentConfig` | 后端模块间传递，自动推导 |
| 第 3 层 配置 | `config/settings.py`（`.env`） | 环境 / 基础设施配置 |

### 4.4 统一响应格式

成功：

```json
{ "status": "success", "data": { }, "message": "", "duration_ms": 1234 }
```

失败：

```json
{ "status": "error", "error": { "code": "NOT_FOUND", "message": "文档不存在", "details": {} } }
```

---

## 5. 入口

| 入口 | 位置 | 说明 |
|------|------|------|
| CLI | `cli/main.py` | `ingest` / `ask` / `analyze(outline,paragraph)` / `style(polish,simplify,academic)` |
| HTTP | `api/app.py` | `/api/v1/{ingest,documents,search,agents,ws}` + `/api/v2/tags` |
| WebSocket | `api/routes/websocket.py` | `/api/v1/ws/chat`：检索 → 流式输出 token |
| 主 Agent | `api/routes/agent.py` | `POST /api/v1/agent/chat` + `WS /api/v1/agent/chat/ws`（orchestrator 惰性单例） |

**HTTP 路由一览：**

```
/api/v1/
├── /health          GET    健康检查
├── /ingest
│   ├── /file        POST   导入单个 PDF（按路径）
│   ├── /directory   POST   批量导入目录
│   └── /upload      POST   上传 PDF 文件
├── /documents
│   ├── /            GET    文档列表（分页 + 标题搜索）
│   ├── /stats       GET    文档统计
│   ├── /{doc_id}    GET    文档详情
│   └── /{doc_id}    DELETE 删除文档
├── /search
│   ├── /            POST   混合检索
│   ├── /vector      POST   仅向量检索
│   └── /keyword     POST   仅关键词检索
├── /agents
│   ├── /writing/outline     POST   写作大纲（旧线 WritingAgent）
│   ├── /writing/paragraph   POST   段落润色（旧线 WritingAgent）
│   ├── /style/polish        POST   风格优化（旧线 StyleAgent）
│   └── /analysis/analyze    POST   论文分析（⚠️ 目前为 TODO 占位）
├── /agent
│   ├── /chat        POST   工具化主 Agent（同步：正文 + 工具轨迹）
│   └── /chat/ws     WS     工具化主 Agent（流式：工具事件 + token + done）
└── /ws/chat         WS     流式聊天
/api/v2/tags
├── /{doc_id}        GET/PUT 查询 / 人工修正标签
├── /stats           GET     标签统计（领域分布 / 主题热度 / 方法论）
└── /search          GET     按标签搜索论文
```

---

## 6. 数据流全景

### 6.1 导入阶段

```
PDF → PDFReader.read() → Document(chunks)
        ├─→ ContentTagExtractor.extract() → content_tags
        ├─→ parent_child_chunking() → parents / children
        ├─→ EmbeddingClient.embed(children) → vectors
        │        └─→ MilvusStore.insert(children, vectors)
        ├─→ BM25Store.build_index(children) → save_index() (JSON)
        └─→ SQLiteStore.save_parents(parents) + save_document(doc)
```

### 6.2 检索阶段

```
query
 ├─→ BM25Store.search(query, top_k)          → [SearchResult(source="bm25")]
 ├─→ EmbeddingClient.embed_one(query)
 │      └─→ MilvusStore.search(vec, top_k)   → [SearchResult(source="vector")]
 ▼
reciprocal_rank_fusion(bm25, vector, k=60)   → [source="fusion"]
 ▼
Reranker.rerank(query, fused, top_k)         → [source="rerank"]
 ▼
_expand_to_parents(results)                  → [source="parent_expanded"]
 ▼
final_top_k
```

### 6.3 Agent 写作阶段（工具化主 Agent）

```
用户请求 + WritingContext（框架/思路/已完成章节）
   │
   ▼
Orchestrator.run()
   │  loop:
   │    ├─ LLM 判断：需文献依据？      → rag_search
   │    ├─              按思路扩写？    → draft_expand(references=检索结果)
   │    ├─              只要改写表达？  → style_polish
   │    └─              够不够要求？    → self_critique
   │  未通过 → 带 issues/suggestions 重写（回到 loop）
   ▼
交付正文（保留上下文供下一节使用）
```

### 6.4 旧线 Agent 阶段（单次同步）

```
WritingAgent.generate_outline(topic)
   ├─→ retriever.retrieve(topic, top_k=5)
   ├─→ build_context(results)  # "片段N (来源: xxx, 第N页)\n文本"
   ├─→ 注入提示词模板
   └─→ LLMClient.chat(system_prompt, user_prompt+context) → Markdown 大纲
```

---

## 7. 关键设计决策

### 7.1 为什么 RAG 独立成层？

RAG 拆成独立模块，Agent 通过 `HybridRetriever` 接口调用。好处：
检索逻辑变更（换库、加缓存）不影响 Agent；可单独测试 RAG（不启动 LLM）；
支持多种检索模式（纯向量 / 纯关键词 / 混合）。

### 7.2 为什么存储拆成三个？

| 方案 | 优点 | 缺点 |
|------|------|------|
| 只用 Milvus | 简单 | 不支持关键词检索，原文回查麻烦 |
| 只用 SQLite | 无外部依赖 | 向量检索性能差 |
| Milvus + SQLite | 向量 + 元数据 | 缺少关键词检索 |
| **Milvus + BM25 + SQLite** | 三者互补 | 维护成本略高 |

三者通过 `chunk_id` / `parent_id` 关联：Milvus 只存 Child 向量与文本；
BM25 存倒排索引；SQLite 存文档、标签与 Parent 整段正文。

### 7.3 为什么用 RRF 而不是加权求和？

| 策略 | 优点 | 缺点 |
|------|------|------|
| 加权求和 | 简单 | 需归一化，权重需调参 |
| 串联（先 BM25 后向量） | 分阶段 | 第一阶段错误会传递 |
| **RRF** | 无需调参，对分数尺度不敏感 | 只利用排名信息 |

BM25 与向量分数尺度不同（BM25 可能 0-100，向量 0-1），RRF 只依赖排名，避免归一化问题。

### 7.4 为什么 BM25 自建而不是 Elasticsearch？

论文库规模初期小，自建 BM25 纯 Python 够用；无需额外服务；索引可序列化为 JSON 快速恢复；
未来规模增长可替换为 ES。

### 7.5 为什么父子分块 + 父文档扩展？

Child（小块）检索精度高，但语义不完整；Parent（章节大块）语义完整，适合喂 LLM。
检索命中 Child 后按 `parent_id` 回查 Parent 整段，兼顾「检索准」与「上下文全」。

### 7.6 为什么 Embedding 直连 Ollama 原生 `/api/embed`？

Ollama 的 OpenAI 兼容端点 `/v1/embeddings` 会静默丢弃 `keep_alive`，导致模型被回收后
向陈旧 llama-server 端口转发 `/tokenize` 返回 400。改用原生 `/api/embed`（**单数**，
认 `keep_alive`）。注意别用复数 `/api/embeddings`：返回未归一化向量，会干扰 COSINE 排序。
即便常驻，Ollama 重启仍可能残留陈旧端口，故加 `_warmup()` 预热 + 分批 + 重试。

### 7.7 为什么用 Pydantic Settings / 三层参数？

类型安全（自动 `str→int/Path`）、启动即校验、有合理默认值、IDE 可补全；
三层参数把「前端约束 / 内部推导 / 环境配置」分离，避免同一 `top_k` 语义漂移。

---

## 8. 现状与结构性缺口

项目处于**新旧两条 Agent 主线并存的过渡态**，评审时需特别注意：

| # | 问题 | 影响 | 位置 |
|---|------|------|------|
| 1 | 新旧架构并行 | 文档/心智模型易混乱 | `agent/orchestrator.py` vs `agent/writing_agent.py` |
| 2 | BM25 重复存 chunk 正文 | 与 Milvus、SQLite 三份重复 | `storage/keyword_store.py` |
| 3 | 中文按字切分 | 关键词检索噪音大 | `storage/keyword_store.py` |
| 4 | 选题 / 论文分析子 Agent 缺失 | 能力不完整 | `api/routes/agents.py` 分析为 TODO |
| 5 | 两套关键词提取逻辑并存（解析已共用，Keywords 正则仍各一份） | 行为不一致、维护分裂 | `readers/pdf_reader.py`、`rag/tag_extractor.py` |
| 6 | 子 chunk 分块偏小（`parent_child_chunking` 默认 `child_size=200`，未接入 `settings`） | 单篇 child 数量多，embedding 耗时长 | `processors/chunker.py` |
| 7 | `api/routes/agents.py` 在模块级构造 `WritingAgent()` / `StyleAgent()` | 导入即构造 LLM 客户端（检索器已惰性） | `api/routes/agents.py` |
| 8 | `list_documents()` 为每篇加载全部 chunks / tags | 列表与统计接口 N+1 | `storage/metadata_store.py` |

已修复项（BM25 索引覆盖与重复分词、子 Agent 强制依赖检索器、导入状态落库、
孤儿行清理、tags 路由顺序、父文档缺失丢结果、重复导入 500、Agent 参数校验）
统一维护在 `README.md` 第 10.1 节。历史修复记录见 `docs/HANDOVER.md`。

---

## 9. 扩展路径

### Phase 1：当前状态 ✅
- RAG 引擎（Milvus + BM25 + SQLite）
- 混合检索（RRF 融合 + Cross-Encoder 重排 + 父文档扩展）
- 工具化主 Agent（Orchestrator + 四类工具 + 自评重写）
- 主 Agent 接入 HTTP / WebSocket（`/api/v1/agent/chat`）
- 旧线写作 / 风格 Agent（兼容保留）
- FastAPI（`/api/v1` + `/api/v2/tags`）+ CLI

### Phase 2：近期可加
- **主 Agent 接 API**：新增 `/api/v1/agent/chat`（含 WebSocket 流式）；
- **会话持久化**：`WritingContext` 与会话历史落库，支持跨请求续写；
- **选题子 Agent**：基于 `content_tags` 的领域 × 方法聚合；
- **检索层降噪**：修复 BM25 索引缺陷，评估其实际贡献后决定去留。

### Phase 3：中期规划
- 论文分析子 Agent；多模态（图表 OCR + 描述）；自动综述；查询改写；引用网络。

### Phase 4：长期演进
- 本地 LLM、增量索引、分布式 Milvus（百万级论文）。

---

## 10. 技术栈

| 组件 | 技术 | 版本要求 |
|------|------|----------|
| 语言 | Python | ≥3.10 |
| Web 框架 | FastAPI | ≥0.100 |
| 向量数据库 | Milvus Lite（嵌入式） | ≥2.3 |
| 元数据库 | SQLite | 内置 |
| 关键词检索 | 自建 BM25（纯 Python） | — |
| 融合策略 | RRF（倒数排名融合） | — |
| 重排序 | Cross-Encoder（可选）/ LLM | sentence-transformers ≥2.2 |
| LLM SDK | OpenAI（OpenAI 兼容接口） | ≥1.0 |
| Embedding | Ollama 原生 `/api/embed` | — |
| 数据模型 | Pydantic | ≥2.0 |
| 配置管理 | Pydantic Settings | ≥2.0 |
| PDF 读取 | PyMuPDF | ≥1.23 |
| 测试 | pytest | ≥7.0 |

---

## 11. 给前端 / 调用方的接口摘要

| 功能 | 方法 | 路径 |
|------|------|------|
| 导入论文 | POST | `/api/v1/ingest/file` |
| 上传论文 | POST | `/api/v1/ingest/upload` |
| 文档列表 | GET | `/api/v1/documents` |
| 混合检索 | POST | `/api/v1/search` |
| 写作大纲 | POST | `/api/v1/agents/writing/outline` |
| 段落润色 | POST | `/api/v1/agents/writing/paragraph` |
| 风格优化 | POST | `/api/v1/agents/style/polish` |
| 标签查询/修正 | GET/PUT | `/api/v2/tags/{doc_id}` |
| 标签统计 | GET | `/api/v2/tags/stats` |
| 流式聊天 | WS | `/api/v1/ws/chat` |
| 主 Agent（同步） | POST | `/api/v1/agent/chat` |
| 主 Agent（流式） | WS | `/api/v1/agent/chat/ws` |

---

**文档版本：** v2.0
**最后更新：** 2026-09-14
**修订说明：** 补齐「工具化主 Agent」主线，修正旧版仅描述同步 Agent 的偏差，新增现状缺口清单。
