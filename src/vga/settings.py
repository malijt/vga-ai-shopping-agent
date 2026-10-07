"""One validated settings object: ``config/settings.yaml``, overridden by environment variables.

Config comes from here and from the environment only (never from code constants spread around).
Precedence, highest first: real environment variables, then ``.env``, then the YAML file, then the
defaults below. See ``.env.example`` for the variables.

Two fields are unset in the code defaults because the build decides them (plan assumption A10 and
Phase 3): ``openai_model`` and ``siglip_revision``. They may be ``None`` at load time (the shipped
``config/settings.yaml`` pins ``siglip_revision`` since the Phase 3 spike; ``openai_model`` is still
unset). When set they must be pinned: a dated OpenAI snapshot id (or an
undated id from ``UNDATED_SNAPSHOT_IDS``, for a model OpenAI publishes only as a snapshot), and a
40-character Hugging Face commit hash. Aliases such as ``gpt-5-mini`` or ``main`` are rejected,
because a pinned version must not change under us.

An empty value in the environment (``OPENAI_MODEL=`` in ``.env``, for example) means "not set": the
YAML value is used. It is never an error and never an empty string.
"""

import os
import re
from collections.abc import MutableMapping
from datetime import date
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import Field, ValidationError, field_validator, model_validator

from vga.errors import ConfigError
from vga.models import CountryCode, MixPreset, SettingsOverride, TierMix, VgaModel

PROJECT_ROOT = Path(__file__).resolve().parents[2]
"""The repository root (this file lives in ``<root>/src/vga``)."""

DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_STORES_DIR = PROJECT_ROOT / "config" / "stores"
DEFAULT_DOTENV_PATH = PROJECT_ROOT / ".env"

DEFAULT_USER_AGENT = "vga-shopping-agent-demo/0.1 (store search demo)"

ENV_OVERRIDES: dict[str, str] = {
    "OPENAI_MODEL": "openai_model",
    "VGA_USER_AGENT": "user_agent",
    "VGA_IMAGE_RANKER": "image_ranker",
    "VGA_LOG_DIR": "log_dir",
    "VGA_LOG_LEVEL": "log_level",
    "VGA_LOG_PROMPTS": "log_prompts",
    "VGA_DEBUG_DUMP": "debug_dump",
    "VGA_DAILY_LLM_CALL_CAP": "daily_llm_call_cap",
    "VGA_UI_FIXTURE": "ui_fixture",
}
"""Environment variable to settings field. ``VGA_SETTINGS_PATH`` picks the YAML file instead, and
``OPENAI_API_KEY`` is read by the OpenAI client directly: it is never a setting, so it can never be
dumped or logged with the settings."""

UNDATED_SNAPSHOT_IDS: frozenset[str] = frozenset(
    {
        # OpenAI's model page lists exactly one snapshot for this model, and it is the versioned
        # name itself: there is no dated variant, so the name is the pin.
        # Source: https://developers.openai.com/api/docs/models/gpt-6-luna (verified 2026-10-08).
        "gpt-6-luna",
    }
)
"""Model ids that have no ``-YYYY-MM-DD`` form but are still a fixed version. An id is added here
only after reading OpenAI's model page for it (record the URL and the date next to the id). An
alias is never added: ``gpt-6-luna-latest`` or a bare ``luna`` must keep failing."""

_SNAPSHOT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*-(\d{4})-(\d{2})-(\d{2})$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_BROWSER_MARKERS = ("mozilla/", "applewebkit", "chrome/", "safari/", "firefox/", "gecko/")


class RankingWeights(VgaModel):
    """Weights of the three parts of the ranking score (PRD R8). They need not sum to 1: the
    combiner normalises, and drops the image weight when there is no image score."""

    text: float = Field(default=0.5, ge=0)
    image: float = Field(default=0.3, ge=0)
    price: float = Field(default=0.2, ge=0)

    @model_validator(mode="after")
    def _some_weight(self) -> Self:
        if self.text + self.image + self.price <= 0:
            msg = "ranking_weights must not all be zero"
            raise ValueError(msg)
        return self


