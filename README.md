# scholarAgent — 论文写作 Agent

面向科研写作的 Agent 系统。核心不是固定工作流，而是**工具化 Agent**：主 Agent 在推理循环中自主决定调用哪个子 Agent / 哪个工具（是否需要检索文献、是否需要润色 skill），最终服务于一个目标——**按你给的框架和思路把论文写出来，写不到位就重写**。

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| 工具化，不做工作流 | 主 Agent 自主规划，工具按需调用，不预设固定管线 |
| Agent 可被 Agent 调用 | 子 Agent（选题、大纲、扩写、润色）对主 Agent 暴露为工具 |
| 检索可选 | 需要文献支撑才走 RAG；纯改写/润色不碰检索栈 |
| 自评重写 | 生成后检查是否覆盖要点、逻辑是否连贯，不达标则回到循环重写 |
| 上下文一致 | 你的框架、思路、已写章节全程可见，后续段落不跑偏 |

---

## 2. 核心使用场景

这是系统要真正解决的问题，也是验收标准：

```
用户：这是论文整体框架 + 我这一节的思路
  │
  ▼
主 Agent 判断当前需要什么
  ├── 需要文献依据？        → 调用 rag_search 工具（混合检索）
  ├── 只需要按思路扩写？    → 调用 draft_expand 工具
  ├── 只要改写表达？        → 调用 style_polish skill（无检索）
  ├── 想换个选题方向？      → 调用子 Agent topic_agent
  └── 不知道够不够？        → 调用 self_critique 自评
  │
  ▼
生成草稿 → 自评（要点覆盖 / 逻辑连贯 / 有无编造）
  ├── 不达标 → 带上问题重新生成（循环）
  └── 达标   → 返回，保留上下文供下一节使用
```

**要点**：用户提供的是「框架 + 思路」，Agent 负责扩写；「达不到要点就重写」由自评循环保证，而不是靠一次 prompt 撞运气。

---

## 3. 架构

### 3.1 目标架构（工具化主 Agent）

```
┌───────────────────────────────────────────────────────────────┐
│                   Orchestrator（主 Agent）                     │
│   think → 选工具 → 观察结果 → 判断是否收敛 → 继续 / 输出        │
│   维护：用户框架、个人思路、已完成章节、检索缓存                 │
└───────────────┬───────────────────────────────────────────────┘
                │  统一工具协议（name / args / returns）
   ┌────────────┼────────────────┬────────────────┐
   ▼            ▼                ▼                ▼
┌────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
│ 检索类  │  │ 写作类      │  │ 质检类      │  │ 子 Agent    │
│rag_    │  │draft_      │  │self_       │  │topic_agent │
│search  │  │expand      │  │critique    │  │outline_    │
│tag_    │  │outline_    │  │style_check │  │agent       │
│query   │  │build       │  │            │  │            │
└───┬────┘  └────────────┘  └────────────┘  └────────────┘
    │
    ▼
┌───────────────────────────────────────────────────────┐
│ 能力层                                                 │
│ HybridRetriever(Milvus + BM25 + RRF + Rerank)          │
│ LLMClient（tool calling + 多轮 messages）               │
│ Skill 层（纯提示词，无检索依赖）                        │
└───────────────────────────────────────────────────────┘
```

### 3.2 实现状态

