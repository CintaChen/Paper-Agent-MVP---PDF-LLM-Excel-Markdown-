# scholarAgent 项目交接文档

> 生成时间: 2026-09-10
> 生成者: scholar-orchestrator (总控 Agent)
> 交接对象: 新任 LLM / 后端工程师

---

## 1. 项目概况

| 项 | 说明 |
|---|---|
| **项目名称** | scholarAgent v2 — 论文写作辅助 RAG 系统 |
| **项目路径** | `E:\kunxuesuo\agent` |
| **Python** | 3.14.3 (.venv 独立环境) |
| **运行方式** | `env -u PYTHONPATH .venv/Scripts/python.exe ...` |
| **测试** | 56/56 通过 |

---

## 2. 技术栈

| 组件 | 技术 | 配置 |
|------|------|------|
| 向量数据库 | Milvus Lite (嵌入式) | `./milvus_lite.db`，无需部署服务端 |
| 关键词检索 | 自建 BM25 倒排索引 | 纯 Python，序列化到 JSON |
| 元数据存储 | SQLite | `storage_data/metadata.db` |
| LLM | glm-4.5-air (zai) | 标签提取、写作 Agent |
| Embedding | nomic-embed-text via Ollama | `localhost:11434/api/embed`，`keep_alive=1800` |
| Web 框架 | FastAPI | `/api/v1/` + `/api/v2/tags` |
| PDF 读取 | PyMuPDF (fitz) | — |

---

## 3. 核心模块

### 3.1 数据流水线

```
PDF → 读取清洗 → 父子分块 → 标签提取 → 向量化 → 存储
     readers/    processors/  rag/       core/    storage/
```

### 3.2 分块策略

| 函数 | 文件 | 说明 |
|------|------|------|
| `parent_child_chunking()` | `processors/chunker.py` | 父子分块（当前使用） |
| `fixed_size_chunks()` | `processors/chunker.py` | 固定大小（备用） |
| `paragraph_chunks()` | `processors/chunker.py` | 段落分块（备用） |

**⚠️ 已知问题：** `child_size=200` 导致 24 页论文切出 597 个 child，embedding 需 3-5 分钟。建议调大到 500。

### 3.3 标签提取（混合策略）

| 来源 | 用途 | 置信度 |
|------|------|--------|
| PDF 自带关键词 | topics | 1.0 |
| LLM 提取 | domain + methodology | 0.0-1.0 |
| 人工修正 | 任意 | 手动设置 |

**文件：**
- `rag/tag_prompts.py` — Prompt 模板
- `rag/tag_extractor.py` — 提取器 + `safe_parse_json` + `_clean_pdf_text`

**PDF 清洗：**
- `_clean_pdf_text()` 移除 BiDi 控制字符（`\u202a-\u202e`）、不可见分隔符（`\x02`）
- `extract_keywords_from_text()` 支持 `关键词：` / `Keywords:` / `Index Terms:` 等多种格式
- 分隔符兼容：`；; ，, 、 \x02` + 连续空格

### 3.4 参数规范体系（三层）

| 层 | 文件 | 用途 |
|---|---|---|
| API 层 | `config/params.py` | 请求参数约束（Pydantic Field） |
| 内部层 | `config/params.py` | 模块间传递（RetrievalConfig, AgentConfig） |
| 配置层 | `config/settings.py` | 环境变量（.env） |

### 3.5 API 路由

| 路由前缀 | 文件 | 说明 |
|----------|------|------|
| `/api/v1/ingest` | `api/routes/ingest.py` | 论文导入 |
| `/api/v1/documents` | `api/routes/documents.py` | 文档管理 |
| `/api/v1/search` | `api/routes/search.py` | 混合检索 |
| `/api/v1/agents` | `api/routes/agents.py` | Agent 调用 |
| `/api/v1/ws` | `api/routes/websocket.py` | 流式聊天 |
| `/api/v2/tags` | `api/routes/tags.py` | 标签管理（新增） |

---

## 4. 已知问题与修复记录

### 4.1 已修复

| 问题 | 根因 | 修复方案 | 文件 |
|------|------|----------|------|
| `list() takes no keyword arguments` | pymilvus 3.0.1 的 `IndexParams` 继承 `list`，不能用构造函数传参 | 改用 `index_params.add_index()` | `storage/vector_store.py` |
| `HTTP 400: tokenize refused` | Ollama 冷启动时 llama-server 端口未就绪 | 添加 `_warmup()` 预热 + 分批 8 条 + 重试前重新预热 | `core/embedding.py` |
| Milvus db locked | 上次进程卡死残留锁 | 删除 `milvus_lite.db` 目录 | 手动操作 |
| BiDi 字符导致关键词匹配失败 | PyMuPDF 提取文本插入不可见控制字符 | `_clean_pdf_text()` 清理 | `rag/tag_extractor.py` |
| `ContentTag` 未定义 | 类定义在 `Document` 之后 | 移到 `Document` 之前 | `core/document.py` |
| 废弃 `api/routes.py` 与新路由重复 | 旧代码未删除 | 删除文件 + 更新文档引用 | `api/routes.py` 已删 |

### 4.2 未解决

| 问题 | 影响 | 优先级 |
|------|------|--------|
| LLM 余额不足 | 标签提取跳过，但导入流程正常 | 🔴 充值即可 |
| child_size=200 导致 597 个 child | embedding 需 3-5 分钟/篇 | 🟡 P1 调大到 500 |
| 关键词粘连（如 `Retrieval-AugmentedGeneration(RAG)`） | 标签质量下降 | 🟡 P2 |
| LLM 置信度全部 = 1.0 | 无法区分高/低置信标签 | 🟡 P2 |
| evidence 截断 100 字（需求 60 字） | 超出需求规定 | 🟢 P3 |
| 两套关键词提取逻辑不统一 | `pdf_reader.py` 和 `tag_extractor.py` 各有一套 | 🟢 P3 |
| 前端未开发 | 无 Web UI | 🟡 P1 |

