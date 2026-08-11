# Paper Agent - 个人文献批处理工具

> 基于 Python + 模型 API 的轻量版方案，面向个人研究者 / 研究生。
> 核心目标：批量处理论文文件，输出结构化文献表、Markdown 文献卡片和人工确认清单。

---

## 一、项目概览

本项目是一个基于 Python 和大模型 API 的个人文献批处理工具。用户将论文文件放入指定文件夹后，程序批量读取 PDF 文件，调用模型 API 提取文献信息和学术总结，最终生成：

- **JSON 结构化数据**：每篇论文的完整分析结果
- **Excel 文献总表**：所有论文的汇总表格
- **Markdown 文献卡片**：单篇论文的详细分析卡片
- **人工确认清单**：需要人工复核的论文列表

该工具的第一版目标是"可用、准确、轻量"，不追求复杂 Agent 编排，也不做前端页面、Notion 自动同步、Zotero 自动写入或 CAJ 原生解析。

---

## 二、目录结构

```
scholarAgent/
├── README.md                   # 项目说明文档（本文档）
├── paper_agent/                # 主程序：文献批处理工具
│   ├── .env                    # 环境变量配置（API Key 等）
│   ├── .env.example            # 环境变量模板
│   ├── main.py                 # 主入口脚本
│   ├── config.py               # 全局配置
│   ├── prompts.py              # 模型提示词模板
│   ├── readers/                # 文件读取模块
│   │   ├── __init__.py
│   │   └── pdf_reader.py       # PDF 文件读取器（支持分页）
│   ├── processors/             # 处理模块
│   │   ├── __init__.py
│   │   ├── paper_analyzer.py   # 论文分析处理器
│   │   └── output_writer.py    # 结果输出写入器
│   └── llm/                    # 大模型接口模块
│       ├── __init__.py
│       └── api_client.py       # LLM API 客户端封装
│
└── mini_rag/                   # 极简 RAG 示例（独立工具）
    ├── .env.example            # RAG 工具环境变量模板
    ├── mini_rag.py             # RAG 主脚本
    ├── test_embedding.py       # Embedding API 测试脚本
    └── README_mini_rag.md      # RAG 工具说明文档
```

---

## 三、各文件功能详解

### 3.1 入口与配置

#### `main.py` — 主入口脚本
- **功能**：程序的启动入口，串联整个批处理流程。
- **流程**：
  1. 加载 `Config` 配置
  2. 创建 `PaperAnalyzer`（论文分析器）和 `OutputWriter`（输出写入器）
  3. 调用 `analyzer.discover_papers()` 发现待处理的论文
  4. 逐篇调用 `analyzer.analyze(paper)` 进行分析
  5. 根据返回的 `needs_review` 标志，将论文分为"正常输出"和"待确认"两类
  6. 调用 `writer.write_all(results)` 输出正常结果
  7. 调用 `writer.write_review_list(review_items)` 输出人工确认清单
  8. 打印处理汇总信息

#### `config.py` — 全局配置
- **功能**：集中管理项目的所有配置参数，支持环境变量覆盖。
- **配置项**：
  - `input_dir`：论文输入目录（默认为 `input/papers`）
  - `output_dir`：结果输出目录（默认为 `output`）
  - `model`：使用的模型名称（默认 `Longcat-2.0`，可通过环境变量 `MODEL` 覆盖）
  - `api_key`：API 密钥（通过环境变量 `API_KEY` 读取）
  - `base_url`：API 基础 URL（通过环境变量 `BASE_URL` 覆盖）
  - `temperature`：模型温度（默认 `0.3`，保证输出稳定）
  - `max_tokens`：最大 token 数（默认 `4096`）
  - `evaluation_topic`：相关性评分的参照主题（默认 `AI赋能企业绿色转型`，可通过环境变量 `EVALUATION_TOPIC` 覆盖）