class Settings(VgaModel):
    """All tunable behaviour of the demo (PRD "Settings" plus plan 1.3.1)."""

    # --- search ---------------------------------------------------------------------------
    country: CountryCode = "AE"
    """ISO 3166-1 alpha-2 code of the market to search. Only enabled stores in this country are
    used. The PRD's "UAE" is ``AE``."""
    stores: list[str] = Field(default_factory=list)
    """Store ids to use. Empty means every enabled store in ``country``."""
    results: int = Field(default=30, ge=1, le=100)
    max_per_store: int = Field(default=6, ge=1, le=50)
    outfit_results_per_garment: int = Field(default=12, ge=1, le=50)
    request_deadline_s: float = Field(default=30.0, gt=0, le=120)
    """Ceiling for one whole request; at the deadline the pipeline returns what it has."""
    max_image_bytes: int = Field(default=8_000_000, gt=0)
    """The largest photo, in bytes, the app accepts. The UI and the pipeline's request validation
    both read this."""

    # --- fetching -------------------------------------------------------------------------
    timeout_s: float = Field(default=6.0, gt=0, le=60)
    rps_per_store: float = Field(default=1.0, gt=0, le=5)
    rps_images_per_host: float = Field(default=5.0, gt=0, le=20)
    store_cache_ttl_s: int = Field(default=600, ge=0)
    store_cooldown_s: int = Field(default=900, ge=0)
    max_response_bytes: int = Field(default=2_000_000, gt=0)
    """Size cap, in bytes, for one HTTP response. ``StoreConfig.max_response_bytes`` overrides it
    for a single store."""
    user_agent: str = DEFAULT_USER_AGENT

    # --- ranking and price ranges ---------------------------------------------------------
    tier_mix: TierMix = Field(default_factory=lambda: MixPreset.EVEN.mix)
    ranking_weights: RankingWeights = Field(default_factory=RankingWeights)
    min_match_score: float = Field(default=0.2, ge=0, le=1)
    neutral_price_score: float = Field(default=0.5, ge=0, le=1)
    """Price-fit score used when the shopper gave no budget (plan 7.2.3)."""

    # --- models ---------------------------------------------------------------------------
    image_ranker: Literal["siglip", "off"] = "off"
    siglip_revision: str | None = None
    siglip_cos_lo: float = Field(default=0.45, ge=0, le=1)
    siglip_cos_hi: float = Field(default=0.90, ge=0, le=1)
    """Image cosine to 0-1 score: ``clip((cos - siglip_cos_lo) / (siglip_cos_hi - siglip_cos_lo),
    0, 1)``. Measured in ``spikes/siglip/REPORT.md``; ``siglip_cos_lo`` must be below
    ``siglip_cos_hi``."""
    openai_model: str | None = None
    daily_llm_call_cap: int = Field(default=200, ge=0)

    # --- logging and debugging ------------------------------------------------------------
    log_dir: str = "logs"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_prompts: bool = False
    debug_dump: bool = False
    ui_fixture: bool = False

    @model_validator(mode="after")
    def _siglip_range_is_ordered(self) -> Self:
        if self.siglip_cos_lo >= self.siglip_cos_hi:
            msg = (
                f"siglip_cos_lo ({self.siglip_cos_lo}) must be below siglip_cos_hi "
                f"({self.siglip_cos_hi}): together they map an image cosine to a 0-1 score"
            )
            raise ValueError(msg)
        return self

    @field_validator("image_ranker", mode="before")
    @classmethod
    def _yaml_off_is_false(cls, value: Any) -> Any:
        # YAML 1.1 reads an unquoted `off` as the boolean False. Accept it as the string it meant.
        return "off" if value is False else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: Any) -> Any:
        return value.upper() if isinstance(value, str) else value

    @field_validator("openai_model")
    @classmethod
    def _pinned_model(cls, value: str | None) -> str | None:
        if not value:
            return None
        if value in UNDATED_SNAPSHOT_IDS:
            return value
        match = _SNAPSHOT_RE.match(value)
        if match:
            year, month, day = (int(part) for part in match.groups())
            try:
                date(year, month, day)
            except ValueError:
                match = None
        if not match:
            allowed_undated = ", ".join(sorted(UNDATED_SNAPSHOT_IDS))
            msg = (
                "openai_model must be a dated snapshot id ending in -YYYY-MM-DD, or one of the "
                f"undated snapshot ids verified against OpenAI's model pages ({allowed_undated}), "
                f"got {value!r}. Aliases such as 'gpt-5-mini', '...-latest' or a bare family name "
                "are not allowed because they can change under us; "
                "pick the dated id from OpenAI's model docs"
            )
            raise ValueError(msg)
        return value

    @field_validator("siglip_revision")
    @classmethod
    def _pinned_revision(cls, value: str | None) -> str | None:
        if not value:
            return None
        if not _REVISION_RE.match(value):
            msg = (
                f"siglip_revision must be a 40-character Hugging Face commit hash, got {value!r}. "
                "Branch names such as 'main' are not allowed because they move"
            )
            raise ValueError(msg)
        return value

    @field_validator("user_agent")
    @classmethod
    def _honest_user_agent(cls, value: str) -> str:
        if not value or not value.isascii() or not value.isprintable() or len(value) > 200:
            msg = "user_agent must be 1-200 printable ASCII characters"
            raise ValueError(msg)
        lowered = value.lower()
        if any(marker in lowered for marker in _BROWSER_MARKERS):
            msg = (
                "user_agent must identify this app honestly; imitating a browser is not allowed "
                "(BRD Rule 2)"
            )
            raise ValueError(msg)
        return value

    def with_overrides(self, override: SettingsOverride | None) -> Self:
        """A copy with the UI sidebar's changes applied. Only the price-range mix is a setting;
        the budget belongs to the request, so the pipeline applies that itself."""
        if override is None or override.tier_mix is None:
            return self
        return self.model_copy(update={"tier_mix": override.tier_mix})