| 能力 | 状态 | 位置 |
|------|------|------|
| PDF 导入（父子分块 / 标签提取 / 断点续传） | 已完成 | `rag/ingest.py`、`processors/chunker.py` |
| 混合检索（BM25 + 向量 + RRF + 重排 + 父文档扩展） | 已完成 | `rag/retrieve.py`、`rag/fusion.py`、`rag/rerank.py` |
| 写作大纲 / 段落润色 / 风格优化（单次同步调用） | 已完成 | `agent/writing_agent.py`、`agent/style_agent.py` |
| 内容标签体系（domain / topic / methodology） | 已完成 | `rag/tag_extractor.py`、`api/routes/tags.py` |
| FastAPI（`/api/v1` + `/api/v2/tags`） | 已完成 | `api/app.py` |
| CLI | 已完成 | `cli/main.py` |
| LLM function calling（`tools` / 多轮 messages） | 已完成 | `core/llm.py` |
| 工具注册表 + 统一工具协议 | 已完成 | `tools/base.py`、`tools/registry.py` |
| 检索 / 润色 / 扩写 / 自评 四类工具 | 已完成 | `tools/` |
| 主 Agent 工具循环（Orchestrator） | 已完成 | `agent/orchestrator.py` |
| 主 Agent HTTP / WebSocket 接口（`/api/v1/agent/chat`） | 已完成 | `api/routes/agent.py` |
| 写作上下文（框架 / 思路 / 成稿） | 已完成 | `agent/context.py` |
| 会话持久化（消息 + 上下文落库，凭 `session_id` 续写） | 已完成 | `storage/metadata_store.py`、`api/routes/agent.py` |
| 导入进度反馈（后台任务 + WebSocket 事件流） | 已完成 | `api/ingest_tasks.py`、`api/routes/ingest.py` |
| 前端界面（6 个页面，构建产物由 FastAPI 托管） | 已完成 | `web/` |
| 自评重写（`self_critique` 工具，回环由主 Agent 自主驱动） | 已完成 | `tools/critique_tools.py` |
| 选题子 Agent | 规划中 | 待建 |
| 论文分析子 Agent（结构化抽取 + 长文 map-reduce + 分片并发） | 已完成 | `agent/analysis_agent.py` |

> **依赖惰性初始化**：所有路由的重量级依赖（Milvus / BM25 / SQLite / LLM / 检索器 / 导入流水线）都封装为 `get_xxx()` 惰性单例，首次请求时才构造。`import api.app` 不连接任何服务，测试也可安全地挂载整个应用。

---

## 4. 项目结构

```
agent/
├── config/          # 配置中心（settings 环境变量 / params 参数规范）
├── core/            # 核心服务（LLM、Embedding、数据模型）
├── rag/             # RAG 引擎（导入、检索、融合、重排序、标签提取）
├── storage/         # 存储层（Milvus Lite、BM25、SQLite）
├── agent/           # Agent 层（主 Agent 循环、写作、风格、写作上下文）
├── tools/           # 工具层（协议、注册表、检索/写作/润色/自评工具）
├── readers/         # 文档读取（PDF）
├── processors/      # 文档处理（分块、清洗）
├── cli/             # 命令行工具
├── api/             # FastAPI 服务
│   ├── routes/      # ingest / documents / search / agents / websocket / tags
│   └── schemas/     # 请求模型（继承 params 约束）
├── web/             # 前端（Vite + React + TS + Tailwind；构建产物由 FastAPI 托管）
│   └── src/         # 页面 / 组件 / API 封装 / WebSocket hook
├── scripts/         # 工具脚本（标签验收、BM25 重建等）
├── tests/           # 测试
└── docs/            # 设计文档
```

> 主 Agent 循环位于 `agent/orchestrator.py`，工具集位于 `tools/`；新增能力只需实现 `Tool` 接口并注册。

---

## 5. 快速开始

> 只想看命令行怎么用？直接跳到 **§6 CLI 使用说明**。

### 5.1 安装依赖

```bash
pip install -e ".[api]"
# 可选：启用 Cross-Encoder 重排序
pip install -e ".[api,rerank]"
```

### 5.2 配置环境变量

```bash
cp .env.example .env   # 若不存在则直接创建 .env
```

最小可用配置（本地 Ollama 提供 Embedding，OpenAI 兼容接口提供 LLM）：

```ini
# LLM
API_KEY=your-key
BASE_URL=https://api.longcat.chat/openai/v1
MODEL=Longcat-2.0

# Embedding（本地 Ollama）
EMB_BASE_URL=http://localhost:11434
EMB_MODEL=nomic-embed-text
```

```bash
ollama pull nomic-embed-text
```

### 5.3 导入论文

无需 Docker：向量库使用 **Milvus Lite（嵌入式）**，数据落在 `./milvus_lite.db`。

```bash
python -m cli.main ingest ./input/papers
```