#### `.env` — 环境变量配置文件
- **功能**：存储 API Key 等敏感配置，避免硬编码。
- **内容示例**：
  ```
  API_KEY=your_api_key_here
  MODEL=LongCat-2.0
  BASE_URL=https://api.longcat.chat/openai/v1
  EVALUATION_TOPIC=AI赋能企业绿色转型
  ```

#### `prompts.py` — 模型提示词模板
- **功能**：定义与大模型交互的提示词。
- **内容**：
  - `SYSTEM_PROMPT`：系统角色设定，告知模型作为"学术论文分析助手"。
  - `ANALYSIS_PROMPT`：分析模板，要求输出结构化 JSON，包含：
    - 基础元数据：标题、作者、年份、期刊
    - 研究内容：背景、问题、目标、方法、发现、贡献、局限
    - 证据定位：研究方法、数据来源、主要发现必须包含页码和原文依据
    - 相关性评分：以 `evaluation_topic` 为参照主题

---

### 3.2 文件读取模块（readers/）

#### `readers/__init__.py` — 包初始化文件
- **功能**：将 `readers` 目录标记为 Python 包。

#### `readers/pdf_reader.py` — PDF 文件读取器
- **功能**：负责从输入目录中列出和读取 PDF 文件，支持分页读取。
- **依赖**：PyMuPDF（`fitz`）或 `pymupdf` 库。
- **方法**：
  - `list_papers()`：扫描 `input_dir` 目录下所有 `.pdf` 文件，返回文件路径列表。
  - `read(filepath)`：打开 PDF 文件，逐页提取文本内容并拼接返回（兼容旧接口）。
  - `read_paginated(filepath)`：读取 PDF 并保留分页信息，返回 `[{"page": 1, "text": "..."}, ...]`。
  - `format_for_prompt(pages)`：将分页内容格式化为带 `===== PAGE N =====` 标记的文本，发送给模型。

---

### 3.3 处理模块（processors/）

#### `processors/__init__.py` — 包初始化文件
- **功能**：将 `processors` 目录标记为 Python 包。

#### `processors/paper_analyzer.py` — 论文分析处理器
- **功能**：核心处理逻辑，协调读取器和 LLM 客户端完成论文分析，包含质量检查和人工确认标记。
- **依赖**：`Config`、`PDFReader`、`LLMClient`、提示词模板。
- **常量**：
  - `MIN_TEXT_LENGTH = 200`：文本质量阈值，少于该字符数视为疑似扫描版。
- **辅助函数**：
  - `extract_doi(text)`：从论文文本中提取 DOI，返回 `(doi, doi_status)`。
  - `normalize_evidence_field(value, field_name)`：规范化证据字段，兼容新旧格式。
  - `_normalize_pages(pages)`：规范化页码为整数列表。
- **方法**：
  - `discover_papers()`：调用 PDFReader 列出所有论文。
  - `analyze(paper)`：分析单篇论文，返回 `(result, needs_review, review_reasons)`：
    - 文本质量检查：< 200 字符标记为"疑似扫描版"，跳过 LLM 调用
    - JSON 解析失败时标记为"JSON 解析失败"
    - 元数据检查：标题/作者/年份未识别、DOI 未找到时标记待确认
    - 正常分析：调用 LLM 并解析结果

#### `processors/output_writer.py` — 结果输出写入器
- **功能**：将分析结果写入输出目录，支持多种格式。
- **辅助函数**：
  - `normalize_string_list(value)`：将各种输入统一为 `list[str]`，安全处理字符串形式的列表。
  - `format_list_for_markdown(items)`：将列表格式化为 Markdown 编号列表。
  - `format_list_for_excel(items)`：将列表格式化为 Excel 换行编号列表。
  - `format_evidence_single_for_markdown(value)`：格式化单个证据字段为 Markdown。
  - `format_evidence_list_for_markdown(items)`：格式化列表证据字段为 Markdown。
  - `format_evidence_list_for_excel(items)`：格式化列表证据字段为 Excel（只加页码）。
