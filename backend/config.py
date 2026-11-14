"""Application configuration for FireScope backend."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "FireScope API"
    app_version: str = "1.0.0"
    app_env: str = "development"
    debug: bool = False

    host: str = "127.0.0.1"
    port: int = 8000
    api_prefix: str = "/api/v1"

    # CORS origins for frontend integration (Vite, Next, React, etc.)
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]

    # Database configuration for mutable metadata
    # Uses SQLite by default for zero-daemon local run; points to PostgreSQL when DATABASE_URL is configured
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'firescope_meta.db').as_posix()}"

    # Path configurations (resolving relative paths to PROJECT_ROOT)
    root_dir: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"
    reports_dir: Path = PROJECT_ROOT / "reports"
    modis_parquet: Path = PROJECT_ROOT / "data" / "processed" / "common_period" / "modis_common_20120121_20260714.parquet"
    viirs_parquet: Path = PROJECT_ROOT / "data" / "processed" / "common_period" / "viirs_common_20120121_20260714.parquet"
    harmonized_dir: Path = PROJECT_ROOT / "data" / "harmonized"

    # Query limits
    default_page_size: int = 50
    max_page_size: int = 500
    max_viewport_detections: int = 2000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                return json.loads(v)
            return [i.strip() for i in v.split(",") if i.strip()]
        return v


settings = Settings()
