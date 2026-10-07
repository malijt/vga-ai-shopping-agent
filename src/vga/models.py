"""Shared data contracts for the whole pipeline.

Every phase codes against these models, so they are FROZEN after Phase 1: change one only in its
own pull request that updates every user. The shapes follow section 4 of the implementation plan
and the requirements R1-R16 in docs/02-prd.md.

Conventions
- Models are immutable (``frozen``) and reject unknown fields (``extra="forbid"``), so a typo in a
  YAML file or a drifting field fails loudly instead of being ignored.
- Anything that came from outside (user text, the photo, store pages) is data. These models only
  describe it; they never interpret it as instructions.
- The uploaded photo never appears in ``repr()`` or in JSON dumps (BRD Rule 4).
"""

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    field_validator,
    model_validator,
)

# --------------------------------------------------------------------------------------------
# Constants shared by several phases
# --------------------------------------------------------------------------------------------

MAX_ITEMS = 4
"""At most this many garments per request (outfit photo): plan 5.1.1 and risk R13."""

MAX_KEYWORDS = 3
"""``ItemIntent.search_keywords`` holds 1-3 English keyword variants (PRD R2)."""

MAX_TEXT_CHARS = 2000
"""Longest request text accepted (after stripping). Enforced by ``SearchRequest``."""

DEFAULT_CURRENCY = "AED"
"""UAE first (BRD decision 1). Used when a shopper gives a budget without a currency."""

MAX_URL_LENGTH = 2048

# --------------------------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------------------------


class Category(StrEnum):
    """The five garment categories in scope (BRD). Accessories are out of scope.

    ``DRESSES`` (added 2026-10-08, assumption A23) covers dresses, gowns, kaftans, abayas,
    jalabiyas, kurtas and similar one-piece or ethnic garments. Jumpsuits, swimwear and nightwear
    are not part of it.
    """

    TOPS = "tops"
    OUTERWEAR = "outerwear"
    BOTTOMS = "bottoms"
    SHOES = "shoes"
    DRESSES = "dresses"


class Tier(StrEnum):
    """Price range. Code says "tier"; the UI says "price range" (see ``Tier.label``).

    Declaration order is cheapest to most expensive, and it is the display order.
    """

    BUDGET = "budget"
    MID_RANGE = "mid_range"
    PREMIUM = "premium"
    LUXURY = "luxury"

    @property
    def label(self) -> str:
        """Shopper-facing name: ``Budget``, ``Mid-range``, ``Premium``, ``Luxury``."""
        return "Mid-range" if self is Tier.MID_RANGE else self.value.capitalize()


TIER_ORDER: tuple[Tier, ...] = tuple(Tier)


class InputType(StrEnum):
    """What the shopper gave us. Same values as ``type`` in the acceptance ``queries.yaml``."""

    PRODUCT_PHOTO = "product_photo"
    OUTFIT_PHOTO = "outfit_photo"
    TEXT = "text"
    PHOTO_TEXT = "photo_text"


class Gender(StrEnum):
    MEN = "men"
    WOMEN = "women"
    UNISEX = "unisex"


class GenderSource(StrEnum):
    """Where a gender came from. ``inferred`` is shown but never applied until the shopper
    confirms it (BRD Rule 8, plan assumption A3). ``explicit`` was stated in the request."""

    EXPLICIT = "explicit"
    INFERRED = "inferred"
    NONE = "none"


class StoreStatus(StrEnum):
    """Outcome of searching one store."""

    OK = "ok"
    EMPTY = "empty"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    ROBOTS_DENIED = "robots_denied"
    COOLDOWN = "cooldown"
    ERROR = "error"


class Flag(StrEnum):
    """Machine-readable notes on a product or a price range. The UI shows them as text."""

    OVER_BUDGET = "over_budget"
    """Price is above the shopper's budget (kept, not dropped: plan assumption A4)."""
    FEW_OPTIONS = "few_options"
    """The price range could not be filled to its target (PRD: "few options in this range")."""
    RELATIVE_RANGE = "relative_range"
    """No luxury-leaning store is enabled, so "Luxury" only means "most expensive found"."""