- **方法**：
  - `write(result)`：将单篇论文结果保存为 JSON。
  - `write_all(results)`：批量输出 JSON、Excel、Markdown。
  - `write_excel(results)`：输出 Excel 总表，自动调整列宽和格式。
  - `write_markdown(result)`：输出 Markdown 文献卡片。
  - `write_review_list(review_items)`：输出人工确认清单 `review_list.md`。
  - `_format_excel(filepath)`：调整 Excel 列宽和自动换行。

---

### 3.4 大模型接口模块（llm/）

#### `llm/__init__.py` — 包初始化文件
- **功能**：将 `llm` 目录标记为 Python 包。

#### `llm/api_client.py` — LLM API 客户端封装
- **功能**：封装对大模型 API 的调用。
- **当前实现**：使用 OpenAI SDK 格式，连接到 LongCat API。
- **方法**：
  - `__init__(config)`：接收 Config 对象，初始化 OpenAI 客户端。
  - `chat(system_prompt, user_prompt)`：发送系统提示词和用户提示词，返回模型生成的文本内容。

---

## 四、极简 RAG 示例（mini_rag/）

这是一个独立的极简 RAG 工具，用于理解 RAG 闭环。详见 [`mini_rag/README_mini_rag.md`](mini_rag/README_mini_rag.md)。

### 快速开始

```bash
# 安装额外依赖
pip install chromadb

# 配置环境变量
cp mini_rag/.env.example .env

# 测试 Embedding API
python mini_rag/test_embedding.py

# 导入 PDF
python mini_rag/mini_rag.py ingest input/papers

# 提问
python mini_rag/mini_rag.py ask "这篇论文的研究方法是什么？"
```

### 功能
- `ingest`：将 PDF 切块、向量化后存入 ChromaDB
- `ask`：根据问题检索相似段落，调用 LLM 生成回答
- `reset`：清空向量库

```
用户放入 PDF → main.py 启动
    ↓
Config 加载配置（读取 .env 文件）
    ↓
PaperAnalyzer.discover_papers() 扫描 input/papers 目录
    ↓
对每篇论文：
    ├── PDFReader.read_paginated() 读取分页内容
    ├── 文本质量检查
    │   ├── < 200 字符 → 标记"疑似扫描版"，跳过 LLM
    │   └── ≥ 200 字符 → 继续正常流程
    ├── 格式化 ANALYSIS_PROMPT（带 PAGE 标记）
    ├── LLMClient.chat() 调用模型 API
    ├── JSON 解析
    │   ├── 成功 → 规范化各字段
    │   └── 失败 → 标记"JSON 解析失败"
    ├── 元数据检查（标题/作者/年份/DOI）
    └── 返回 (result, needs_review, review_reasons)
    ↓
分类：
    ├── 正常论文 → results 列表
    └── 待确认论文 → review_items 列表
    ↓
OutputWriter.write_all(results) 输出：
    ├── papers_summary_{timestamp}.json
    ├── papers_summary_{timestamp}.xlsx
    └── {论文标题}.md（每篇一个）
    ↓
OutputWriter.write_review_list(review_items) 输出：
    └── review_list.md（人工确认清单）
    ↓
打印处理汇总
```

---

## 五、输出文件说明

| 文件 | 说明 |
|------|------|
| `papers_summary_{timestamp}.json` | 所有论文的结构化 JSON 数据 |
| `papers_summary_{timestamp}.xlsx` | Excel 文献总表，包含所有字段 |
| `{论文标题}.md` | 单篇论文的 Markdown 文献卡片 |
| `review_list.md` | 人工确认清单，列出需要复核的论文 |

### Excel 表格列说明

