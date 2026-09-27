# 让 scholarAgent 连上 Milvus

> 本目录是我新增的辅助文件，没有改动你任何已有源码。
> 诊断结论 + 修改清单如下，代码请自己动手改。

---

## 一、诊断结果（已实测）

| 项 | 状态 | 说明 |
|---|---|---|
| pymilvus | 已装 3.0.1 | `.venv` 里已有 |
| `storage/vector_store.py` | 已完整实现 | `MilvusStore` 逻辑齐全 |
| Ollama embedding | 运行中 | `nomic-embed-text`，实测 **768 维** |
| Milvus 服务 | **未运行** | Docker Desktop 没启动，19530 连不上 |
| C 盘剩余 | 52G / 366G | 不建议再往 C 盘塞镜像 |

**结论：你的代码早就写好了，唯一缺的就是 Milvus 服务本身。**

---

## 二、推荐方案：Milvus Lite（零 Docker，数据落 E 盘）

Milvus Lite 是 pymilvus 自带的单机文件模式，不需要 Docker、不占 C 盘。
我已实测验证：**建集合、写入、语义检索全部跑通**。

适合你的场景：论文库几百到几万条 chunk，完全够用。等哪天数据量上百万再迁 Docker 也不迟。

### 需要你改的地方（共 3 处）

#### 改动 1：`config/settings.py` 第 29-34 行

**推荐用相对路径 + 统一解析**（完整写法见下一节"二点五"），这样项目搬家不用改配置：

```python
    # === Milvus 配置 ===
    milvus_uri: str = Field(
        default="storage_data/milvus.db", alias="MILVUS_URI"
    )
    milvus_host: str = Field(default="localhost", alias="MILVUS_HOST")
    milvus_port: str = Field(default="19530", alias="MILVUS_PORT")
    milvus_collection: str = Field(
        default="paper_rag", alias="MILVUS_COLLECTION"
    )
```

> 想快点跑通就直接写绝对路径 `default="E:/kunxuesuo/agent/storage_data/milvus.db"`，代价是项目换盘或换目录时要改代码。

> 为什么加 `milvus_uri` 而不是直接改 host：留一个开关，以后想切 Docker 只改 `.env` 就行，代码不用动。

---

## 二点五、相对路径的正确写法（重要）

**相对路径是相对"进程当前工作目录"解析的，不是相对项目目录。**

实测（`_milvus_bootstrap\test_relpath.py`，从两个目录各跑一次）：

| 运行位置 | 写法 A（直接写相对路径） | 写法 B（按项目根解析） |
|---|---|---|
| 从 `E:\kunxuesuo\agent` 跑 | `E:\kunxuesuo\agent\storage_data` 正确 | 正确 |
| 从 `E:\kunxuesuo` 跑 | `E:\kunxuesuo\storage_data` **跑偏** | 正确 |

写法 A 的后果：换个目录跑命令，Milvus 就在那里新建一个空库，你会以为"数据丢了"。
**你现在的 `storage_dir` / `sqlite_path` / `bm25_index_path` 全都有这个隐患。**

### 改法（`config/settings.py`）

第 1-4 行加 `field_validator` 导入，并定义项目根目录：

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from pathlib import Path

# 项目根目录：config/ 的上一级，始终指向项目本身
PROJECT_ROOT = Path(__file__).resolve().parent.parent
```

在 `Settings` 类里加两个校验器（字段定义之后、`__init__` 之前）：

```python
    @field_validator("milvus_uri")
    @classmethod
    def _abs_uri(cls, v):
        p = Path(v)
        return str(p if p.is_absolute() else (PROJECT_ROOT / p).resolve())

    @field_validator("storage_dir", "sqlite_path", "bm25_index_path",
                     "input_dir", "output_dir")
    @classmethod
    def _abs_path(cls, v):
        p = Path(v)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()
```

好处：
- `.env` 写相对路径（`MILVUS_URI=storage_data/milvus.db`）或绝对路径都能正确解析
- 项目搬到 D 盘、换台机器，一行配置都不用改
- 从任何目录跑 `python -m cli.main ...` 都不会跑偏

---

#### 改动 2：`storage/vector_store.py` 第 36 行

现在这行：

```python
        connections.connect(alias="default", host=self.host, port=self.port)
```

改成：

```python
        connections.connect(alias="default", uri=settings.milvus_uri)
