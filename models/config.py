from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    app_name: str = "本地智能路线规划系统"
    app_version: str = "0.1.0"
    default_city: str = "成都"
    data_dir: Path = DATA_DIR
    pois_file: Path = DATA_DIR / "poi_data_100k.json"
    reviews_file: Path = DATA_DIR / "reviews_100k.json"
    user_profiles_file: Path = DATA_DIR / "user_profiles.json"
    max_route_pois: int = Field(default=8, gt=0)
    default_route_duration_minutes: int = Field(default=240, gt=0)
    walking_speed_kmph: float = Field(default=4.5, gt=0)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ROUTE_PLANNER_",
        extra="ignore",
    )


settings = Settings()
