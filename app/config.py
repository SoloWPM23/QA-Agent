"""Central application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


class AppConfig(BaseModel):
    """Central config object, injected into modules instead of scattered os.getenv calls.

    Plain BaseModel so tests can construct an instance with custom values directly.
    LM Studio values may also be supplied per-run via the UI.
    """

    lm_studio_url: str = ""  # Base URL LM Studio (may be set via UI)
    lm_model: str = ""  # Model name in LM Studio (may be set via UI)
    default_base_url: str = ""  # Base URL target API (optional, from form/CLI)
    report_dir: str = "reports"  # Output directory for CLI reports
    temp_upload_dir: str = "tmp_uploads"  # Temporary upload directory
    default_executor: str = "httpx"  # Default HTTP executor: playwright | httpx
    max_retries: int = 3  # Max LLM retries on parse failures

    def ensure_dirs(self) -> None:
        """Create report and temp directories if they do not exist yet."""
        for name in (self.report_dir, self.temp_upload_dir):
            Path(name).mkdir(parents=True, exist_ok=True)


def load_config(env_file: str = ".env") -> AppConfig:
    """Load .env if present, read values, and return an AppConfig instance.

    Args:
        env_file: Path to the .env file. Default is ".env" in the working directory.

    Returns:
        AppConfig populated from environment variables. LM Studio URL/model may
        also be supplied per-run via the UI.
    """
    load_dotenv(env_file, override=False)

    return AppConfig(
        lm_studio_url=os.getenv("LM_STUDIO_URL", ""),
        lm_model=os.getenv("LM_MODEL", ""),
        default_base_url=os.getenv("DEFAULT_BASE_URL", ""),
        report_dir=os.getenv("REPORT_DIR", AppConfig.model_fields["report_dir"].default),
        temp_upload_dir=os.getenv(
            "TEMP_UPLOAD_DIR", AppConfig.model_fields["temp_upload_dir"].default
        ),
        default_executor=os.getenv(
            "DEFAULT_EXECUTOR", AppConfig.model_fields["default_executor"].default
        ),
        max_retries=int(
            os.getenv("MAX_RETRIES", str(AppConfig.model_fields["max_retries"].default))
        ),
    )