通过 API 导入时，上传是**异步**的：立即返回 `task_id`，导入在后台线程执行，进度既能轮询也能流式订阅。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/ingest/upload` | 上传 PDF，立即返回 `task_id`（不再阻塞等待） |
| GET | `/api/v1/ingest/tasks` | 最近导入任务列表 |
| GET | `/api/v1/ingest/tasks/{id}` | 任务快照：`status` / `stage` / `percent` / `events` |
| WS | `/api/v1/ingest/ws/{id}` | 进度事件流：`progress`（含百分比与文字日志）→ `done` |

导入阶段依次为 `reading → tagging → chunking → embedding → storing → completed`，
其中 `embedding` 会按批次上报 `向量化 8/40`、`16/40` … 的细粒度进度。
多个上传任务会**串行执行**（Milvus Lite 不支持并发写），后到的任务先显示「排队中」。

### 5.4 提问 / 检索

```bash
python -m cli.main ask "人工智能在教育中的应用"
```

### 5.5 写作辅助

```bash
python -m cli.main analyze outline --topic "AI赋能教育"
python -m cli.main analyze paragraph --topic "AI赋能教育" --draft "草稿内容"
python -m cli.main style polish "待润色的段落"
```

### 5.6 启动 API

```bash
python -m uvicorn api.app:app --port 8000
# 打开 http://localhost:8000/docs
```

### 5.7 使用主 Agent（工具化写作）

```python
from agent.orchestrator import Orchestrator
from agent.context import WritingContext

context = WritingContext(
    topic="AI 赋能个性化学习",
    framework="1 引言  2 相关工作  3 方法  4 实验  5 结论",
    ideas="引言要突出个性化学习的痛点与本文贡献",
)
context.add_section("引言", "（已写好的引言……）")

orch = Orchestrator()
result = orch.run(
    "请扩写《相关工作》，重点对比已有方法的两点不足",
    context=context,
)
print(result.content)
print([s.tool for s in result.steps])   # 主 Agent 自主选择的工具轨迹
```

主 Agent 会自行决定是否调用 `rag_search`、用 `draft_expand` 扩写、再用 `self_critique` 自评，不达标则带着 `issues` 重写。

也可通过 HTTP 调用（同步返回正文 + 工具轨迹）：

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "请扩写《相关工作》",
    "context": {"topic": "AI 赋能教育", "framework": "引言/相关工作/方法/结论", "ideas": "对比已有方法不足"}
  }'
```

响应里的 `session_id` 即会话凭证。下次**只传 `session_id`** 就能续接——服务端会自动恢复历史消息与写作上下文，不必再把 `history` / `context` 重传一遍：

```bash
curl -X POST http://localhost:8000/api/v1/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "继续扩写《方法》一节", "session_id": "上一步返回的 ID"}'
```

持久化落在 `storage_data/metadata.db` 的三张表：`sessions` / `session_messages` / `writing_contexts`。只落库 user / assistant 消息，system 提示与上下文每轮重新注入，避免重复膨胀。

会话管理接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/agent/sessions` | 列出会话（按最近活跃排序，`?limit=` 1–200） |
| GET | `/api/v1/agent/sessions/{id}` | 会话详情：消息 + 写作上下文（刷新页面后恢复界面用） |
| DELETE | `/api/v1/agent/sessions/{id}` | 删除会话及其消息与上下文 |

### 5.8 前端界面

前端位于 `web/`（Vite + React + TypeScript + Tailwind CSS）。构建产物由 FastAPI **同源托管**，所以只启动后端就能用：

```bash
python -m uvicorn api.app:app --port 8000
# 浏览器打开 http://localhost:8000
```

开发模式（热更新，`/api` 自动代理到 8000，含 WebSocket）：

```bash
cd web
npm install
npm run dev        # http://localhost:5173
```

构建（产物 `web/dist`，FastAPI 检测到即自动托管）：

```bash
cd web
npm run build
```

页面：仪表盘 · 写作助手 · 文献检索 · 文档库 · 文档详情（含论文分析）· 风格优化。

流式调用：`WS /api/v1/agent/chat/ws`，先推送 `tool_call` / `tool_result` 事件，再分片推送 `token`，最后推送 `done`（同样返回 `session_id`）。

---

## 6. CLI 使用说明

> 本项目**没有注册控制台入口**（`pyproject.toml` 里没有 `[project.scripts]`），
> 统一用 `python -m cli.main` 调用。所有命令都在**项目根目录**下执行。

### 6.1 前置条件

| 依赖 | 用途 | 怎么确认 |
|------|------|----------|
| Python ≥ 3.10，且已 `pip install -e .` | 运行 CLI | `python -c "import cli.main"` |
| `.env` 配好 LLM（`API_KEY`/`BASE_URL`/`MODEL`） | `ingest`（提标签）、`analyze`、`style` | 见 §5.2 |
| Ollama 提供 Embedding | `ingest`、`ask` 的向量检索 | `ollama list` 里有 `nomic-embed-text` |
| 已导入论文 | `ask` / `analyze` 才有检索结果 | `python -m cli.main ingest ./input/papers` |

Windows 下若用项目内虚拟环境，把 `python` 换成 `.venv\Scripts\python.exe`：

```powershell
.\.venv\Scripts\python.exe -m cli.main --help
```

### 6.2 命令总览

| 命令 | 作用 | 需要 LLM | 需要检索栈 |
|------|------|:--------:|:----------:|
| `ingest` | 导入 PDF（单文件 / 目录），支持断点续传与重试 | 是（提标签） | 是 |
| `ask` | 检索本地论文库，列出相关片段 | **否** | 是 |
| `analyze outline` | 基于文献生成写作大纲 | 是 | 是 |
| `analyze paragraph` | 撰写 / 优化段落 | 是 | 是 |
| `style` | 润色 / 简化 / 学术化文本 | 是 | **否** |

`python -m cli.main --help` 看总览；子命令加 `--help` 看参数（例如 `python -m cli.main ingest --help`）。

### 6.3 ingest：导入论文

```bash
# 导入整个目录（已完成的论文自动跳过）
python -m cli.main ingest ./input/papers