---

## 5. 文件结构

```
E:\kunxuesuo\agent\
├── agent/                     # Agent 层
│   ├── base_agent.py          # 基类（chat 支持 temperature/max_tokens）
│   ├── writing_agent.py       # 写作 Agent（使用 AgentConfig）
│   ├── style_agent.py         # 风格 Agent（使用 AgentConfig）
│   └── prompts.py             # 提示词模板
├── api/                       # API 层
│   ├── app.py                 # FastAPI 入口
│   ├── routes/                # 路由（ingest/documents/search/agents/websocket/tags）
│   ├── schemas/request.py     # 请求模型（继承 params 约束）
│   └── middleware/
├── config/                    # 配置层
│   ├── settings.py            # Pydantic Settings（.env）
│   ├── params.py              # 三层参数规范
│   └── logging.py
├── core/                      # 核心服务
│   ├── document.py            # Chunk + ContentTag + Document + SearchResult
│   ├── llm.py                # LLM 客户端
│   └── embedding.py           # Embedding 客户端（Ollama 原生 /api/embed）
├── processors/                # 文档处理
│   ├── chunker.py             # 分块策略（父子/固定/段落/滑动窗口）
│   └── cleaner.py             # 文本清洗 + evidence 截取
├── rag/                       # RAG 引擎
│   ├── ingest.py              # 导入流水线
│   ├── retrieve.py            # 混合检索（使用 RetrievalConfig）
│   ├── fusion.py              # RRF 融合
│   ├── rerank.py              # Cross-Encoder 重排序
│   ├── tag_extractor.py       # 标签提取器
│   ├── tag_prompts.py         # 标签 Prompt
│   └── hierarchical.py        # 层次化检索（预留）
├── readers/                   # 文档读取
│   └── pdf_reader.py          # PDF 读取 + 清洗 + 标题/摘要/关键词提取
├── storage/                   # 存储层
│   ├── vector_store.py        # Milvus Lite（MilvusClient API）
│   ├── keyword_store.py       # BM25 倒排索引
│   ├── metadata_store.py      # SQLite（documents + chunks + content_tags + parents）
│   └── base.py                # 抽象接口
├── tests/                     # 测试（56 个）
├── docs/                      # 文档
│   ├── ARCHITECTURE.md        # 架构说明
│   ├── API_DESIGN.md          # API 设计
│   ├── FRONTEND_PLAN.md       # 前端方案
│   ├── PARAMS.md              # 参数变更指南
│   ├── DATA_CLEANING.md       # 数据清洗逻辑
│   └── TAG_EVALUATION.md     # 标签验收报告
├── tasks/                     # 任务文档
│   ├── TAG_EXTRACTION_TASK.md # 标签提取任务书
│   └── REVIEW_CHECKLIST.md    # 验收清单
├── scripts/                   # 工具脚本
│   ├── test_tags.py           # 标签提取测试
│   ├── check_keywords_v2.py   # 关键词格式检查
│   └── gen_eval.py            # 验收报告生成
├── input/papers/              # 论文 PDF（6 篇）
├── storage_data/              # SQLite + BM25 索引
├── .env                       # 环境变量
├── pyproject.toml             # 依赖声明
└── milvus_lite.db/            # Milvus Lite 数据（自动生成）
```

---

## 6. 运行命令

```bash
# 运行测试（必须清除 PYTHONPATH）
cd "E:\kunxuesuo\agent"
env -u PYTHONPATH .venv/Scripts/python.exe -m pytest tests/ -v

# 导入论文
env -u PYTHONPATH .venv/Scripts/python.exe -c "
from rag.ingest import IngestPipeline
p = IngestPipeline()
p.ingest_directory('input/papers')
"

# 启动 API
env -u PYTHONPATH .venv/Scripts/python.exe -m uvicorn api.app:app --port 8000
```

---

## 7. 关键技术决策

| 决策 | 理由 |
|------|------|
| Milvus Lite 而非服务端 | 免部署，嵌入式运行，适合本地开发 |
| Ollama /api/embed 而非 /v1/embeddings | 原生端点支持 keep_alive 参数 |
| keep_alive=1800 | 30 分钟无调用自动卸载，平衡性能和资源 |
| 分批 8 条 embedding | 避免 Ollama llama-server tokenize 端口崩溃 |
| evidence: str 而非 dict | 每行一个 tag，SQL 友好，无冗余 |
| PDF 自带关键词优先 | 零成本、零幻觉、作者定义 |
| 三层参数体系 | API 约束 → 内部推导 → 环境覆盖 |

---

## 8. 下一步建议

| 优先级 | 任务 | 说明 |
|--------|------|------|
| 🔴 P0 | LLM 充值 | 恢复标签提取功能 |
| 🟡 P1 | 调大 child_size 到 500 | 减少 child 数量，加速 embedding |
| 🟡 P1 | 前端开发 | 基于 `docs/FRONTEND_PLAN.md` |
| 🟡 P1 | 生成 openapi.yaml | 前后端契约先行 |
| 🟡 P2 | 关键词粘连修复 | 在 `_clean_pdf_text` 中增加粘连模式分割 |
| 🟡 P2 | LLM 置信度差异化 | Prompt 中增加评分指南 |
| 🟢 P3 | 统一两套关键词提取逻辑 | `pdf_reader.py` 和 `tag_extractor.py` 合并 |

---

**文档结束。**
