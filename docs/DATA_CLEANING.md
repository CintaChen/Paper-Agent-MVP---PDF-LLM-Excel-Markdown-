# 数据清洗逻辑说明

> 本文档描述 scholarAgent 项目中，论文 PDF 从入库到分块、标签提取全流程的数据清洗逻辑。

---

## 1. 总体流程

```
PDF 文件
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  readers/pdf_reader.py  — PDF 读取 + 初步清洗           │
│  ├─ _clean_raw_text()      页级清洗                     │
│  ├─ _extract_abstract()    智能提取摘要                  │
│  ├─ _extract_keywords()    关键词提取                    │
│  ├─ _extract_title()       多策略标题提取                │
│  └─ _extract_doi()         DOI 提取                     │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  processors/cleaner.py  — 通用文本清洗                   │
│  ├─ clean_text()           基础清洗                     │
│  ├─ normalize_whitespace() 空白规范化                   │
│  ├─ remove_header_footer() 去除页眉页脚                 │
│  └─ extract_evidence()     按句截取证据                 │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  processors/chunker.py  — 分块策略                       │
│  ├─ fixed_size_chunks()    固定大小分块                  │
│  ├─ paragraph_chunks()     按段落分块                    │
│  └─ sliding_window_chunks() 滑动窗口分块                 │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  rag/tag_extractor.py  — 标签提取清洗                    │
│  ├─ _clean_pdf_text()      深度清洗不可见字符            │
│  └─ extract_keywords_from_text()  正则匹配关键词          │
└─────────────────────────────────────────────────────────┘
```

---

## 2. 第一阶段：PDF 读取清洗

**文件：** `readers/pdf_reader.py`

### 2.1 页级清洗 `_clean_raw_text()`

每页 PDF 文本在提取后立即执行：

| 步骤 | 操作 | 正则 |
|------|------|------|
| 1 | 过滤纯数字行（PDF 提取产生的页码噪声 `000`, `001`, `002...`） | `^\\d{1,4}\\s*$` → 删除 |
| 2 | 过滤连续空白行（保留单换行） | `\\n{3,}` → `\\n\\n` |
| 3 | 过滤行首行尾空白 | `line.strip()` |
| 4 | 过滤空行 | 移除长度为 0 的行 |

### 2.2 智能摘要提取 `_extract_abstract()`

不再使用硬截断，改为定位章节边界：

1. 定位 `Abstract` / `摘要` / `Abstrac?t`（兼容换行断词）起始位置
2. 从起始位置向后搜索下一章节标题：
   - `\n\s*1[.\s]+\s*introduction`（一级标题"1 Introduction"）
   - `\n\s*keywords` / `\n\s*关键词`（关键词章节）
   - `\n\s*\d+[.\s]+\s*\w+`（数字编号章节）
   - `\n\s*I\s*ntroduction`（罗马数字章节）
3. 至少保留 100 字符，避免误判
4. 清理末尾不完整句子（最后一个句号在 70% 位置之后时截断）

### 2.3 关键词提取 `_extract_keywords_from_text()` + `_split_keywords()`

匹配模式（按顺序尝试）：

```
(?i)keywords?\s*[:：]\s*(.+?)(?=\n\n|abstract|introduction|$)
(?i)key\s*words?\s*[:：]\s*(.+?)(?=\n\n|abstract|introduction|$)
(?i)索引词\s*[:：]\s*(.+?)(?=\n\n|摘要|引言|$)
关键词\s*[:：]\s*(.+?)(?=\n\n|摘要|引言|$)
```

分隔符兼容（`_split_keywords()`）：

| 类型 | 字符 | 处理方式 |
|------|------|----------|
| 特殊符号 | `•` `▪` `●` `◆` `■` `□` `→` `←` `↑` `↓` | 替换为 `,` |
| 中间点号 | `·`（如 `keyword1 · keyword2`） | 替换为 `,` |
| 标准分隔符 | `,` `;` `，` `；` `\n` `\r` `\t` | 替换为 `,` |
| 连续空格 | 2 个及以上空格 | 替换为 `,` |