# 只导入单个 PDF
python -m cli.main ingest ./input/papers/xxx.pdf

# 强制重新导入（忽略"已完成"状态）
python -m cli.main ingest ./input/papers --force

# 重试之前失败的论文（无需提供路径）
python -m cli.main ingest --retry

# 清空向量 / 关键词 / 元数据（危险：论文库会被清空）
python -m cli.main ingest --reset

# 清空后重新导入
python -m cli.main ingest --reset ./input/papers
```

| 参数 | 说明 |
|------|------|
| `path` | PDF 文件或目录；`--reset` / `--retry` 时可省略 |
| `--reset` | 清空向量库 + BM25 索引 + SQLite 元数据 |
| `--force` | 忽略断点续传，强制重新处理 |
| `--retry` | 重试状态为 `failed` 的论文 |

注意：

- 导入**逐篇**进行，单篇失败不影响其他论文，失败项可用 `--retry` 重试；
- 耗时主要在 Embedding（Ollama），一篇 20 页论文通常几十秒到数分钟；
- 文档 ID 由文件路径的 MD5 生成，**移动/重命名文件会被当成新论文**；
- 目录导入**只扫一层**（`*.pdf`），不递归子目录。

### 6.4 ask：检索片段

```bash
python -m cli.main ask "人工智能在教育中的应用"
python -m cli.main ask "个性化学习" --top-k 10
```

输出为「来源 / 页码 / 分数 + 片段前 200 字」。**该命令只做检索、不调用 LLM**，适合用来确认论文库导入成功、检索能命中。结果为空时，先查 `ingest` 是否成功、Ollama 是否可用。

### 6.5 analyze：写作大纲 / 段落

```bash
# 生成写作大纲（会检索相关文献作为依据）
python -m cli.main analyze outline --topic "AI 赋能教育"

# 换用不同的检索查询词
python -m cli.main analyze outline --topic "AI 赋能教育" --query "个性化学习 自适应"