class Step(StrEnum):
    """Pipeline steps reported to ``on_step`` (plan 13.1.2), in execution order."""

    VALIDATE = "validate"
    UNDERSTAND = "understand"
    SEARCH = "search"
    FILTER = "filter"
    RANK = "rank"
    IMAGE_RANK = "image_rank"
    SHAPE = "shape"
    ASSEMBLE = "assemble"


Language = Literal["en", "ar", "mixed", "other"]

# --------------------------------------------------------------------------------------------
# Base class and reusable field types
# --------------------------------------------------------------------------------------------


class VgaModel(BaseModel):
    """Base for every contract: immutable, strict about unknown fields, strips string padding."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        allow_inf_nan=False,
    )


def new_request_id() -> str:
    """A fresh request id: 32 lowercase hex characters, safe to put in logs and file names."""
    return uuid.uuid4().hex


def _check_https_url(value: str) -> str:
    """Accept only absolute https URLs that are safe to render and store.

    This is the model-level half of the "https only" rule. Whether the host is on a store's
    ``allowed_hosts`` is checked later by the fetch engine, which knows the store.
    """
    if len(value) > MAX_URL_LENGTH:
        msg = f"must be at most {MAX_URL_LENGTH} characters"
        raise ValueError(msg)
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in value):
        msg = "must not contain spaces or control characters"
        raise ValueError(msg)
    parts = urlsplit(value)
    if parts.scheme != "https":
        msg = "must start with https://"
        raise ValueError(msg)
    if not parts.hostname:
        msg = "must include a host name"
        raise ValueError(msg)
    if parts.username is not None or parts.password is not None:
        msg = "must not contain credentials"
        raise ValueError(msg)
    return value


HttpsUrl = Annotated[str, AfterValidator(_check_https_url)]


def _upper_stripped(value: Any) -> Any:
    return value.strip().upper() if isinstance(value, str) else value


CurrencyCode = Annotated[
    str, BeforeValidator(_upper_stripped), StringConstraints(pattern=r"^[A-Z]{3}$")
]
CountryCode = Annotated[
    str, BeforeValidator(_upper_stripped), StringConstraints(pattern=r"^[A-Z]{2}$")
]
Score = Annotated[float, Field(ge=0.0, le=1.0)]
RequestId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]


def _blank_to_none(value: str | None) -> str | None:
    """Treat an empty or whitespace-only string as "not given"."""
    if value is None or not value.strip():
        return None
    return value


# --------------------------------------------------------------------------------------------
# Request and intent
# --------------------------------------------------------------------------------------------


class Usage(VgaModel):
    """OpenAI usage for one request (PRD R12, plan 5.2.5)."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    llm_calls: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class Budget(VgaModel):
    """A shopper's price ceiling, e.g. "under 400 AED". Optional everywhere (PRD R7)."""

    max_price: float = Field(gt=0)
    currency: CurrencyCode = DEFAULT_CURRENCY