```

**就这一行**。我已实测 `connections.connect(uri=...)` 能直接连本地文件，你现有的 `Collection` / `search` / `insert` 全部代码一行都不用动。

#### 改动 3：`.env` 里加一行

```ini
MILVUS_URI=E:/kunxuesuo/agent/storage_data/milvus.db
```

（`config/settings.py` 的 `extra="ignore"` 保证你留着旧的 `MILVUS_HOST` 也不冲突）

### 改完怎么验证

```bash
cd E:\kunxuesuo\agent
.venv\Scripts\python.exe _milvus_bootstrap\verify_after_patch.py
```

看到 `全部通过` 就说明接上了。然后直接跑你的导入：

```bash
.venv\Scripts\python.exe -m cli.main ingest ./input/papers
```

---

## 三、强烈建议顺手改：索引参数

你现在是 `IVF_FLAT` + `nlist=128`（`vector_store.py` 第 80-85 行）。
我实测时 Milvus 直接打了警告：

```
WARNING clustering 3 points to 3 centroids: please provide at least 117 training points
```

意思是：你要求聚成 128 个簇，但数据太少，实际只聚成 3 个，索引形同虚设。
表现就是检索分数区分度极差（实测 0.5917 / 0.5857 / 0.5741，几乎分不出好坏）。

**建议改成 HNSW**，小数据量下召回更稳，而且不用手调 `nprobe`：

`vector_store.py` 第 80-85 行：

```python
        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 200},
        }
```

第 117 行搜索参数配套改成：

```python
        search_params = {"metric_type": "COSINE", "params": {"ef": 64}}
```

> `ef` 越大召回越全、越慢。64 是常用起点，调到 128 精度更高。

---

## 三点五、论文量变大后的索引策略（你关心的"量大"问题）

### 先算你的量级

实测你现有 6 篇论文：163 页、63.5 万字，按 `CHUNK_SIZE=500` 约 **1,271 chunks**，平均 **211 chunks/篇**。

| 论文数 | chunk 量级 | 768 维向量体积 |
|---|---|---|
| 6 篇（现状） | ~1.3 千 | ~4 MB |
| 100 篇 | ~2.1 万 | ~62 MB |
| 500 篇 | ~10.6 万 | ~310 MB |
| 2000 篇 | ~42 万 | ~1.2 GB |

**Milvus Lite 官方建议上限 100 万条**。所以到 2000 篇论文都还能用，不必急着上 Docker。

### 实测数据（N=5000，768 维，以 FLAT 暴力结果为标准答案）

```
索引                    参数            召回@10
--------------------------------------------------
FLAT (基准)             -               100.0%
IVF_FLAT nlist=128    nprobe=8          25.3%   <-- 你现在的 nprobe=10 就在这一档
IVF_FLAT nlist=128    nprobe=32         54.0%
IVF_FLAT nlist=1024   nprobe=64         72.3%
HNSW M=16             ef=128            76.7%   <-- 最优
```

**这里有个必须重视的结论**：你 `vector_store.py` 第 117 行写的是 `nprobe=10`，
配合 `nlist=128` 实测召回只有 **25% 上下** —— 意味着 **四分之三的相关内容根本没被召回**，
后面对接的 RRF 融合和重排序再强也救不回来（没召回的东西没法排序）。

同时也已验证：**Milvus Lite 支持 HNSW**，可以放心用。

### 分档选型建议

| 数据量 | 索引 | 参数 | 检索参数 |
|---|---|---|---|
| < 5 万 | **HNSW** | `M=16, efConstruction=200` | `ef=64`（要精度就 128） |
| 5 万 - 50 万 | **HNSW** | `M=32, efConstruction=360` | `ef=128` |
| 50 万+ | IVF_PQ 或 DISKANN | 见下 | — |

**优先选 HNSW 而不是 IVF_FLAT 的理由**：
1. 召回更高（实测 76.7% vs 25.3%）
2. **天然支持增量**：后续加论文直接 insert 即可，索引自动扩展
3. IVF_* 系列靠 k-means 聚类，数据量涨了 `nlist` 就得跟着调，否则召回持续劣化；
   要恢复就得 `drop_index` + `create_index` 重建，数据量大时很贵

如果你坚持用 IVF_FLAT，**`nlist` 的经验公式**是：

```
nlist ≈ 4 × sqrt(数据量)
```

| 数据量 | nlist |
|---|---|
| 1 万 | 128 |
| 10 万 | 1024 |
| 50 万 | 2048 |

`nprobe` 取 `nlist / 16` 起步。

### 增量加论文的正确姿势

你的 `ingest.py` 已经是"每篇 PDF 走一次完整 pipeline"，这个结构是对的。
加论文时只需要注意三点：

**1. 索引只建一次，不要重复建**
`create_collection()` 里已有 `has_collection` 判断，集合存在就跳过，逻辑没问题。
但要**删掉里面重复 create_index 的隐患**——如果集合已存在又建索引，会浪费时间。

**2. 插入后必须 flush 才能持久化**
你 `insert()` 里已经调了 `self.collection.flush()`，正确。
注意 Lite 模式下 flush 会清理 WAL 文件，在某些受管控环境（如沙箱、回收站不可用）
会报 `safe-delete` 错误——**在普通 CMD/PowerShell 里跑就没这个问题**。

**3. 批量插入，别一条一条插**
`ingest.py` 现在是整篇论文一次性 insert，已经够用了。
如果单篇论文 chunk 数特别多（比如你那篇 77 页的，约 600 chunks），
建议按 200-500 条分批，避免单次请求过大：

```python
BATCH = 300
for i in range(0, len(chunks), BATCH):
    self.vector_store.insert(chunks[i:i+BATCH], vectors[i:i+BATCH])