# 撰写 / 优化段落（可带当前草稿）
python -m cli.main analyze paragraph --topic "AI 赋能教育" --draft "当前草稿内容……"
```

| 参数 | 说明 |
|------|------|
| `mode` | `outline`（大纲）或 `paragraph`（段落），必填 |
| `--topic` | 必填，研究主题 |
| `--query` | 可选，检索查询词（默认取 `--topic`） |
| `--draft` | 仅 `paragraph`：当前草稿，可留空 |
| `--top-k` | 检索文献数量，默认 5 |

### 6.6 style：行文风格优化

```bash
python -m cli.main style polish "本文提出了一种……"
python -m cli.main style simplify "这段文字比较啰嗦……"
python -m cli.main style academic "我认为这个方法很好……"
```

| 参数 | 说明 |
|------|------|
| `mode` | `polish` 润色 / `simplify` 简化 / `academic` 学术化 |
| `text` | 待优化文本（含空格时用引号包起来） |

该命令**不访问论文库**，纯改写表达，所以论文库为空时也能用。

### 6.7 典型工作流

```bash
# 1) 配置（只需一次）：cp .env.example .env 并按需修改
# 2) 导入论文
python -m cli.main ingest ./input/papers
# 3) 确认检索可用
python -m cli.main ask "你的主题关键词"
# 4) 大纲 → 段落 → 润色
python -m cli.main analyze outline --topic "你的主题"
python -m cli.main analyze paragraph --topic "引言" --draft "……"
python -m cli.main style academic "……"
```

### 6.8 常见问题

| 现象 | 原因 / 处理 |
|------|-------------|
| `路径不存在` | `path` 写错，或目录里没有 `*.pdf`（只扫一层，不递归） |
| `ingest` 什么都没做 | 该论文状态已是 `completed`；用 `--force` 强制重导 |
| 检索结果为空 | 论文未导入成功，或 Ollama 的 Embedding 模型没启动 |
| Embedding 报 400 / 连接被拒 | Ollama 未运行或模型被卸载，执行 `ollama pull nomic-embed-text` |
| LLM 命令报鉴权错误 | `.env` 的 `API_KEY` / `BASE_URL` / `MODEL` 配错 |
| 改了 `CHUNK_SIZE` 但分块没变 | 该变量未接入实际导入路径，见 §8 说明 |

---

## 7. 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python ≥ 3.10 |
| 向量数据库 | Milvus Lite（嵌入式，无需服务端） |
| 关键词检索 | 自建 BM25 倒排索引（纯 Python） |
| 融合策略 | RRF（倒数排名融合） |
| 重排序 | Cross-Encoder（可选）/ LLM |
| 元数据 | SQLite |
| LLM | OpenAI SDK（OpenAI 兼容接口，可切任意后端） |
| Embedding | Ollama 原生 `/api/embed`（如 `nomic-embed-text`） |
| Web 框架 | FastAPI |
| PDF 读取 | PyMuPDF |

---

## 8. 配置说明

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `API_KEY` | LLM API Key | `testapi` |
| `BASE_URL` | LLM API 地址 | `https://api.longcat.chat/openai/v1` |
| `MODEL` | LLM 模型 | `Longcat-2.0` |
| `EMB_BASE_URL` | Embedding 服务地址 | 空（回退到 `BASE_URL`） |
| `EMB_MODEL` | Embedding 模型 | `text-embedding-3-small` |
| `MILVUS_URI` | Milvus Lite 数据路径 | `./milvus_lite.db` |
| `MILVUS_COLLECTION` | 集合名 | `paper_rag` |
| `SQLITE_PATH` | 元数据数据库 | `./storage_data/metadata.db` |
| `BM25_INDEX_PATH` | BM25 索引文件 | `./storage_data/bm25_index.json` |
| `CHUNK_SIZE` | 分块大小 | `500` |
| `RETRIEVE_TOP_K` | 检索结果数 | `10` |
| `USE_RERANK` | 是否启用重排序 | `True` |

> ⚠️ `CHUNK_SIZE` / `CHUNK_OVERLAP` 目前只被 `fixed_size_chunks()` 使用，**该函数未接入导入流水线**。
> 实际导入走 `parent_child_chunking()`，其分块参数是函数默认值
> （`parent_size=1000`、`child_size=200`、`overlap=50`），**不读取 `settings`**。
> 也就是说：改 `.env` 里的 `CHUNK_SIZE` 不会影响实际分块。

> ⚠️ `MILVUS_URI` 这个**环境变量名与 pymilvus 自身的全局配置同名**。
> 写进 `.env` 没问题（`.env` 只被本项目读取）；但如果把它导出成真正的环境变量，
> pymilvus 会在 `import` 阶段解析本地路径并抛 `Illegal uri` 而启动失败。
> 需要临时切换 Milvus 库时，请直接改 `settings.milvus_uri` 或 `.env`，不要 `export` 它。

参数分层的完整规范见 `docs/PARAMS.md`。

---

## 9. 路线图

按依赖顺序推进：