class SearchRequest(VgaModel):
    """What the shopper submitted: a photo, text, or both (PRD R1).

    Text is validated here so every caller gets the same rule: it is stripped, blank text counts
    as no text, it may be at most ``MAX_TEXT_CHARS`` long, and a request needs text or a photo,
    unless it is a re-run (``rerun_of`` is set). Image checks (magic bytes, size, dimensions) are
    NOT done here; they happen at the pipeline entry (plan 13.1.1). The photo is excluded from
    ``repr`` and from every dump so it cannot leak into logs or fixtures.
    """

    text: str | None = None
    image: bytes | None = Field(default=None, repr=False, exclude=True)
    request_id: RequestId = Field(default_factory=new_request_id)
    rerun_of: RequestId | None = None
    """The ``request_id`` of the search being re-run, or ``None`` for a new search. After a
    photo-only search the app discards the photo (BRD Rule 4), so when the shopper edits a chip
    there is no text and no image left to send. A re-run request may therefore have neither: it
    carries the earlier understanding and the stored image embedding in ``RunOverrides`` instead.
    The pipeline, not this model, checks that a re-run comes with ``overrides.understood``."""

    @field_validator("text")
    @classmethod
    def _clean_text(cls, value: str | None) -> str | None:
        text = _blank_to_none(value)
        if text is not None and len(text) > MAX_TEXT_CHARS:
            msg = f"text must be at most {MAX_TEXT_CHARS} characters, got {len(text)}"
            raise ValueError(msg)
        return text

    @model_validator(mode="after")
    def _needs_input(self) -> Self:
        if self.text is None and self.image is None and self.rerun_of is None:
            msg = "a request needs text, a photo, or both"
            raise ValueError(msg)
        return self

    @property
    def has_image(self) -> bool:
        return self.image is not None


