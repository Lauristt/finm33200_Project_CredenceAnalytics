"""Configuration loading for local development, CLI, and tool execution.

The package intentionally avoids a hard dependency on `python-dotenv`; this file
implements the tiny subset needed for `.env` based demos. Environment variables
already set by the caller are not overwritten.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    """Load simple KEY=VALUE lines into `os.environ` if they are not set."""
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
    """Runtime configuration shared by retrieval, extraction, and judges."""

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    serper_api_key: str | None = None
    jina_api_key: str | None = None
    finnhub_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    fmp_api_key: str | None = None
    fred_api_key: str | None = None
    marketstack_api_key: str | None = None
    tiingo_api_key: str | None = None
    sec_user_agent: str | None = None
    llm_provider: str = "auto"
    openai_model: str | None = None
    anthropic_model: str | None = None
    request_timeout: float = 25.0
    enable_live_extraction: bool = False
    enable_structured_sources: bool = True
    enable_yahoo_fallback: bool = False
    allow_insecure_ssl_fallback: bool = False
    enable_ticker_universe_filter: bool = True
    enable_ticker_universe_fetch: bool = False
    ticker_universe_file: str | None = None
    ticker_universe_cache_file: str | None = ".cache/financial_credibility/company_tickers_exchange.json"
    enable_asset_universe_filter: bool = True
    asset_universe_file: str | None = None

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "ToolkitConfig":
        """Build config from process env plus an optional `.env` file."""
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
            alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY") or None,
            fmp_api_key=os.getenv("FMP_API_KEY") or None,
            fred_api_key=os.getenv("FRED_API_KEY") or None,
            marketstack_api_key=os.getenv("MARKETSTACK_API_KEY") or None,
            tiingo_api_key=os.getenv("TIINGO_API_KEY") or None,
            sec_user_agent=os.getenv("SEC_USER_AGENT") or None,
            llm_provider=os.getenv("CREDIBILITY_LLM_PROVIDER", "auto").lower(),
            openai_model=os.getenv("OPENAI_MODEL") or None,
            anthropic_model=os.getenv("ANTHROPIC_MODEL") or None,
            request_timeout=float(os.getenv("CREDIBILITY_REQUEST_TIMEOUT", "25")),
            enable_live_extraction=os.getenv("CREDIBILITY_LIVE_EXTRACTION", "").lower()
            in {"1", "true", "yes"},
            enable_structured_sources=os.getenv("CREDIBILITY_STRUCTURED_SOURCES", "true").lower()
            in {"1", "true", "yes"},
            enable_yahoo_fallback=os.getenv("CREDIBILITY_YAHOO_FALLBACK", "").lower()
            in {"1", "true", "yes"},
            allow_insecure_ssl_fallback=os.getenv(
                "CREDIBILITY_ALLOW_INSECURE_SSL_FALLBACK", ""
            ).lower()
            in {"1", "true", "yes"},
            enable_ticker_universe_filter=os.getenv(
                "CREDIBILITY_TICKER_UNIVERSE_FILTER", "true"
            ).lower()
            in {"1", "true", "yes"},
            enable_ticker_universe_fetch=os.getenv(
                "CREDIBILITY_TICKER_UNIVERSE_FETCH", "true"
            ).lower()
            in {"1", "true", "yes"},
            ticker_universe_file=os.getenv("CREDIBILITY_TICKER_UNIVERSE_FILE") or None,
            ticker_universe_cache_file=os.getenv("CREDIBILITY_TICKER_UNIVERSE_CACHE")
            or ".cache/financial_credibility/company_tickers_exchange.json",
            enable_asset_universe_filter=os.getenv(
                "CREDIBILITY_ASSET_UNIVERSE_FILTER", "true"
            ).lower()
            in {"1", "true", "yes"},
            asset_universe_file=os.getenv("CREDIBILITY_ASSET_UNIVERSE_FILE") or None,
        )
