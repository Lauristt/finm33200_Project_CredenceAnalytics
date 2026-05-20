from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class ToolkitConfig:
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    serper_api_key: str | None = None
    jina_api_key: str | None = None
    finnhub_api_key: str | None = None
    sec_user_agent: str | None = None
    llm_provider: str = "auto"
    openai_model: str | None = None
    anthropic_model: str | None = None
    request_timeout: float = 25.0
    enable_live_extraction: bool = False

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "ToolkitConfig":
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv(Path.cwd() / ".env")

        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
            serper_api_key=os.getenv("SERPER_API_KEY") or None,
            jina_api_key=os.getenv("JINA_API_KEY") or None,
            finnhub_api_key=os.getenv("FINNHUB_API_KEY") or None,
            sec_user_agent=os.getenv("SEC_USER_AGENT") or None,
            llm_provider=os.getenv("CREDIBILITY_LLM_PROVIDER", "auto").lower(),
            openai_model=os.getenv("OPENAI_MODEL") or None,
            anthropic_model=os.getenv("ANTHROPIC_MODEL") or None,
            request_timeout=float(os.getenv("CREDIBILITY_REQUEST_TIMEOUT", "25")),
            enable_live_extraction=os.getenv("CREDIBILITY_LIVE_EXTRACTION", "").lower()
            in {"1", "true", "yes"},
        )
