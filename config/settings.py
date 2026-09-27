"""统一配置管理（Pydantic Settings）"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # === LLM 配置 ===
    llm_api_key: str = Field(default="testapi", alias="API_KEY")
    llm_base_url: str = Field(
        default="https://api.longcat.chat/openai/v1", alias="BASE_URL"
    )
    llm_model: str = Field(default="Longcat-2.0", alias="MODEL")
    llm_temperature: float = 0.2
    llm_max_tokens: int = 8192

    # === Embedding 配置 ===
    emb_api_key: str = Field(default="", alias="EMB_API_KEY")
    emb_base_url: str = Field(default="", alias="EMB_BASE_URL")
    emb_model: str = Field(default="text-embedding-3-small", alias="EMB_MODEL")

    # === Milvus 配置 ===
    milvus_host: str = Field(default="localhost", alias="MILVUS_HOST")
    milvus_port: str = Field(default="19530", alias="MILVUS_PORT")
    milvus_uri: str = Field(default="./milvus_lite.db", alias="MILVUS_URI")
    milvus_collection: str = Field(
        default="paper_rag", alias="MILVUS_COLLECTION"
    )

    # === 存储路径 ===
    storage_dir: Path = Field(default=Path("./storage_data"), alias="STORAGE_DIR")
    sqlite_path: Path = Field(
        default=Path("./storage_data/metadata.db"), alias="SQLITE_PATH"
    )
    bm25_index_path: Path = Field(
        default=Path("./storage_data/bm25_index.json"),
        alias="BM25_INDEX_PATH",
    )

    # === 分块配置 ===
    chunk_size: int = Field(default=500, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=50, alias="CHUNK_OVERLAP")

    # === 检索配置 ===
    retrieve_top_k: int = Field(default=10, alias="RETRIEVE_TOP_K")
    bm25_top_k: int = Field(default=10, alias="BM25_TOP_K")
    vector_top_k: int = Field(default=10, alias="VECTOR_TOP_K")
    rerank_top_k: int = Field(default=5, alias="RERANK_TOP_K")
    rrf_k: int = Field(default=60, alias="RRF_K")

    # === 重排序配置 ===
    rerank_model: str = Field(
        default="bge-reranker-v2-m3", alias="RERANK_MODEL"
    )
    use_rerank: bool = Field(default=True, alias="USE_RERANK")

    # === 应用配置 ===
    input_dir: Path = Field(
        default=Path("./input/papers"), alias="INPUT_DIR"
    )
    output_dir: Path = Field(default=Path("./output"), alias="OUTPUT_DIR")
    evaluation_topic: str = Field(default="AI赋能", alias="EVALUATION_TOPIC")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 确保存储目录存在
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


# 全局单例
settings = Settings()
