# scholarAgent 参数规范

> 本文档是参数变更的同步指南。修改任何参数前，请阅读本文档。

---

## 1. 参数分层体系

| 层级 | 文件 | 用途 | 变更频率 |
|------|------|------|----------|
| **API 层** | `config/params.py` | 前端请求参数约束 | 低 |
| **内部层** | `config/params.py` | 后端模块间传递 | 低 |
| **配置层** | `config/settings.py` | 环境/基础设施配置 | 中 |
| **请求层** | `api/schemas/request.py` | 具体接口的参数默认值 | 中 |

---

## 2. 参数清单

### 2.1 检索参数

| 参数 | API 默认 | 内部推导 | 影响模块 | 约束 |
|------|----------|----------|----------|------|
| `top_k` | 10 | - | retrieve → rerank | 1-50 |
| `bm25_top_k` | - | max(final, 10) | BM25Store.search | 1-100 |
| `vector_top_k` | - | max(final, 10) | MilvusStore.search | 1-100 |
| `rerank_top_k` | - | = final | Reranker.rerank | 1-50 |
| `rrf_k` | 60 | - | Fusion.rrf | 1-200 |
| `use_bm25` | True | - | retrieve 流程 | bool |
| `use_vector` | True | - | retrieve 流程 | bool |
| `use_rerank` | True | - | retrieve 流程 | bool |

**参数关系图：**
```
API 层: top_k=10
    ↓
内部层: final_top_k=10
        bm25_top_k=max(10, 10)=10  ← BM25 召回
        vector_top_k=max(10, 10)=10 ← 向量召回
        rerank_top_k=10             ← 重排序后保留
```

### 2.2 分块参数

| 参数 | 默认 | 影响模块 | 约束 | 变更后果 |
|------|------|----------|------|----------|
| `chunk_size` | 500 | processors/chunker.py | 100-2000 | ⚠️ 需重建索引 |
| `chunk_overlap` | 50 | processors/chunker.py | 0-500 | ⚠️ 需重建索引 |
| `min_chunk_length` | 50 | processors/chunker.py | ≥10 | ⚠️ 需重建索引 |

### 2.3 Agent 参数

| 参数 | 默认 | 影响模块 | 约束 |
|------|------|----------|------|
| `top_k` | 5 | agent/writing_agent.py | 1-20 |
| `temperature` | 0.2 | core/llm.py | 0.0-2.0 |
| `max_tokens` | 8192 | core/llm.py | 100-32000 |
| `mode` | "polish" | agent/style_agent.py | polish\|simplify\|academic |
| `analysis_type` | "full" | agent/analysis_agent.py | full\|method\|results\|limitations |

---

## 3. 变更操作清单

### 场景 A：改 top_k（检索返回数）

**影响范围：** 仅 API 层

**操作步骤：**
1. 修改 `config/params.py` 中 `RetrievalAPIParams.top_k` 的 default
2. 无需重启，前端下次请求自动生效

**验证：**
```bash
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "top_k": 20}'
```

### 场景 B：改 chunk_size（分块大小）

**影响范围：** 全链路（分块 → 向量化 → 存储 → 检索）

**操作步骤：**
1. 修改 `config/params.py` 中 `ChunkingAPIParams.chunk_size` 的 default
2. **必须重建索引**：
   ```bash
   # 删除旧数据
   rm -rf storage_data/
   # 重新导入所有 PDF
   python -m cli.main ingest --dir ./input/papers
   ```
3. 验证检索结果是否正常

**⚠️ 警告：** 不重建索引会导致新旧 chunk 大小不一致，检索质量下降。

### 场景 C：改 temperature（LLM 温度）

**影响范围：** 所有 Agent 调用

**操作步骤：**
1. 修改 `config/params.py` 中 `AgentAPIParams.temperature` 的 default
2. 无需重启，Agent 下次调用自动生效

### 场景 D：改 rrf_k（RRF 平滑参数）

**影响范围：** 融合策略

**操作步骤：**
1. 修改 `config/params.py` 中 `RetrievalAPIParams.rrf_k` 的 default
2. 无需重启

**调参建议：**
- 值越大，排名差异的影响越小（更平滑）
- 值越小，排名靠前的结果权重越大
- 推荐范围：30-100

### 场景 E：新增一个参数

**操作步骤：**
1. 在 `config/params.py` 的对应类中添加字段
2. 在 `api/schemas/request.py` 中使用该参数
3. 在 `rag/retrieve.py` 或 `agent/*.py` 中传递该参数
4. 更新本文档的参数清单和变更操作

---

## 4. 参数约束校验

所有 API 请求参数都通过 Pydantic 自动校验：

```python
# 示例：非法参数会被自动拒绝
SearchRequest(top_k=999)  # ❌ 超过最大值 50
SearchRequest(top_k=-1)   # ❌ 低于最小值 1
StyleRequest(mode="xxx")  # ❌ 不在 Literal 范围内
```

**错误响应：**
```json
{
  "status": "error",
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数校验失败",
    "details": {
      "top_k": "Input should be less than or equal to 50"
    }
  }
}
```

---

## 5. 常见问题

### Q1：改了 settings.py 的参数但没生效？

**原因：** `settings.py` 的值只在启动时读取一次。如果 `params.py` 的 API 层默认值与 settings 不同，以 API 层为准。

**解决：** 修改 `config/params.py` 中的默认值，或通过环境变量覆盖。

### Q2：如何让不同 Agent 使用不同的 temperature？

**方法：** 调用时传入覆盖值：
```python
agent.generate_outline(topic, temperature=0.5)  # 覆盖默认 0.2
```

### Q3：前端需要知道参数约束吗？

**需要。** 前端应根据约束设置输入框的 min/max，避免用户输入非法值。
建议从 `openapi.yaml` 生成前端类型，自动获取约束信息。

---

## 6. 版本记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-09-04 | 初始版本，建立三层参数体系 |