1. **把主 Agent 接到 API**（已完成）：`POST /api/v1/agent/chat` 与 `WS /api/v1/agent/chat/ws`，见 `api/routes/agent.py`。
2. **会话持久化**（已完成）：`sessions` / `session_messages` / `writing_contexts` 三张表，凭 `session_id` 续接历史与写作上下文。
3. **选题子 Agent**：基于 `content_tags` 的领域 × 方法聚合，产出候选选题与文献支撑。
4. **检索层降噪**：BM25 索引缺陷已修（含重复分词）；剩余去重正文存储、中文分词方案，并评估 BM25 的实际贡献后决定去留。
5. **论文分析子 Agent**（已完成）：`agent/analysis_agent.py`，长文走 map-reduce，分片并发。
6. **前端**：参考 `docs/FRONTEND_PLAN.md`。

---

## 10. 已知问题

> 本节按「已修复 / 待修复」分区，只反映**当前实现**的状态。
> 历史问题与修复过程见 `docs/HANDOVER.md`。

### 10.1 已修复

| 问题 | 修复方式 | 位置 |
|------|----------|------|
| BM25 索引 `chunk_map` 被逐篇覆盖，而倒排索引累加 | `build_index` 改为增量合并，新增 `doc_lengths`，检索时容错脏索引 | `storage/keyword_store.py` |
| BM25 检索时对每个候选重新分词 | 预存 `doc_lengths`，检索直接查表 | `storage/keyword_store.py` |
| 历史版本导致 BM25 索引与向量库不同步 | 新增 `scripts/rebuild_bm25.py`，从 Milvus 重建索引（无需重新 embedding） | `scripts/rebuild_bm25.py` |
| 子 Agent 强制依赖检索器 | `BaseAgent.retriever` 改为惰性属性，首次检索才构造 | `agent/base_agent.py` |
| 重复保存文档把导入状态打回 `pending` | `INSERT OR REPLACE` 改为 UPSERT，保留 `status` / `error_message` | `storage/metadata_store.py` |
| 应用级单例 `SQLiteStore` 跨线程报 `ProgrammingError` | 连接改用 `check_same_thread=False` | `storage/metadata_store.py` |
| 删除文档残留 `content_tags` / `parents` 孤儿行 | 级联清理子表 | `storage/metadata_store.py` |
| 新文档中途失败时状态不落库、无法重试 | 导入前先登记 `documents` 行（`register_document`） | `rag/ingest.py`、`storage/metadata_store.py` |
| `/api/v2/tags/stats`、`/search` 被 `/{doc_id}` 抢先匹配 | 静态路径提前注册 | `api/routes/tags.py` |
| 父文档缺失时检索结果被整批丢弃 | 降级保留 Child | `rag/retrieve.py` |
| 重复导入已完成论文返回 500 | 识别 `doc is None`，返回 `skipped: true` | `api/routes/ingest.py` |
| `/api/v1/agents/*` 因 `temperature=None` 校验失败返回 500 | 新增 `AgentAPIParams.with_overrides()`，丢弃 None 覆盖项 | `config/params.py`、`agent/writing_agent.py`、`agent/style_agent.py` |
| README / 架构文档与实现存在偏差 | `docs/ARCHITECTURE.md` 重写为 v2.0，README 状态表与本节同步 | `docs/ARCHITECTURE.md` |

### 10.2 待修复

| 问题 | 影响 | 位置 |
|------|------|------|
| BM25 重复存储 chunk 正文 | 与 Milvus、SQLite 三份重复 | `storage/keyword_store.py` |
| 中文按字切分 | 关键词检索噪音大 | `storage/keyword_store.py` |
| 两套关键词提取逻辑并存（解析已共用，Keywords 正则仍各有一份） | 行为不一致、维护分裂 | `readers/pdf_reader.py`、`rag/tag_extractor.py` |
| 子 chunk 分块偏小（`parent_child_chunking` 默认 `child_size=200`，且未接入 `settings`） | 单篇论文 child 数量多，embedding 耗时长 | `processors/chunker.py` |
| PDF 解析未抽取 authors / year / journal | 分析结果与引用场景中这三个字段恒为空 | `readers/pdf_reader.py` |
| `list_documents()` 为每篇论文加载全部 chunks / tags | 列表与统计接口 N+1 | `storage/metadata_store.py` |
| `/upload` 未校验上传文件名 | 路径穿越（本地工具，风险低） | `api/routes/ingest.py` |