class ItemIntent(VgaModel):
    """One garment the shopper wants, as understood by the model (PRD R2)."""

    category: Category
    colour: str | None = Field(default=None, max_length=60)
    style: str | None = Field(default=None, max_length=120)
    material: str | None = Field(default=None, max_length=60)
    gender: Gender | None = None
    gender_source: GenderSource = GenderSource.NONE
    search_keywords: list[Annotated[str, StringConstraints(min_length=1, max_length=80)]] = Field(
        min_length=1, max_length=MAX_KEYWORDS
    )
    """1-3 English keyword variants sent to store search. Never contains price words (Rule 7)."""

    @field_validator("colour", "style", "material")
    @classmethod
    def _blank_attribute_is_none(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @model_validator(mode="after")
    def _gender_matches_source(self) -> Self:
        if self.gender is None and self.gender_source is not GenderSource.NONE:
            msg = "gender_source must be 'none' when gender is not set"
            raise ValueError(msg)
        if self.gender is not None and self.gender_source is GenderSource.NONE:
            msg = "gender_source must be 'explicit' or 'inferred' when gender is set"
            raise ValueError(msg)
        return self


class UnderstandResult(VgaModel):
    """Output of the Understand step: what to look for (plan section 4)."""

    input_type: InputType
    items: list[ItemIntent] = Field(min_length=1, max_length=MAX_ITEMS)
    budget: Budget | None = None
    edits: list[str] = Field(default_factory=list, max_length=10)
    """Changes asked for on top of a photo ("dark brown", "cheaper"), kept apart from items."""
    language: Language = "en"
    prompt_version: str = Field(min_length=1)
    model: str = Field(min_length=1)
    usage: Usage = Field(default_factory=Usage)
    warnings: list[str] = Field(default_factory=list)
    """Plain notes such as "fallback keywords used"; the pipeline copies them to the response."""


class ItemEdit(VgaModel):
    """The shopper's chip edits for one detected item.

    ``None`` keeps the detected value. For ``colour`` an empty string clears it.
    """

    index: int = Field(ge=0, lt=MAX_ITEMS)
    category: Category | None = None
    colour: str | None = Field(default=None, max_length=60)
    gender: Gender | None = None
    """A gender set here is the shopper's confirmation: it becomes ``explicit``."""


class ChipEdits(VgaModel):
    """Everything the shopper changed in the chips before searching again (PRD R3).

    The plan lists the budget under each item, but a request has one budget
    (``UnderstandResult.budget``), so it is request-wide here.
    """

    items: list[ItemEdit] = Field(default_factory=list, max_length=MAX_ITEMS)
    budget: Budget | None = None
    clear_budget: bool = False
    """True when the shopper removed the budget. Mutually exclusive with ``budget``."""

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        indexes = [item.index for item in self.items]
        if len(indexes) != len(set(indexes)):
            msg = "items must not repeat an index"
            raise ValueError(msg)
        if self.clear_budget and self.budget is not None:
            msg = "set either budget or clear_budget, not both"
            raise ValueError(msg)
        return self


class TierMix(VgaModel):
    """Share of results per price range, in percent. Must sum to 100 (PRD R14)."""

    budget: int = Field(ge=0, le=100)
    mid_range: int = Field(ge=0, le=100)
    premium: int = Field(ge=0, le=100)
    luxury: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _sums_to_100(self) -> Self:
        total = self.budget + self.mid_range + self.premium + self.luxury
        if total != 100:
            msg = (
                f"tier_mix must sum to 100, got {total} "
                f"(budget={self.budget}, mid_range={self.mid_range}, "
                f"premium={self.premium}, luxury={self.luxury})"
            )
            raise ValueError(msg)
        return self

    def share(self, tier: Tier) -> int:
        """Percentage for one price range."""
        return int(getattr(self, tier.value))

    def as_tuple(self) -> tuple[int, int, int, int]:
        """Percentages in display order (budget, mid_range, premium, luxury)."""
        return (self.budget, self.mid_range, self.premium, self.luxury)


class MixPreset(StrEnum):
    """The three presets from the PRD "Price ranges" table. Shared by the UI sidebar (10.1.3) and
    by the "cheaper without a budget" rule in the pipeline (A7), so the numbers live once."""

    EVEN = "even"
    VALUE_FIRST = "value_first"
    LUXURY_FIRST = "luxury_first"

    @property
    def label(self) -> str:
        return {
            MixPreset.EVEN: "Even",
            MixPreset.VALUE_FIRST: "Value first",
            MixPreset.LUXURY_FIRST: "Luxury first",
        }[self]

    @property
    def mix(self) -> TierMix:
        return _MIX_PRESETS[self]


_MIX_PRESETS: dict[MixPreset, TierMix] = {
    MixPreset.EVEN: TierMix(budget=25, mid_range=25, premium=25, luxury=25),
    MixPreset.VALUE_FIRST: TierMix(budget=40, mid_range=30, premium=20, luxury=10),
    MixPreset.LUXURY_FIRST: TierMix(budget=10, mid_range=20, premium=30, luxury=40),
}


class SettingsOverride(VgaModel):
    """Per-run changes chosen in the UI sidebar (plan 10.1.3, 15.2.3)."""

    tier_mix: TierMix | None = None
    budget: Budget | None = None


class RunOverrides(VgaModel):
    """The ``overrides`` argument of ``Pipeline.run`` (plan 13.1.5, 15.2.1).

    All parts are optional. Precedence for the budget: ``chips.budget`` over
    ``settings.budget`` over ``understood.budget``.

    - ``settings``: sidebar changes (price-range mix, budget). A change to these alone re-shapes
      cached candidates: no store requests and no OpenAI call.
    - ``chips``: the shopper's chip edits, applied to ``understood`` with no OpenAI call.
    - ``understood``: the earlier ``SearchResponse.understood``, reused instead of calling OpenAI.
    - ``query_embedding``: the earlier ``SearchResponse.query_embedding``, reused instead of the
      photo (the photo bytes are dropped after the first run: plan assumption A8).
    """

    settings: SettingsOverride | None = None
    chips: ChipEdits | None = None
    understood: UnderstandResult | None = None
    query_embedding: list[float] | None = Field(default=None, repr=False, exclude=True)


@dataclass
class QueryImage:
    """The shopper's photo as the image ranker sees it: bytes and/or its embedding.

    Deliberately a mutable dataclass: ``ImageRanker.score`` stores the embedding it computes in
    ``embedding`` so that a chip re-run can score again with ``image=None`` (plan 8.1.3, A8).
    Neither field appears in ``repr`` (BRD Rule 4).
    """

    image: bytes | None = field(default=None, repr=False)
    embedding: list[float] | None = field(default=None, repr=False)


# --------------------------------------------------------------------------------------------
# Stores and products
# --------------------------------------------------------------------------------------------

MAPPABLE_PRODUCT_FIELDS = frozenset(
    {"title", "price", "currency", "image_url", "product_url", "colour", "in_stock", "category"}
)
"""``Product`` fields a store's ``extraction.strategies[].fields`` may map. ``store`` is not
mappable: it always comes from the store's config."""

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,62}$")


