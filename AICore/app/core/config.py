import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_VALID_ENVS = {"dev", "staging", "prod"}


class BaseConfig:
    PREFIX = "dev"
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def __init__(self) -> None:
        self._load_runtime_env()

    def _load_runtime_env(self) -> None:
        # PostgreSQL (Prisma)
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://aicore:aicore@postgres:5432/aicore",)

        # Vector DB
        self.QDRANT_URL: str = os.getenv("QDRANT_URL", "http://qdrant:6333")
        self.QDRANT_HOST: str = os.getenv("QDRANT_HOST", "qdrant")
        self.QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
        self.QDRANT_GRPC_PORT: int = int(os.getenv("QDRANT_GRPC_PORT", "6334"))
        
        # Qdrant HNSW Configuration
        self.QDRANT_HNSW_M: int = int(os.getenv("QDRANT_HNSW_M", "32"))
        self.QDRANT_HNSW_EF_CONSTRUCT: int = int(os.getenv("QDRANT_HNSW_EF_CONSTRUCT", "200"))
        self.QDRANT_HNSW_EF: int = int(os.getenv("QDRANT_HNSW_EF", "100"))
        self.QDRANT_HNSW_FULL_SCAN_THRESHOLD: int = int(os.getenv("QDRANT_HNSW_FULL_SCAN_THRESHOLD", "10000"))
        self.QDRANT_DEFAULT_SEGMENT_NUMBER: int = int(os.getenv("QDRANT_DEFAULT_SEGMENT_NUMBER", "8"))
        self.QDRANT_MAX_SEGMENT_SIZE: int = int(os.getenv("QDRANT_MAX_SEGMENT_SIZE", "1500000"))
        self.QDRANT_INDEXING_THRESHOLD: int = int(os.getenv("QDRANT_INDEXING_THRESHOLD", "600000"))
        self.QDRANT_POI_COLLECTION: str = os.getenv("QDRANT_POI_COLLECTION", "poi_data")
        self.QDRANT_ATTRIBUTE_COLLECTION: str = os.getenv("QDRANT_ATTRIBUTE_COLLECTION", "attribute_data",)

        # Embedding Service
        self.EMBEDDING_SERVICE_URL: str = os.getenv("EMBEDDING_SERVICE_URL", "aicore-embedding:50051")
        self.EMBEDDING_SERVICE_MODEL: str = os.getenv("EMBEDDING_SERVICE_MODEL", "bge-m3")
        self.EMBEDDING_SERVICE_TIMEOUT: int = int(os.getenv("EMBEDDING_SERVICE_TIMEOUT", "30"))
        self.EMBEDDING_SERVICE_RETRY_COUNT: int = int(os.getenv("EMBEDDING_SERVICE_RETRY_COUNT", "3"))
        self.EMBEDDING_SERVICE_TYPE: bool = bool(os.getenv("EMBEDDING_SERVICE_TYPE", "False"))
        self.EMBEDDING_SIZE: int = int(os.getenv("EMBEDDING_SIZE", "1024"))
        self.VECTOR_UPSERT_BATCH_SIZE: int = int(
            os.getenv("VECTOR_UPSERT_BATCH_SIZE", "10"),
        )
        self.ATTRIBUTE_SEARCH_PREFETCH_LIMIT: int = int(os.getenv("ATTRIBUTE_SEARCH_PREFETCH_LIMIT", "50"))
        # RRF score cutoff after dense+sparse fusion (tune later)
        self.ATTRIBUTE_SEARCH_RRF_THRESHOLD: float = float(os.getenv("ATTRIBUTE_SEARCH_RRF_THRESHOLD", "0.01"))
        self.TASCO_POI_TOP_K: int = int(os.getenv("TASCO_POI_TOP_K", "20"))
        self.TASCO_ATTRIBUTE_TOP_K: int = int(os.getenv("TASCO_ATTRIBUTE_TOP_K", "20"))

        # LLM Gateway (LiteLLM)
        self.LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")
        self.LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
        self.LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "300"))
        self.LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))

        # Provider API keys
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")


class DevelopmentConfig(BaseConfig):
    """Development environment configuration."""
    PREFIX = "dev"


class StagingConfig(BaseConfig):
    """Staging environment configuration."""
    PREFIX = "staging"


class ProductionConfig(BaseConfig):
    """Production environment configuration."""
    PREFIX = "prod"


def get_settings() -> BaseConfig:
    config_map = {
        "dev": DevelopmentConfig,
        "staging": StagingConfig,
        "prod": ProductionConfig,
    }
    env_file_map = {
        "dev": ".env",
        "staging": ".env",
        "prod": ".env",
    }

    # ENV must be set in the OS/Docker environment — it is read before load_dotenv
    # runs, so it cannot be sourced from the .env file itself.
    env_name = os.getenv("ENV", "dev")
    if env_name not in _VALID_ENVS:
        raise ValueError(
            f"ENV='{env_name}' is not recognised. Valid values: {sorted(_VALID_ENVS)}"
        )

    env_path = os.path.join(BaseConfig.BASE_DIR, env_file_map[env_name])
    logger.debug("Loading environment from: %s", env_path)

    load_dotenv(env_path)
    return config_map[env_name]()


# Global settings instance
settings = get_settings()