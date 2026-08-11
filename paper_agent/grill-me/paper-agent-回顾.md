# Paper Agent 项目全景回顾

> 最后更新：2026-08-02
> 目的：快速回忆项目全貌，用于 Obsidian 笔记

---

## 一、项目是什么

**Paper Agent** 是一个个人文献批处理工具，帮助研究生/研究者批量处理学术论文 PDF，自动提取结构化信息并生成多种格式输出。

**核心理念**：可用、准确、轻量。不追求复杂 Agent 编排，专注解决文献阅读和整理的核心痛点。

---

## 二、两个独立工具

| 工具 | 目录 | 用途 |
|------|------|------|
| **paper_agent** | `paper_agent/` | 主程序：批量分析 PDF → JSON/Excel/Markdown |
| **mini_rag** | `mini_rag/` | 独立 RAG 示例：理解检索增强生成闭环 |

---

## 三、paper_agent 主程序

### 3.1 技术栈

- **PDF 解析**：`pymupdf4llm`（将 PDF 转为 Markdown，保留论文结构）
- **LLM 调用**：OpenAI SDK 兼容接口（默认 LongCat API）
- **输出格式**：JSON / Excel / Markdown

### 3.2 文件结构

```
paper_agent/
├── .env                    # API Key 等配置
├── .env.example            # 环境变量模板
├── main.py                 # 主入口
├── config.py               # 全局配置
├── prompts.py              # 模型提示词（分步执行指令）
├── readers/
│   └── pdf_reader.py       # PDF 读取（支持分页）
├── processors/
│   ├── paper_analyzer.py   # 核心分析逻辑
│   └── output_writer.py    # 多格式输出
└── llm/
    └── api_client.py       # LLM 客户端封装
```

### 3.3 核心流程

```
PDF → pymupdf4llm 转 Markdown → 分页提取 → LLM 分析 → 结构化 JSON
                                    ↓
                              质量检查 → 标记待确认论文
                                    ↓
                         ┌─────────┴─────────┐
                         ↓                   ↓
                    正常论文              待确认论文
                         ↓                   ↓
                  JSON/Excel/Markdown    review_list.md
```

### 3.4 输出字段

| 类别 | 字段 |
|------|------|
| 元数据 | extracted_title, authors, year, journal, doi, doi_status |
| 研究内容 | research_background, research_question, research_objective |
| 方法与设计 | research_method (含 evidence_pages, evidence_excerpt) |
| 数据 | data_source (含证据定位) |
| 发现 | key_findings (每个结论独立证据定位) |
| 贡献与局限 | contributions, limitations_reported, limitations_inferred |
| 评分 | relevance_score（以 evaluation_topic 为统一参照） |

### 3.5 关键设计决策

**为什么用 pymupdf4llm 而不是纯文本提取？**
- Markdown 保留论文的标题层级和段落结构
- 自动忽略图表中的散点坐标噪声
- 更适合 LLM 理解论文结构

**为什么分页标记 `===== PAGE X =====`？**
- 让模型能定位证据页码
- 回答时可标注来源 [片段2，第7页]

**为什么 limitations 要分 reported 和 inferred？**
- reported：作者明确写的局限（客观）
- inferred：模型推断的潜在局限（需谨慎对待）
- 混用会导致用户无法区分事实和猜测

**为什么 evaluation_topic 要写死？**
- 确保所有论文的评分标准一致
- 不同论文的相关性可以用同一把尺子衡量

### 3.6 人工确认清单

以下情况的论文会被标记为"待确认"：
- 提取文本 < 200 字符（疑似扫描版）
- JSON 解析失败
- 标题/作者/年份未识别
- DOI 未找到

---

## 四、mini_rag 工具

### 4.1 技术栈

- **PDF 解析**：`pymupdf4llm`
- **Embedding**：Ollama nomic-embed-text（本地，768 维）
- **向量数据库**：ChromaDB（本地持久化 `./chroma_db`）
- **LLM**：OpenAI SDK 兼容接口

### 4.2 文件结构

```
mini_rag/
├── .env.example            # 环境变量模板
├── mini_rag.py             # 主脚本
├── test_embedding.py       # Embedding API 测试
└── README_mini_rag.md      # 说明文档
```

### 4.3 命令

```bash
python mini_rag.py ingest input/papers      # 导入 PDF
python mini_rag.py ask "问题"                # 提问
python mini_rag.py ask "问题" --debug        # 调试模式
python mini_rag.py reset                     # 清空向量库
```

### 4.4 文本清洗规则