class StrategyConfig(VgaModel):
    """One step of a store's extraction chain (plan 6.4). Strategies are tried in order."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    """Registered strategy: ``store_json``, ``json_ld`` and, if needed, ``embedded_json``,
    ``css``, ``shopify``. The fetch engine rejects a name it does not know."""
    fields: dict[str, str] = Field(default_factory=dict)
    """Product field to dotted JSON path (or CSS selector for ``css``)."""
    options: dict[str, Any] = Field(default_factory=dict)
    """Strategy-specific settings (items path, script selector, ...). Free-form on purpose, so a
    new strategy needs no change to this contract."""

    @field_validator("fields")
    @classmethod
    def _known_fields(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = sorted(set(value) - MAPPABLE_PRODUCT_FIELDS)
        if unknown:
            msg = f"unknown product field(s) {unknown}; allowed: {sorted(MAPPABLE_PRODUCT_FIELDS)}"
            raise ValueError(msg)
        return value


class ExtractionConfig(VgaModel):
    """How to read products out of a store's search response."""

    strategies: list[StrategyConfig] = Field(min_length=1)


class StoreConfig(VgaModel):
    """One store = one small config entry (PRD R4). Adding a store adds a YAML file, no code.

    Safe by default: ``enabled`` is false until a live smoke test passes (plan 12.x.3).
    """

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,39}$")
    name: str | None = Field(default=None, min_length=1, max_length=60)
    """Shopper-facing name, e.g. "6thStreet". Defaults to ``id``. Becomes ``Product.store``."""
    country: CountryCode
    currency: CurrencyCode
    search_url_template: str
    """https URL containing ``{query}``, replaced by the URL-encoded keywords."""
    allowed_hosts: list[str] = Field(min_length=1)
    """The store's own hosts and its image CDN hosts: the only hosts we fetch from or link to."""
    extraction: ExtractionConfig
    rps: float | None = Field(default=None, gt=0, le=5)
    """Requests per second to this store. ``None`` means ``Settings.rps_per_store``."""
    timeout_s: float | None = Field(default=None, gt=0, le=30)
    """Per-request timeout. ``None`` means ``Settings.timeout_s``."""
    max_response_bytes: int | None = Field(default=None, gt=0)
    """Size cap, in bytes, for one HTTP response from this store. ``None`` means
    ``Settings.max_response_bytes``."""
    max_variants: int | None = Field(default=None, ge=1, le=MAX_KEYWORDS)
    """How many of the 1-3 keyword variants (``ItemIntent.search_keywords``) to send to this
    store, taken in order. ``None`` means all of them."""
    genders: frozenset[Gender] | None = Field(default=None, min_length=1)
    """The genders this store sells for; ``None`` means all, or not known. Many of the stores an
    honest client can read are single-gender (women-only) boutiques, and the pipeline must not send
    a men's query to such a store or show its products for one: see ``sells_for_gender``. In YAML
    and JSON this is a list such as ``[women]``, written in a fixed order. It cannot be empty (a
    store that sells for nobody should be ``enabled: false``)."""
    tier_hint: Tier | None = None
    """``luxury`` marks a luxury-leaning store (affects the ``relative_range`` flag)."""
    enabled: bool = False

    @property
    def display_name(self) -> str:
        return self.name or self.id

    def sells_for_gender(self, gender: Gender | None) -> bool:
        """Whether a request for ``gender`` should go to this store.

        Yes when the store does not say which genders it sells for (``genders is None``), when no
        gender is asked for (``None``) or the request is ``unisex`` (that does not narrow the
        audience), when the store lists ``unisex`` (it sells for everyone), or when it lists
        the requested gender. Callers apply only a gender the shopper stated or confirmed
        (BRD Rule 8); an inferred one is shown, not applied, so it never reaches this method.
        """
        if self.genders is None or gender is None or gender is Gender.UNISEX:
            return True
        return Gender.UNISEX in self.genders or gender in self.genders

    @field_serializer("genders")
    def _genders_in_a_fixed_order(self, value: frozenset[Gender] | None) -> list[Gender] | None:
        # A set has no order; sorting by the enum's order keeps dumps and logs deterministic.
        if value is None:
            return None
        return [gender for gender in Gender if gender in value]

    @field_validator("allowed_hosts")
    @classmethod
    def _valid_hosts(cls, value: list[str]) -> list[str]:
        hosts: list[str] = []
        for raw in value:
            host = raw.strip().lower()
            if not _HOST_RE.match(host):
                msg = (
                    f"{raw!r} is not a plain host name (no scheme, path, port, wildcard or "
                    "IP address)"
                )
                raise ValueError(msg)
            if host not in hosts:
                hosts.append(host)
        return hosts

    @model_validator(mode="after")
    def _template_is_safe(self) -> Self:
        template = self.search_url_template
        if not template.startswith("https://"):
            msg = "search_url_template must start with https://"
            raise ValueError(msg)
        if "{query}" not in template:
            msg = "search_url_template must contain {query}"
            raise ValueError(msg)
        if "{" in template.replace("{query}", "") or "}" in template.replace("{query}", ""):
            msg = "search_url_template may only use the {query} placeholder"
            raise ValueError(msg)
        if "{query}" in urlsplit(template).netloc:
            msg = "the {query} placeholder must be in the path or query string, not the host"
            raise ValueError(msg)
        # Check the URL as it will look with a harmless query substituted in.
        probe = template.replace("{query}", "q")
        try:
            _check_https_url(probe)
        except ValueError as exc:
            msg = f"search_url_template is not a valid https URL: {exc}"
            raise ValueError(msg) from exc
        host = (urlsplit(probe).hostname or "").lower()
        if host not in self.allowed_hosts:
            msg = (
                f"search_url_template host {host!r} must be listed in allowed_hosts "
                f"{self.allowed_hosts}"
            )
            raise ValueError(msg)
        return self


