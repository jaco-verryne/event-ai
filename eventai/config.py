"""Settings from Streamlit secrets first, then the environment (with a local .env file)."""

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseModel):
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    openrouter_api_key: str | None = None
    openrouter_model: str = "nvidia/nemotron-3.5-super-vl:free"
    companies_house_api_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
    google_client_secret_file: str = "credentials.json"
    google_token_file: str = "token.json"


def read_dotenv(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines. Plain on purpose, so no python-dotenv dependency."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def load_dotenv(path: Path = ROOT / ".env") -> None:
    # A variable that is already set in the environment wins over the file.
    for key, value in read_dotenv(path).items():
        os.environ.setdefault(key, value)


def _streamlit_secret(name: str) -> str | None:
    # Only look when a Streamlit app runs; Part 2 and the tests do not import Streamlit.
    st = sys.modules.get("streamlit")
    if st is None:
        return None
    try:
        return st.secrets.get(name)
    except Exception:  # st.secrets raises when there is no secrets file
        return None


def get(name: str, default: str | None = None) -> str | None:
    for value in (_streamlit_secret(name), os.environ.get(name)):
        if value not in (None, ""):
            return str(value)
    return default


@lru_cache
def load_settings() -> Settings:
    load_dotenv()
    values = {field: get(field.upper()) for field in Settings.model_fields}
    return Settings(**{k: v for k, v in values.items() if v is not None})
