"""Every fixed phrase the shopper reads, in one place.

The UI says "price range", never "tier" (the code name for the same thing), and buttons say what
they do. A test walks the whole page and fails if the word "tier" appears. Nothing in this file
comes from a store or from the shopper, so it is safe to pass to functions that read markdown.
"""

from vga.models import Category, Flag, Gender, InputType, Step

APP_TITLE = "AI Fashion Shopping Agent"

# Trust notes (plan 10.1.1 and 10.1.2). Worded as the plan words them.
NOTE_DEMO = "Demo: results link to the store's own site."
NOTE_AI = "Matching is AI-assisted and can be wrong."
NOTE_PHOTO = "Your photo is sent to OpenAI for analysis and is not stored by us."

# Words for the buttons: each says what it does.
BUTTON_SEARCH = "Search stores"
BUTTON_APPLY_CHIPS = "Apply changes and search again"
BUTTON_RESET_CHIPS = "Reset to detected"

EXAMPLE_QUERIES: tuple[str, ...] = (
    "black oversized blazer for men under 400 AED",
    "wide-leg blue jeans for women under 250 AED",
    "جاكيت جلد أسود للرجال بأقل من 400 درهم",  # "black leather jacket for men under 400 AED"
)

# "Dresses" alone would read oddly for an abaya or a kurta, so the fifth label names both.
CATEGORY_LABELS: dict[Category, str] = {
    Category.TOPS: "Tops",
    Category.OUTERWEAR: "Outerwear",
    Category.BOTTOMS: "Bottoms",
    Category.SHOES: "Shoes",
    Category.DRESSES: "Dresses and ethnic wear",
}

GENDER_LABELS: dict[Gender, str] = {
    Gender.MEN: "Men",
    Gender.WOMEN: "Women",
    Gender.UNISEX: "Unisex",
}
GENDER_NOT_SET = "Not set"

# The question above the results when a gender was only guessed, or not found (BRD Rule 8). The
# buttons answer it: "Women" and "Men" use GENDER_LABELS, "Show both" closes it.
GENDER_QUESTION = "Who is this for?"
BUTTON_SHOW_BOTH = "Show both"
GENDER_NOT_STATED = "Your request does not say who it is for, so results for everyone are shown."
GENDER_GUESS_DIFFERS = (
    "The AI guessed different genders for different items. None has been applied."
)
# Where a guess came from, by what the shopper gave.
GUESS_SOURCE_WORDS: dict[InputType, str] = {
    InputType.TEXT: "your description",
    InputType.PRODUCT_PHOTO: "your photo",
    InputType.OUTFIT_PHOTO: "your photo",
    InputType.PHOTO_TEXT: "your photo and description",
}


def gender_guess_note(gender: Gender, input_type: InputType) -> str:
    """``The AI guessed women from your photo. It has not been applied.`` (BRD Rule 8)."""
    words = GUESS_SOURCE_WORDS[input_type]
    return f"The AI guessed {GENDER_LABELS[gender].lower()} from {words}. It has not been applied."


# The pipeline reports each step as it starts (plan 13.1.2). Present tense: it is happening now.
STEP_LABELS: dict[Step, str] = {
    Step.VALIDATE: "Checking your request",
    Step.UNDERSTAND: "Understanding what you are looking for",
    Step.SEARCH: "Searching the stores",
    Step.FILTER: "Filtering products",
    Step.RANK: "Ranking the matches",
    Step.IMAGE_RANK: "Comparing products with your photo",
    Step.SHAPE: "Sorting results into price ranges",
    Step.ASSEMBLE: "Putting the results together",
}

# Flags are shown as words, never by colour alone (UI rule).
FLAG_TEXT: dict[Flag, str] = {
    Flag.OVER_BUDGET: "Over your budget",
    Flag.FEW_OPTIONS: "Few options in this range",
    Flag.RELATIVE_RANGE: (
        "No luxury store was searched, so Luxury here only means the most expensive found"
    ),
}

ERROR_HEADLINE = "We could not finish that."
SETUP_HEADLINE = "Searching is not set up yet."
NO_RESULTS_HEADLINE = "No results right now."
NO_RESULTS_TIPS: tuple[str, ...] = (
    "Describe the item more simply, for example its type and colour only.",
    "Remove the budget or raise it.",
    "Check the category and colour in the Detected by AI section, then search again.",
    "Try again in a minute: a store may have been slow.",
)

PLACEHOLDER_NO_IMAGE = "No image available"


def approximate_price_note(base_currency: str) -> str:
    """The one sentence shown above results when a card has an "about" price (ADR 0006). The
    budget box names the base currency and is compared with that figure, so a shopper looking at
    ``245.000 KWD (about 2,920 AED)`` can tell which number a budget or a price range goes by.
    ``base_currency`` is ``Settings.base_currency``, a checked three-letter code."""
    return (
        f"A price in another currency also shows an approximate {base_currency} figure, "
        "and price ranges and your budget go by that figure."
    )