class Product(VgaModel):
    """One product read from a store. The six required fields are PRD R6: a record missing any
    of them is dropped before it gets here."""

    title: str = Field(min_length=1, max_length=1000)
    price: float = Field(gt=0)
    currency: CurrencyCode
    image_url: HttpsUrl
    product_url: HttpsUrl
    store: str = Field(min_length=1, max_length=60)
    """The store's display name (``StoreConfig.display_name``). Also what the per-store cap of
    ``max_per_store`` counts, so display names must be unique across enabled stores."""
    colour: str | None = Field(default=None, max_length=60)
    in_stock: bool | None = None
    """``None`` means the store page does not say; only ``False`` removes a product (PRD R7)."""
    category: Category | None = None
    """Inferred from the title or breadcrumb by the ranker; ``None`` when ambiguous."""
    gender: Gender | None = None
    """Who the product is for, when the store's own data says so; ``None`` means unknown."""

    @field_validator("colour")
    @classmethod
    def _blank_colour_is_none(cls, value: str | None) -> str | None:
        return _blank_to_none(value)

    @property
    def key(self) -> str:
        """Stable id of this product within a request: its product URL. Used as the dictionary
        key of ``ImageRanker.score``."""
        return self.product_url


class StoreResult(VgaModel):
    """What searching one store produced (plan section 4)."""

    store_id: str
    status: StoreStatus
    products: list[Product] = Field(default_factory=list)
    duration_ms: float = Field(default=0.0, ge=0)
    strategy: str | None = None
    """Name of the extraction strategy that produced the products."""
    from_cache: bool = False
    dropped: dict[str, int] = Field(default_factory=dict)
    """Records dropped while extracting, as ``{reason: count}`` (plan 6.5.2, harness 11.2.2)."""
    detail: str | None = None
    """Short technical note for logs (e.g. "HTTP 403"). Never shown to shoppers."""

    @model_validator(mode="after")
    def _status_matches_products(self) -> Self:
        if self.status is StoreStatus.OK and not self.products:
            msg = "status 'ok' needs at least one product; use 'empty' for no results"
            raise ValueError(msg)
        if self.status is not StoreStatus.OK and self.products:
            msg = f"status {self.status.value!r} must not carry products"
            raise ValueError(msg)
        return self