| 列名 | 说明 |
|------|------|
| original_filename | 原始文件名 |
| extracted_title | 模型提取的论文标题 |
| authors | 作者列表（中文分号连接） |
| year | 发表年份 |
| journal | 期刊名称 |
| doi | DOI |
| doi_status | DOI 状态（已找到/未找到/待确认） |
| research_background | 研究背景 |
| research_question | 研究问题 |
| research_objective | 研究目标 |
| research_method | 研究方法（含页码） |
| model_or_framework | 模型或理论框架 |
| data_source | 数据来源（含页码） |
| experimental_design | 实验设计 |
| analysis_process | 分析流程 |
| key_findings | 主要发现（含页码） |
| contributions | 研究贡献 |
| limitations_reported | 作者明确提出的局限 |
| limitations_inferred | 模型推断的局限 |
| relevance_score | 相关性评分 |
| path | 文件路径 |

### Markdown 文献卡片结构

```markdown
# 论文标题

## 一、基本信息
- 作者：...
- 年份：...
- 期刊/来源：...
- DOI：...
- DOI 状态：...

## 研究背景
## 研究问题
## 研究目标
## 研究方法（含证据页码和原文依据）
## 模型或理论框架
## 数据来源（含证据页码和原文依据）
## 实验或研究设计
## 分析流程
## 主要发现（含证据页码和原文依据）
## 研究贡献
## 研究局限
### 作者明确提出的局限
### 模型基于论文内容推断的局限
## 相关性评分
## 文件路径
```

---

## 六、环境依赖

### paper_agent（主程序）
- Python 3.10+
- PyMuPDF (`pymupdf`) — PDF 文本提取
- OpenAI SDK (`openai`) — 模型 API 调用
- pandas — Excel 输出
- openpyxl — Excel 格式调整
- python-dotenv — 环境变量加载

### mini_rag（RAG 示例，可选）
- chromadb — 向量数据库

### 安装依赖

```bash
# 主程序依赖
pip install pymupdf openai pandas openpyxl python-dotenv

# RAG 示例额外依赖
pip install chromadb
```

---

## 七、准确性原则

- 找不到 DOI 时，必须输出"未找到"，不能猜测
- 题名、作者、年份、期刊无法确认时，必须标记"未识别"或"待确认"
- 模型输出必须以原文内容为依据，不能凭常识补全文献信息
- 扫描版 PDF 或文本提取质量差时，必须进入人工确认清单
- 如果模型返回 JSON 解析失败，程序应保存原始响应，便于人工检查
- 证据页码只能来自论文正文中的 PAGE 标记，不得猜测
- 相关性评分必须以 `evaluation_topic` 为统一参照主题

---

## 八、版本路线

| 版本 | 状态 | 说明 |
|------|------|------|
| MVP v1.0 | 已完成 | 基础批处理流程，PDF 读取 + LLM 分析 + JSON 输出 |
| v1.1 | 已完成 | 增加 Excel 总表、Markdown 文献卡片 |
| v1.2 | 已完成 | 增加元数据提取（作者/年份/期刊/DOI）、证据定位 |
| v1.3 | 已完成 | 增加人工确认清单、文本质量检查、分页读取 |
| 后续规划 | 待开发 | 综述素材汇总、Notion/Zotero 同步 |

---

## 九、改动记录

| 日期 | 改动内容 | 说明 |
|------|----------|------|
| 2026-07-21 | 初始版本 | 项目结构搭建，完成 main.py / config.py / prompts.py / pdf_reader.py / paper_analyzer.py / output_writer.py / api_client.py |
| 2026-07-28 | v1.2 更新 | 增加元数据提取（作者/年份/期刊/DOI）、证据定位（页码+原文依据）、相关性评分统一主题 |
| 2026-07-28 | v1.3 更新 | 增加分页读取、文本质量检查、人工确认清单、列表字段格式化 |
| 2026-07-29 | v1.4 更新 | 新增 mini_rag/ 极简 RAG 示例；整理文件结构，将 RAG 工具归入独立子目录 |