后处理：
- 分割后 `strip()` 去空
- 去重保序（大小写不敏感比较）

### 2.4 多策略标题提取 `_extract_title()`

按优先级尝试三种策略：

| 策略 | 方法 | 条件 |
|------|------|------|
| 1. 字号识别 | `_extract_title_by_fontsize()` | PyMuPDF 获取首页字号，取最大字号文本块 |
| 2. 启发式规则 | `_heuristic_extract_title()` | 过滤噪声（`Available online at`, `DOI:`, `Journal of` 等 18 种模式），取最长非噪声行 |
| 3. LLM 兜底 | `_extract_title_by_llm()` | 调用 LLM 提取 |

---

## 3. 第二阶段：通用文本清洗

**文件：** `processors/cleaner.py`

### 3.1 基础清洗 `clean_text()`

```python
# 多余空行（3+ 换行 → 2 换行）
text = re.sub(r"\n{3,}", "\n\n", text)
# 行首行尾空白
lines = [line.strip() for line in text.split("\n")]
# 过滤空行
lines = [line for line in lines if line]
return "\n".join(lines)
```

### 3.2 空白规范化 `normalize_whitespace()`

```python
# 连续制表符/空格 → 单个空格
text = re.sub(r"[ \t]+", " ", text)
# 3+ 换行 → 2 换行
text = re.sub(r"\n{3,}", "\n\n", text)
return text.strip()
```

### 3.3 证据截取 `extract_evidence()`

按句子边界截取，避免长句被截断：

1. 找到关键词位置（不区分大小写）
2. 向前找最近的句子开头（`。` `；` `\n` `. ` `; `）
3. 向后找最近的句子结尾
4. 返回完整句子

---

## 4. 第三阶段：分块策略

**文件：** `processors/chunker.py`

| 策略 | 函数 | 参数 | 说明 |
|------|------|------|------|
| 固定大小 | `fixed_size_chunks()` | chunk_size=500, chunk_overlap=50 | 步进式滑动窗口 |
| 段落分块 | `paragraph_chunks()` | min_length=50 | 按 `\n\n` 分割 |
| 滑动窗口 | `sliding_window_chunks()` | window_size=500, step=250 | 固定步长 |

**当前实际使用：** `paragraph_chunks()`（在 `pdf_reader._build_chunks()` 中按 `\n\n` 分割）

过滤条件：分块后文本长度 ≥ 50 字符（`len(para.strip()) >= 50`）

---

## 5. 第四阶段：标签提取清洗

**文件：** `rag/tag_extractor.py`

### 5.1 深度清洗 `_clean_pdf_text()`

PDF 提取文本时插入的不可见字符：

| 字符 | Unicode | 来源 | 处理 |
|------|---------|------|------|
| `\u202a` - `\u202e` | U+202A - U+202E | BiDi 方向控制字符 | 删除 |
| `\u2066` - `\u2069` | U+2066 - U+2069 | BiDi 方向控制字符（隔离） | 删除 |
| `\x00` - `\x08` | 控制字符 | PDF 内部标记 | 删除 |
| `\x0b` `\x0c` `\x0e` - `\x1f` | 控制字符 | PDF 内部标记 | 删除 |
| `\x7f` - `\x9f` | 控制字符 | PDF 内部标记 | 删除 |
| `\u0002` | Start of Text | PDF 分隔符 | 删除 |
| `\u200b` | Zero Width Space | 零宽空格 | 删除 |
| `\ufeff` | Zero Width No-Break Space / BOM | 字节顺序标记 | 删除 |

保留：`\n` `\r` `\t`（不在删除范围内）

### 5.2 关键词匹配（二次清洗后执行）

在深度清洗后的文本上执行正则匹配：

