# 极简 RAG 示例

基于纯 Python + OpenAI SDK + ChromaDB + pymupdf4llm 的本地 RAG 工具。

## 安装依赖

```bash
pip install openai chromadb pymupdf4llm python-dotenv
```

## 配置 .env

复制 `.env.example` 为 `.env`，并填写你的 API Key：

```bash
cp .env.example .env
```

编辑 `.env`：

```
API_KEY=你的API_KEY
BASE_URL=https://api.longcat.chat/openai/v1
MODEL=Longcat-2.0
EMB_MODEL=text-embedding-3-small
CHROMA_DB_DIR=./chroma_db
COLLECTION_NAME=paper_rag
```

> 如果当前 LLM API 不支持 embedding，可以单独配置支持 embedding 的 API：
> ```
> EMB_API_KEY=支持embedding的API_KEY
> EMB_BASE_URL=支持embedding的API地址
> EMB_MODEL=nomic-embed-text
> ```

## 测试 Embedding API

```bash
python test_embedding.py
```

如果成功，会输出向量长度和前 10 个数值。

如果失败，请检查：
- API 服务商是否支持 embeddings 接口
- EMB_MODEL 名称是否正确
- API Key 是否有 embedding 权限

## 使用方法

### 导入单篇 PDF

```bash
python mini_rag.py ingest input/papers/xxx.pdf
```

### 导入整个目录

```bash
python mini_rag.py ingest input/papers
```

### 单轮提问

```bash
python mini_rag.py ask "这篇论文的研究方法是什么？"
```

### 调试模式（查看完整 Prompt）

```bash
python mini_rag.py ask "这篇论文的研究方法是什么？" --debug
```

### 多轮对话

```bash
python mini_rag.py chat
```

多轮对话特性：
- 自动维护最近 3 轮对话记忆
- 自动重写检索词（补全代词如"它""这篇论文"）
- 输入 `exit`、`quit` 或 `q` 退出

### 清空向量库

```bash
python mini_rag.py reset
```

## 工作流程

1. **ingest**：PDF → pymupdf4llm 转换为 Markdown → 清洗 → 按页切块 → 质量过滤 → Embedding 向量化 → ChromaDB 存储
2. **ask**：问题 → Embedding 向量化 → ChromaDB 检索 6 个片段 → LLM 生成回答
3. **chat**：多轮对话 → 查询重写 → 检索 → 生成回答 → 更新对话历史
4. **reset**：删除 ChromaDB collection

## 文本清洗规则

| 过滤项 | 规则 |
|--------|------|
| 字符数 | >= 120 |
| 完整句子 | >= 2 个 |
| 英文单词 | >= 25 或中文 >= 50 |
| 数字比例 | <= 0.2 |
| 字母/汉字比例 | >= 0.5 |
| 短行比例 | <= 50%（行长度 < 15） |
| 图注噪声 | Figure/Table/Source 开头且无正文 |
| 图片文本 | HTML 注释标记 |
| HTML 标签 | `<mark>` 等标签在检索后清洗 |

## 防幻觉规则

LLM Prompt 严格要求：
- 只能根据编号片段回答
- 每个结论必须标注来源 `[片段X，第Y页]`
- 无依据的结论禁止写出
- 不使用模型已有知识补充
- 输出分两部分：可确认结论 + 无法确认内容

## 注意事项

- 如果当前 LLM API 不支持 embedding，可以单独配置支持 embedding 的 API（如 Ollama 本地模型）
- 向量数据存储在 `./chroma_db` 目录
- 每个 chunk 保存了来源文件路径和页码信息
- 修改切块或清洗逻辑后，请先 `reset` 再重新 `ingest`
