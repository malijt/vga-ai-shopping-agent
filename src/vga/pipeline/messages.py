"""Every sentence the pipeline writes for the shopper, in one place.

Warnings and store reasons are plain language that says what happened and, where it helps, what it
means for the results. They name stores by the store's own display name (from configuration, so
trusted) and never repeat the shopper's words or anything a store sent. The shopper-facing word for
a tier is "price range": the word "tier" appears nowhere below, and a test walks every message.
"""

from vga.models import Category, Gender, StoreConfig, StoreStatus

# --- Request validation (plan 13.1.1) -------------------------------------------------------

NOT_AN_IMAGE = (
    "That file is not a PNG, JPG or WebP photo. Please upload one of those, "
    "or describe what you are looking for in words."
)
UNREADABLE_PHOTO = (
    "We couldn't read that photo. Please upload a different PNG, JPG or WebP image, "
    "or describe what you are looking for in words."
)
EMPTY_PHOTO = "The photo you uploaded is empty. Please choose it again, or describe it in words."
PHOTO_TOO_SMALL = (
    "That photo is too small to recognise anything in. Please upload a larger one, "
    "or describe what you are looking for in words."
)
PHOTO_TOO_LARGE_DIMENSIONS = (
    "That photo is far larger than a normal picture. Please upload a smaller one, "
    "or describe what you are looking for in words."
)
RERUN_WITHOUT_EARLIER_RESULTS = (
    "We can't repeat that search because the earlier results are missing. "
    "Please start a new search."
)


def photo_too_large(max_bytes: int) -> str:
    megabytes = max_bytes / 1_000_000
    return (
        f"That photo is larger than {megabytes:g} MB. Please upload a smaller one, "
        "or describe what you are looking for in words."
    )


def text_too_long(max_chars: int) -> str:
    return f"Your description is longer than {max_chars} characters. Please shorten it."


# --- The deadline (plan 13.2.2) -------------------------------------------------------------

REQUEST_TIMED_OUT = (
    "The search took too long and was stopped before we could show anything. "
    "Please try again in a moment."
)
STORE_NOT_FINISHED = "This store had not answered when the time limit for the search ran out."


def deadline_warning(seconds: float) -> str:
    return (
        f"The search took longer than {seconds:g} seconds, so we are showing what we had by "
        "then. Some results may be missing."
    )


# --- Stores (plan 13.2.1, 13.2.3) -----------------------------------------------------------

NO_STORES_CONFIGURED = "No stores are set up to search right now, so there is nothing to show."
NO_RESULTS_ANYWHERE = (
    "No results right now: every store we tried was skipped or had nothing that matched."
)
SEARCH_CRASHED = "We could not search the stores for one of the items right now."

STORE_REASONS: dict[StoreStatus, str] = {
    StoreStatus.BLOCKED: "This store did not allow the search, so we skipped it.",
    StoreStatus.ROBOTS_DENIED: (
        "This store asks automated tools not to search it, so we skipped it."
    ),
    StoreStatus.COOLDOWN: (
        "This store turned down a recent request, so we are leaving it alone for a while."
    ),
    StoreStatus.TIMEOUT: "This store did not answer in time, so we skipped it.",
    StoreStatus.ERROR: "We could not read this store's results right now, so we skipped it.",
    StoreStatus.EMPTY: "This store had no products matching this search.",
}
"""``StoreReport.reason`` for every status except ``ok``."""

_STORE_WARNINGS: dict[StoreStatus, str] = {
    StoreStatus.BLOCKED: "{store} was skipped because it did not allow the search.",
    StoreStatus.ROBOTS_DENIED: "{store} was skipped because it asks automated tools not to "
    "search it.",
    StoreStatus.COOLDOWN: "{store} was skipped because it turned down a recent request.",
    StoreStatus.TIMEOUT: "{store} was skipped because it did not answer in time.",
    StoreStatus.ERROR: "{store} was skipped because its results could not be read.",
}
"""A store that failed is named in ``SearchResponse.warnings``. ``empty`` is not a failure."""


def store_partial_warning(store_name: str) -> str:
    """A store that answered for some of the shopper's items but not for all of them."""
    return f"{store_name} could not be searched for every item, so some results may be missing."


def store_reason(status: StoreStatus) -> str:
    return STORE_REASONS[status]


def store_warning(store_name: str, status: StoreStatus) -> str | None:
    """The warning for a store that failed, or ``None`` for ``ok`` and ``empty``."""
    template = _STORE_WARNINGS.get(status)
    return template.format(store=store_name) if template else None


_GENDER_WORDS: dict[Gender, str] = {
    Gender.MEN: "men",
    Gender.WOMEN: "women",
    Gender.UNISEX: "everyone",
}
_CATEGORY_WORDS: dict[Category, str] = {
    Category.TOPS: "tops",
    Category.OUTERWEAR: "outerwear",
    Category.BOTTOMS: "bottoms",
    Category.SHOES: "shoes",
    Category.DRESSES: "dresses and ethnic wear",  # the chip label: "Dresses" alone misses abayas
}


def gender_word(gender: Gender) -> str:
    return _GENDER_WORDS.get(gender, gender.value)


def category_word(category: Category) -> str:
    # A category added later reads as its own name until it is given a word here, rather than
    # turning a plain warning into a crash.
    return _CATEGORY_WORDS.get(category, category.value)


def store_not_for_gender(store: StoreConfig, gender: Gender) -> str:
    """The reason a store was not searched because it does not sell for ``gender``."""
    return f"Not searched: {store.display_name} does not sell clothing for {gender_word(gender)}."


def no_store_for_gender(category: Category, gender: Gender) -> str:
    return (
        f"None of the stores we search sell clothing for {gender_word(gender)}, so we could not "
        f"look for {category_word(category)}."
    )


def nothing_found_for(category: Category) -> str:
    return f"We found nothing that matched for {category_word(category)}."


# --- Understanding and ranking --------------------------------------------------------------

IMAGE_SIMILARITY_UNAVAILABLE = (
    "Results are ranked by text match and price only because image similarity was not available."
)
CHEAPER_WITHOUT_BUDGET = (
    "You asked for something cheaper but gave no budget, so we are showing more results in "
    "the lower price ranges."
)


def inferred_gender_note(gender: Gender) -> str:
    return f"Gender ({gender.value}) was guessed by the AI and is not applied until you confirm it."
