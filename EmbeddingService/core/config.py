import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_VALID_ENVS = {"dev", "staging", "prod"}


class BaseConfig:
    """Base configuration populated from runtime environment variables."""

    PREFIX = "dev"
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def __init__(self) -> None:
        self._load_runtime_env()

    def _load_runtime_env(self) -> None:
        self.SERVICE_NAME = os.getenv("SERVICE_NAME", "embedding-service")
        self.HOST = os.getenv("HOST", "0.0.0.0")
        self.PORT = int(os.getenv("PORT", "50051"))
        self.MAX_WORKERS = int(os.getenv("MAX_WORKERS", "10"))
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

        self.CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
        self.COLBERT_POOL_FACTOR = int(os.getenv("COLBERT_POOL_FACTOR", "3"))


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
    """Build and return the settings instance for the active environment."""
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

    env_name = os.getenv("ENV", "dev")
    if env_name not in _VALID_ENVS:
        raise ValueError(
            f"ENV='{env_name}' is not recognised. Valid values: {sorted(_VALID_ENVS)}"
        )

    env_path = os.path.join(BaseConfig.BASE_DIR, env_file_map[env_name])
    logger.debug("Loading environment from: %s", env_path)

    load_dotenv(env_path)
    return config_map[env_name]()


settings = get_settings()