```python
patterns = [
    r"关键词[：:\s]\s*(.+?)(?:\n|$)",
    r"Key\s*words[：:\s]\s*(.+?)(?:\n|$)",
    r"Keywords[：:\s]\s*(.+?)(?:\n|$)",
    r"KEY\s*WORDS[：:\s]\s*(.+?)(?:\n|$)",
    r"Index\s*Terms[：:\s]\s*(.+?)(?:\n|$)",
]
```

注意：`[：:\s]` 允许冒号、中文冒号或空格均可匹配。

分隔符扩展：

```python
# 支持 ；; ，, 、 \x02 \u0002 作为分隔符
keywords = re.split(r"[；;，,、\x02\u0002]\s*", raw)
```

后处理：

```python
# 去空、去停用词、去太短（<2 字符）、去纯符号
keywords = [
    kw.strip()
    for kw in keywords
    if kw.strip()
    and kw.strip() not in STOP_WORDS
    and len(kw.strip()) >= 2
    and re.search(r"\w", kw.strip())
]
return keywords[:10]  # 最多取 10 个
```

### 5.3 停用词表

```python
STOP_WORDS = {"研究", "分析", "方法", "技术", "系统", "应用", "基于", "面向", "设计", "实现", "探讨", "发展", "理论", "模型"}
```

---

## 6. 清洗前后对比

### 6.1 原始 PDF 文本（示例）

```
000
001
002
‭Keywords‬‭:‬‭Retrieval-Augmented‬‭Generation‬‭(RAG),‬‭Enterprise‬‭AI,‬‭Compliance-regulated‬‭industries,‬
‭Semantic‬‭search,‬‭Hybrid‬‭query‬‭strategies,‬
```

### 6.2 第一阶段清洗后（`_clean_raw_text`）

```
Keywords: Retrieval-Augmented Generation (RAG), Enterprise AI, Compliance-regulated industries, Semantic search, Hybrid query strategies,
```

### 6.3 第四阶段深度清洗后（`_clean_pdf_text`）

```
Keywords: Retrieval-Augmented Generation (RAG), Enterprise AI, Compliance-regulated industries, Semantic search, Hybrid query strategies,
```

（BiDi 字符 `\u202c` `\u202d` 被移除）

### 6.4 最终提取结果

```python
[
    "Retrieval-Augmented Generation (RAG)",
    "Enterprise AI",
    "Compliance-regulated industries",
    "Semantic search",
    "Hybrid query strategies"
]
```

---

## 7. 已知问题

| 问题 | 原因 | 影响范围 |
|------|------|----------|
| 关键词粘连 | PDF 中关键词之间无分隔符（如 `Retrieval-AugmentedGeneration(RAG)`） | 部分 PDF |
| 双空格分隔 | 某些 PDF 用连续空格分隔关键词 | 部分 PDF |
| 置信度无差异 | LLM 输出全部 confidence=1.0 | 所有论文 |
| evidence 截断过长 | 代码中 `evidence[:100]`，需求是 60 字 | 所有论文 |
| topics 为空 | 无自带关键词 + LLM 不补充 topics | 部分论文 |

---

## 8. 配置参数

| 参数 | 文件 | 默认值 | 说明 |
|------|------|--------|------|
| `chunk_size` | `config/settings.py` | 500 | 分块大小 |
| `chunk_overlap` | `config/settings.py` | 50 | 分块重叠 |
| `min_chunk_length` | `processors/chunker.py` | 50 | 最小分块长度 |
| `STOP_WORDS` | `rag/tag_extractor.py` | 14 个中文停用词 | 关键词过滤 |
| 最大关键词数 | `rag/tag_extractor.py` | 10 | 每篇论文最多提取 |
| 最大 evidence 长度 | `rag/tag_extractor.py` | 100 字符 | 单个证据截断 |
| 最大引言长度 | `rag/tag_extractor.py` | 2000 字符 | LLM 输入截断 |
| 最大关键词扫描长度 | `rag/tag_extractor.py` | 5000 字符 | 关键词提取范围 |