```

### 什么时候该从 Lite 迁到 Docker

出现下面任一情况就该迁了：

- 向量数超过 **50 万**
- 需要多人/多进程**并发访问**（Lite 是单进程独占文件锁）
- 检索延迟明显变慢（万级数据量下 HNSW 应在 10ms 内）
- 磁盘数据文件超过 2-3 GB

迁移成本很低：数据卷配在 E 盘（见第五节 compose 文件），
`.env` 改成 `MILVUS_URI=http://localhost:19530` 就行，代码一行不用动
（`connections.connect` 的 `uri` 既接受本地文件也接受 http 地址）。
数据本身需要用 Milvus 的迁移工具或重新灌一遍。

---

## 四、另外两个我顺手发现的坑（不急，但你迟早会遇到）

### 1. `delete()` 的表达式有 bug — `vector_store.py` 第 151 行

```python
expr = f"id in {chunk_ids}"
```

Python 的 list 转字符串是 `['a', 'b']`（单引号），但 Milvus 表达式只认双引号，这行会报错。
改成：

```python
ids_str = ", ".join(f'"{i}"' for i in chunk_ids)
expr = f"id in [{ids_str}]"
```

### 2. pymilvus 3.1 会移除你现在用的这套 ORM API

运行时你应该看到过这类警告：

```
PyMilvusDeprecationWarning: `utility.drop_collection` is an ORM-style
PyMilvus API and will be removed in PyMilvus 3.1.
```

你现在 `pymilvus 3.0.1` 一切正常，但下次升级大版本就会挂。
长远建议迁到 `MilvusClient`（写法参考本目录 `e2e_check.py`），不着急。

---

## 五、备选：如果你还是想用 Docker（数据挂 E 盘）

Docker Desktop 现在没启动，要用的话先手动启动它。镜像约 1.5GB，注意 C 盘。

把下面这份存成 `docker-compose.yml`，**数据卷全部指向 E 盘**，不占 C 盘：

```yaml
services:
  etcd:
    container_name: milvus-etcd
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
      - ETCD_SNAPSHOT_COUNT=50000
    volumes:
      - E:/kunxuesuo/milvus-data/etcd:/etcd
    command: etcd -advertise-client-urls=http://etcd:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 30s
      timeout: 20s
      retries: 3

  minio:
    container_name: milvus-minio
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    ports:
      - "9001:9001"
      - "9000:9000"
    volumes:
      - E:/kunxuesuo/milvus-data/minio:/minio_data
    command: minio server /minio_data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  standalone:
    container_name: milvus-standalone
    image: milvusdb/milvus:v2.4.0
    command: ["milvus", "run", "standalone"]
    security_opt:
      - seccomp:unconfined
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    volumes:
      - E:/kunxuesuo/milvus-data/milvus:/var/lib/milvus
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      start_period: 90s
      timeout: 20s
      retries: 3
    ports:
      - "19530:19530"
      - "9091:9091"
    depends_on:
      - etcd
      - minio
```

启动后把 `.env` 改成：

```ini
MILVUS_URI=http://localhost:19530
```

（`connections.connect` 的 `uri` 既能接本地文件，也能接 `http://` 地址，所以代码不用再改第二遍。）

想看图形界面就加一个 Attu：

```bash
docker run -d --name attu -p 8000:3000 -e MILVUS_URL=localhost:19530 zilliz/attu:v2.4
```

浏览器打开 `http://localhost:8000`。

---

## 六、本目录文件说明

| 文件 | 用途 |
|---|---|
| `MIGRATE.md` | 本文件，改动清单 |
| `test_lite.py` | 连通性诊断，对比三种连接方式哪个可用 |
| `probe_embedding.py` | 测 Ollama embedding 维度和可用性 |
| `e2e_check.py` | 端到端演示：embedding → 入库 → 检索（不依赖你的代码） |
| `verify_after_patch.py` | **你改完代码后跑这个**，验证 `MilvusStore` 是否真的通了 |

这些都可以随时删，不影响项目。