| 过滤项 | 规则 |
|--------|------|
| 字符数 | >= 120 |
| 完整句子 | >= 2 个 |
| 英文单词 | >= 25 或中文 >= 50 |
| 数字比例 | <= 0.2 |
| 字母/汉字比例 | >= 0.5 |
| 短行比例 | <= 50%（行长度 < 15） |
| 图注噪声 | Figure/Table/Source 开头且无正文 |
| 图片文本 | `<!-- Start of picture text -->` 标记 |

### 4.5 LLM Prompt 防幻觉规则

```
1. 只能根据编号片段回答
2. 每个结论必须标注来源 [片段X，第Y页]
3. 无依据的结论禁止写出
4. 不使用模型已有知识补充
5. 输出分两部分：可确认结论 + 无法确认内容
```

### 4.6 temperature 设置

- **paper_agent**: 0.3（允许一定创造性）
- **mini_rag**: 0.0（完全确定性，防止幻觉）

---

## 五、环境配置

### 5.1 .env 变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| API_KEY | LLM API 密钥 | - |
| BASE_URL | LLM API 地址 | LongCat |
| MODEL | LLM 模型 | Longcat-2.0 |
| EMB_API_KEY | Embedding API 密钥 | 复用 API_KEY |
| EMB_BASE_URL | Embedding API 地址 | 复用 BASE_URL |
| EMB_MODEL | Embedding 模型 | text-embedding-3-small |
| EVALUATION_TOPIC | 相关性评分参照主题 | AI赋能企业绿色转型 |
| CHROMA_DB_DIR | ChromaDB 存储路径 | ./chroma_db |
| COLLECTION_NAME | ChromaDB 集合名 | paper_rag |

### 5.2 依赖

```bash
# paper_agent
pip install pymupdf4llm openai pandas openpyxl python-dotenv

# mini_rag（额外）
pip install chromadb
```

---

## 六、已知问题与限制

### 6.1 paper_agent

| 问题 | 说明 |
|------|------|
| 无记忆功能 | LLM API 无状态，每次调用独立 |
| 无法跨会话保存 | 历史分析结果不持久化 |
| 长论文截断 | 全文发送给 LLM，可能超出上下文窗口 |

### 6.2 mini_rag

| 问题 | 说明 |
|------|------|
| 检索噪声 | 图表坐标、图注可能混入检索结果 |
| LLM 幻觉 | 模型可能根据已有知识而非检索内容回答 |
| 单轮对话 | 不支持多轮追问 |
| embedding 依赖 | Ollama 需要本地运行 |

---

## 七、下一步计划

### 短期

- [ ] 实现多轮对话记忆（短期：历史对话传入）
- [ ] 支持跨文献综述生成
- [ ] 论文书写助手（基于 RAG 的 outline/evidence/cite）

### 中期

- [ ] 本地 Embedding 模型支持（sentence-transformers）
- [ ] 按主题分 Collection 存储
- [ ] 论文对比分析功能

### 长期

- [ ] Notion/Zotero 同步
- [ ] 前端界面
- [ ] 多用户支持

---

## 八、关键代码片段回忆

### 8.1 分页标记（传给模型）

```python
def format_for_prompt(pages):
    parts = []
    for p in pages:
        parts.append(f"===== PAGE {p['page']} =====\n{p['text']}")
    return "\n\n".join(parts)
```

### 8.2 证据定位结构

```json
{
  "research_method": {
    "text": "面板数据回归",
    "evidence_pages": [8],
    "evidence_excerpt": "We employ Model (1) to examine..."
  }
}
```

### 8.3 列表字段安全解析

```python
def normalize_string_list(value):
    """安全处理字符串形式的列表，禁止 eval"""
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, (list, tuple)):
                return [str(v) for v in parsed]
        except (ValueError, SyntaxError):
            pass
        return [value]
    return [str(v) for v in value] if isinstance(value, list) else []
```

### 8.4 JSON 清洗（防止 Markdown 代码块污染）

```python
def clean_json_text(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group(0)
    return text
```

---

## 九、常用命令速查

```bash
# ========== paper_agent ==========
cd paper_agent
.venv\Scripts\activate
python main.py

# ========== mini_rag ==========
cd mini_rag
python test_embedding.py                              # 测试 embedding
python mini_rag.py ingest input/papers/xxx.pdf       # 导入单篇
python mini_rag.py ingest input/papers               # 导入目录
python mini_rag.py ask "问题"                         # 提问
python mini_rag.py ask "问题" --debug                 # 调试模式
python mini_rag.py reset                             # 清空向量库
```

---

## 十、相关资源

- **LongCat API**: https://api.longcat.chat
- **pymupdf4llm**: https://pypi.org/project/pymupdf4llm/
- **ChromaDB**: https://docs.trychroma.com/
- **Ollama**: https://ollama.com/