# --------------------------------------------------------------------------------------------
# Ranked results
# --------------------------------------------------------------------------------------------


class Scores(VgaModel):
    """Score breakdown for one product, each 0-1 (PRD R8)."""

    text: Score
    image: Score | None = None
    """``None`` when there is no query photo or the image ranker failed or is off."""
    price: Score
    total: Score


class ScoredProduct(VgaModel):
    product: Product
    scores: Scores
    tier: Tier | None = None
    """Set by the tier shaper; ``None`` before shaping."""
    reason: str = ""
    """Short sentence using only facts the code knows (PRD R11)."""
    flags: list[Flag] = Field(default_factory=list)
    base_price: float | None = Field(default=None, gt=0)
    """The product's price in the base currency (``Settings.base_currency``), at the fixed rate in
    settings. Set only when ``product.currency`` differs from the base currency, and only by the
    price-range shaper; ``None`` for a product priced in the base currency itself (its own price
    is then already the base figure) and for one whose currency has no rate. Price ranges, their
    spans and the over-budget flag are all measured on this figure, so a page, the command line
    and the harness read it from here instead of converting again. It is approximate: the rate is
    fixed, not live. Show it with ``vga.money.format_price``."""


def _format_price(value: float) -> str:
    return f"{value:,.0f}" if value == round(value) else f"{value:,.2f}"


class TierResult(VgaModel):
    """One price range of the final list: its real price span, count and target (PRD R16)."""

    name: Tier
    price_min: float | None = Field(default=None, gt=0)
    price_max: float | None = Field(default=None, gt=0)
    currency: CurrencyCode | None = None
    target_count: int = Field(ge=0)
    count: int = Field(ge=0)
    flags: list[Flag] = Field(default_factory=list)
    results: list[ScoredProduct] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.count != len(self.results):
            msg = f"count ({self.count}) must equal the number of results ({len(self.results)})"
            raise ValueError(msg)
        if self.results:
            if self.price_min is None or self.price_max is None or self.currency is None:
                msg = "a range with results needs price_min, price_max and currency"
                raise ValueError(msg)
            if self.price_min > self.price_max:
                msg = "price_min must not exceed price_max"
                raise ValueError(msg)
            for scored in self.results:
                # The span is in the range's currency (the base currency), so a converted product
                # is measured on its base price and every other product on its own price.
                price = scored.base_price if scored.base_price is not None else scored.product.price
                if not self.price_min <= price <= self.price_max:
                    msg = (
                        f"result price {price} lies outside the span "
                        f"{self.price_min}-{self.price_max}"
                    )
                    raise ValueError(msg)
        elif any(v is not None for v in (self.price_min, self.price_max)):
            msg = "an empty range must not carry a price span"
            raise ValueError(msg)
        return self

    @property
    def display_label(self) -> str:
        """Header text in the PRD R16 format: ``Budget · 45-139 AED · 8 results``."""
        noun = "result" if self.count == 1 else "results"
        if not self.results or self.price_min is None or self.price_max is None:
            return f"{self.name.label} · no results"
        low, high = _format_price(self.price_min), _format_price(self.price_max)
        span = low if low == high else f"{low}-{high}"
        return f"{self.name.label} · {span} {self.currency} · {self.count} {noun}"


