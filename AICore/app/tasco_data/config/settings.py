from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

AICORE_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = AICORE_DIR.parent


class PipelineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(AICORE_DIR / ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://aicore:aicore@localhost:5432/aicore"
    poi_dataset_path: str = "data/raw/ai_maps_track2_dataset_participants.xlsx"
    poi_dataset_sheet: str = "POI_Dataset"

    # llm_provider/llm_model/openai_api_key/llm_temperature sống ở app.core.config.settings
    # (dùng chung với phía API service) — không khai báo lại ở đây.
    llm_taxonomy_enabled: bool = True
    llm_batch_size: int = 20

    llm_signal_enrichment_enabled: bool = True
    llm_signal_batch_size: int = 10

    @property
    def poi_dataset_abspath(self) -> Path:
        path = Path(self.poi_dataset_path)
        return path if path.is_absolute() else REPO_ROOT / path


settings = PipelineSettings()