# --------------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------------

_DOTENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_dotenv(
    path: Path | str = DEFAULT_DOTENV_PATH,
    environ: MutableMapping[str, str] | None = None,
) -> list[str]:
    """Copy ``KEY=value`` lines of a ``.env`` file into the environment.

    Variables that are already set are left alone, so a real environment variable always beats
    the file. A variable that is set but empty counts as not set, the same as everywhere else in
    the settings loader, so the file can fill it. Returns the names it set. A missing file is
    fine. This is a small reader on purpose (no extra dependency): it handles comments,
    ``export``, and single or double quotes.
    """
    target = os.environ if environ is None else environ
    file = Path(path)
    if not file.is_file():
        return []
    applied: list[str] = []
    for line in file.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _DOTENV_LINE.match(line)
        if not match:
            continue
        name, value = match.groups()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = re.split(r"(?:^|\s+)#", value, maxsplit=1)[0].strip()
        if name in target and (target[name].strip() or not value):
            continue  # a real value wins, and an empty line has nothing to add to an empty one
        target[name] = value
        applied.append(name)
    return applied


def _format_validation_error(exc: ValidationError, env_sources: dict[str, str]) -> str:
    lines: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "settings"
        message = str(error["msg"]).removeprefix("Value error, ")
        source = env_sources.get(str(error["loc"][0])) if error["loc"] else None
        suffix = f" (set by environment variable {source})" if source else ""
        lines.append(f"{location}: {message}{suffix}")
    return "; ".join(lines)


def load_settings(
    path: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> Settings:
    """Load and validate the settings.

    ``path`` is the YAML file; if omitted, ``VGA_SETTINGS_PATH`` or ``config/settings.yaml``.
    ``env`` is the environment to read overrides from; if omitted, ``.env`` is loaded into
    ``os.environ`` first and ``os.environ`` is used. Tests pass ``env={}`` for a clean run.

    Raises ``ConfigError`` naming every invalid field.
    """
    if env is None:
        load_dotenv(DEFAULT_DOTENV_PATH)
        env = dict(os.environ)

    chosen = path or env.get("VGA_SETTINGS_PATH") or DEFAULT_SETTINGS_PATH
    file = Path(chosen)
    if not file.is_file():
        raise ConfigError(
            f"The app settings file {file.name} was not found. "
            "Check the path (VGA_SETTINGS_PATH) and restart.",
            detail=f"settings file not found: {file}",
        )
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(
            f"The app settings file {file.name} could not be read. Fix it and restart.",
            detail=f"cannot read settings file {file}: {exc}",
        ) from exc
    data: dict[str, Any] = {} if raw is None else raw
    if not isinstance(data, dict):
        raise ConfigError(
            f"The app settings file {file.name} must contain a mapping of settings.",
            detail=f"top level of {file} is {type(data).__name__}, expected a mapping",
        )

    env_sources: dict[str, str] = {}
    for variable, field_name in ENV_OVERRIDES.items():
        value = env.get(variable)
        if value is not None and value.strip():
            data[field_name] = value.strip()
            env_sources[field_name] = variable

    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        summary = _format_validation_error(exc, env_sources)
        raise ConfigError(
            f"The app settings are not valid: {summary}. "
            "Fix config/settings.yaml or your environment variables and restart.",
            detail=summary,
        ) from exc