class GarmentGroup(VgaModel):
    """The four price ranges for one detected garment. A non-outfit request has one group."""

    item_index: int = Field(ge=0, lt=MAX_ITEMS)
    """Index into ``SearchResponse.understood.items``."""
    category: Category
    tiers: list[TierResult]

    @field_validator("tiers")
    @classmethod
    def _four_tiers_in_order(cls, value: list[TierResult]) -> list[TierResult]:
        if [tier.name for tier in value] != list(TIER_ORDER):
            msg = "tiers must hold exactly budget, mid_range, premium, luxury, in that order"
            raise ValueError(msg)
        return value

    @property
    def result_count(self) -> int:
        return sum(tier.count for tier in self.tiers)


class StepTiming(VgaModel):
    """One timed step (PRD R12). Mirrors the line written by ``vga.log.timed``."""

    step: str = Field(min_length=1)
    store: str | None = None
    duration_ms: float = Field(ge=0)
    status: str = "ok"


class StoreReport(VgaModel):
    """Per-store summary kept in the response (no products), for the UI and the harness."""

    store_id: str
    status: StoreStatus
    product_count: int = Field(default=0, ge=0)
    duration_ms: float = Field(default=0.0, ge=0)
    strategy: str | None = None
    from_cache: bool = False
    dropped: dict[str, int] = Field(default_factory=dict)
    reason: str | None = None
    """Plain-language reason shown to the shopper. Required for skipped stores."""

    @classmethod
    def from_result(cls, result: StoreResult, reason: str | None = None) -> Self:
        return cls(
            store_id=result.store_id,
            status=result.status,
            product_count=len(result.products),
            duration_ms=result.duration_ms,
            strategy=result.strategy,
            from_cache=result.from_cache,
            dropped=dict(result.dropped),
            reason=reason,
        )


class SearchResponse(VgaModel):
    """Everything one request produced (plan section 4)."""

    request_id: RequestId
    understood: UnderstandResult
    groups: list[GarmentGroup] = Field(default_factory=list)
    """One group per detected garment. May be empty when no store returned anything."""
    stores_used: list[StoreReport] = Field(default_factory=list)
    """Stores that contributed products (status ``ok``)."""
    stores_skipped: list[StoreReport] = Field(default_factory=list)
    """Every other store, each with a plain-language ``reason``."""
    timings: list[StepTiming] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: float = Field(default=0.0, ge=0)
    """Wall time of the whole request (the 30 s budget is checked against this)."""
    query_embedding: list[float] | None = Field(default=None, repr=False, exclude=True)
    """Embedding of the query photo, kept in memory so chip re-runs need no photo (A8). Excluded
    from JSON so dumps and logs stay small and carry nothing derived from the photo."""

    @model_validator(mode="after")
    def _stores_listed_correctly(self) -> Self:
        for report in self.stores_used:
            if report.status is not StoreStatus.OK:
                msg = f"stores_used may only hold status 'ok', got {report.store_id!r}"
                raise ValueError(msg)
        for report in self.stores_skipped:
            if report.status is StoreStatus.OK:
                msg = f"stores_skipped must not hold status 'ok': {report.store_id!r}"
                raise ValueError(msg)
            if not report.reason:
                msg = f"skipped store {report.store_id!r} needs a reason"
                raise ValueError(msg)
        return self

    @property
    def products(self) -> list[ScoredProduct]:
        return [scored for group in self.groups for tier in group.tiers for scored in tier.results]

    @property
    def result_count(self) -> int:
        return sum(group.result_count for group in self.groups)
