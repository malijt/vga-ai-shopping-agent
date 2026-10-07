# ruff: noqa: RUF001  (Arabic letters look like Latin ones to the linter; they are meant)
"""English and Arabic word lists that the Understand step applies in plain code, after the model.

Three jobs, each one a rule the model alone cannot be trusted with:

- **Price words** (BRD Rule 7): "cheap", "budget", "رخيص" ... are filters, never search terms, so
  they are removed from every keyword whatever the model returned (plan 5.3.2).
- **Gender words**: a gender the model only *inferred* must not reach the search keywords (BRD
  Rule 8, plan 5.3.4), and a gender it calls *explicit* must really appear in the shopper's text.
- **Garment words**: the fallback (plan 5.3.1) has no model to say what category a request is
  about, so it reads a small garment word list instead.

The lists are deliberately short and will have gaps. A gender word they miss fails safe: the claim
is downgraded to "inferred" (shown, not applied). A price word they miss is a real leak of Rule 7
into a store search, so extend the list when the live eval or a shopper shows a gap.
"""

import re
import unicodedata

from vga.models import Category, Gender

# --------------------------------------------------------------------------------------------
# Arabic helpers
# --------------------------------------------------------------------------------------------

_ARABIC_MARKS = set(map(chr, range(0x064B, 0x0660))) | {"ـ"}  # tashkeel and tatweel
_ARABIC_FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})
_ARABIC_PREFIXES = ("وال", "بال", "لل", "ال", "و", "ب", "ل", "ف")


def fold_arabic(text: str) -> str:
    """Lower-case, drop Arabic diacritics and tatweel, and unify the common letter variants."""
    stripped = "".join(ch for ch in text.lower() if ch not in _ARABIC_MARKS)
    return unicodedata.normalize("NFKC", stripped).translate(_ARABIC_FOLD)


def _arabic_forms(token: str) -> list[str]:
    """The token and the forms left after dropping one prefix and/or a trailing tanween alef."""
    forms = [token]
    for prefix in _ARABIC_PREFIXES:
        if token.startswith(prefix) and len(token) > len(prefix) + 1:
            forms.append(token[len(prefix) :])
    return forms + [form[:-1] for form in forms if form.endswith("ا") and len(form) > 3]


# --------------------------------------------------------------------------------------------
# Price words (BRD Rule 7)
# --------------------------------------------------------------------------------------------

_AR_PREFIX = r"(?:وال|بال|لل|وب|ول|ال|و|ب|ل|ف)?"

_STRONG_QUALIFIER = (
    r"(?:under|below|beneath|less\s+than|lower\s+than|up\s+to|upto|at\s+most|within|budget\s+of"
    r"|(?<!air )max(?:imum)?"  # not "Air Max 90": a shoe, not a price
    r"|بأقل\s+من|باقل\s+من|أقل\s+من|اقل\s+من|بحد\s+أقصى|بحد\s+اقصى|حتى|لا\s+يتجاوز|اقصى|أقصى)"
)
"""Words that make a bare number a price ("under 300"). Safe without a currency."""

_WEAK_QUALIFIER = r"(?:around|about|over|above|more\s+than|between|بحدود|حوالي|أكثر\s+من|اكثر\s+من)"
"""Words that make a number a price only next to a currency ("around 300 AED")."""

_ANY_QUALIFIER = rf"(?:{_STRONG_QUALIFIER}|{_WEAK_QUALIFIER})"
_CURRENCY = (
    r"(?:aed|dhs?|dirhams?|sar|riyals?|qar|kwd|omr|bhd|usd|eur|gbp|\$|€|£"
    r"|درهم|دراهم|ريال|دينار|ر\.\s?س|د\.\s?إ)"
)
_NUMBER = r"\d[\d,.٫٬]{0,14}k?"  # bounded: a long run of digits cannot make a match slow
_TRAILING_LIMIT = r"(?:\s+(?:or|and)\s+(?:less|under|below|lower|fewer)|\s+max(?:imum)?|\s+tops?)"

_PRICE_PHRASES = re.compile(
    "|".join(
        [
            # Arabic "at a suitable price" must go before the single words below it.
            rf"(?<!\w){_AR_PREFIX}سعر(?:ه|ها)?\s+(?:ال)?مناسب(?:ه|ة)?(?!\w)",
            # "AED 400", "under $300"
            rf"(?<!\w){_ANY_QUALIFIER}?\s*{_CURRENCY}\s*{_NUMBER}(?!\w)",
            # "400 AED", "under 400 AED", "200-300 AED", "300 dirhams or less", "300 AED max"
            rf"(?<!\w){_ANY_QUALIFIER}?\s*(?:{_NUMBER}\s*(?:-|\u2013|to|and)\s*)?{_NUMBER}\s*"
            rf"{_CURRENCY}(?:{_TRAILING_LIMIT})?(?!\w)",
            # "under 300", "max 400", "300 or less"
            rf"(?<!\w){_STRONG_QUALIFIER}\s*{_NUMBER}(?!\w)",
            rf"(?<!\w){_NUMBER}\s+(?:or|and)\s+(?:less|under|below|lower|fewer)(?!\w)",
            # "< 400", "<=400", "\u2264 300" (no word boundary: "jacket<400" is common)
            rf"[<\u2264]=?\s*(?:{_CURRENCY}\s*)?{_NUMBER}(?:\s*{_CURRENCY})?(?!\w)",
        ]
    ),
    re.IGNORECASE,
)

_PRICE_WORDS = re.compile(
    "|".join(
        [
            r"(?<!\w)(?:"
            r"cheap(?:er|est)?|budget|affordable|inexpensive|economical|economy|bargains?"
            r"|discount(?:ed)?|sale|deals?|clearance|offers?|expensive|pricey|luxury|premium"
            r"|high[-\s]?end|low[-\s]?(?:price|cost|priced)|(?:best|good|great|lowest)\s+price"
            r"|value\s+for\s+money|on\s+a\s+budget|price[sd]?"
            r")(?!\w)",
            rf"(?<!\w){_AR_PREFIX}(?:"
            r"رخيص(?:ه|ة|ين)?|ارخص|أرخص|اقتصادي(?:ه|ة)?|ميزانيه|ميزانية|تخفيضات?|خصم|خصومات"
            r"|عروض|غالي(?:ه|ة)?|فاخر(?:ه|ة)?|سعر|اسعار|أسعار"
            r")(?!\w)",
        ]
    ),
    re.IGNORECASE,
)


def strip_price_words(text: str) -> str:
    """Remove price words and price phrases ("under 300 AED", "بأقل من 200 درهم") from ``text``.

    The budget is a filter (the model returns it in its own field), so none of it belongs in a
    store search. Spaces are left for the caller to collapse.
    """
    text = re.sub(r"\s+", " ", text)  # a long run of spaces would make the phrase patterns slow
    return _PRICE_WORDS.sub(" ", _PRICE_PHRASES.sub(" ", text))


# --------------------------------------------------------------------------------------------
# Gender words (BRD Rule 8)
# --------------------------------------------------------------------------------------------

_GENDER_PATTERNS: dict[Gender, re.Pattern[str]] = {
    Gender.MEN: re.compile(
        r"(?<!\w)(?:men(?:'s|’s|s)?|man|male|gents?|gentlem[ae]n|boys?|guys?|him|menswear"
        rf"|{_AR_PREFIX}(?:رجال(?:ي|ية|يه)?|شباب|ولادي|اولاد|أولاد))(?!\w)",
        re.IGNORECASE,
    ),
    Gender.WOMEN: re.compile(
        r"(?<!\w)(?:wom[ae]n(?:'s|’s|s)?|female|ladies|lady|girls?|her|womenswear"
        rf"|{_AR_PREFIX}(?:نساء|نسائي|نسائية|نسائيه|حريمي|حريم|سيدات|بنات|بناتي|ستاتي))(?!\w)",
        re.IGNORECASE,
    ),
    Gender.UNISEX: re.compile(
        rf"(?<!\w)(?:unisex|gender[-\s]?neutral|{_AR_PREFIX}(?:جنسين|يونيسكس))(?!\w)",
        re.IGNORECASE,
    ),
}


def mentioned_genders(text: str) -> set[Gender]:
    """Genders the text names in words ("for men", "للنساء"). Empty when it names none."""
    folded = fold_arabic(text)
    return {gender for gender, pattern in _GENDER_PATTERNS.items() if pattern.search(folded)}


def strip_gender_words(text: str) -> str:
    """Remove every gender word. Used on keywords when the gender was not stated by the shopper."""
    folded = fold_arabic(text)
    if not mentioned_genders(folded):
        return text
    # Fold only decides *whether* to strip. Stripping runs on the folded text so Arabic prefixes
    # and spellings match; Latin words are lower-cased by the fold, which keywords tolerate.
    result = folded
    for pattern in _GENDER_PATTERNS.values():
        result = pattern.sub(" ", result)
    return result


# --------------------------------------------------------------------------------------------
# Stop words: tokens that carry no meaning on their own
# --------------------------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    {
        "a", "an", "and", "or", "the", "for", "with", "in", "of", "on", "to", "by", "at", "from",
        "i", "me", "my", "want", "need", "looking", "look", "find", "please", "some", "any", "is",
        "are", "that", "this", "it", "like", "similar", "same", "but", "than",
        "و", "او", "في", "من", "على", "الى", "مع", "ل", "ب", "انا", "اريد", "ابغى", "ابي", "ابحث",
    }
)  # fmt: skip
_STOP_WORDS = frozenset(fold_arabic(word) for word in _STOP_WORDS)
"""Folded like the text they are compared with, so spellings such as "على" and "ابغى" match."""


def trim_connectors(text: str) -> str:
    """Drop stop words from both ends ("and black jacket for" becomes "black jacket"): what is
    left once a price phrase or a gender word is cut out of the middle of a sentence."""
    words = text.split()
    while words and fold_arabic(words[0]) in _STOP_WORDS:
        words.pop(0)
    while words and fold_arabic(words[-1]) in _STOP_WORDS:
        words.pop()
    return " ".join(words)


def meaningful_tokens(text: str) -> list[str]:
    """Words of ``text`` that name something: not stop words, not gender words, not digits only.

    Used to tell a real keyword ("black jacket") from leftovers ("and", "men", "300") once price
    words are gone.
    """
    tokens: list[str] = []
    for raw in re.findall(r"[^\W_]+", fold_arabic(text)):
        if raw in _STOP_WORDS or raw.isdigit() or mentioned_genders(raw):
            continue
        tokens.append(raw)
    return tokens


# --------------------------------------------------------------------------------------------
# Garment words, for the fallback only
# --------------------------------------------------------------------------------------------

_GARMENT_WORDS: dict[Category, tuple[str, ...]] = {
    Category.TOPS: (
        "shirt", "tshirt", "tee", "top", "blouse", "polo", "sweater", "jumper", "pullover",
        "hoodie", "sweatshirt", "cardigan", "jersey", "tank",
        "قميص", "تيشيرت", "بلوزه", "كنزه", "هودي", "سويتر", "بلوفر", "فنيله",
    ),
    Category.OUTERWEAR: (
        "jacket", "coat", "blazer", "parka", "bomber", "windbreaker", "puffer", "trench",
        "anorak", "gilet", "overcoat",
        "جاكيت", "جاكت", "سترات", "سترة", "معطف", "بلازر", "كوت", "جاكيته",
    ),
    Category.BOTTOMS: (
        "jeans", "pants", "pant", "trousers", "trouser", "shorts", "chinos", "joggers",
        "sweatpants", "leggings", "skirt", "cargo", "denim",
        "بنطلون", "بنطال", "جينز", "شورت", "تنوره", "ليقنز",
    ),
    Category.SHOES: (
        "shoe", "sneaker", "trainer", "boot", "loafer", "sandal", "slide", "heel", "flat",
        "oxford", "slipper", "footwear",
        "حذاء", "احذيه", "جزمه", "صندل", "بوت", "سنيكرز", "كوتشي", "كوتش", "نعال", "شبشب",
    ),
}  # fmt: skip

_GARMENT_LOOKUP: dict[str, Category] = {
    word: category for category, words in _GARMENT_WORDS.items() for word in words
}


def _category_of_token(token: str) -> Category | None:
    variants = [token, token.removesuffix("s"), token.removesuffix("es"), *_arabic_forms(token)]
    return next((_GARMENT_LOOKUP[v] for v in variants if v in _GARMENT_LOOKUP), None)


def garment_category(text: str) -> Category | None:
    """The category of the garment ``text`` names, or ``None``.

    In an English phrase the garment is the last word ("denim jacket" is a jacket, "oxford shirt"
    a shirt), so Latin words are read from the right. In Arabic the garment comes first ("جاكيت
    جلد"), so Arabic words are read from the left. Latin words win when both are present.
    "t-shirt" counts as "tshirt"; plurals are read by dropping a final "s" or "es".
    """
    folded = fold_arabic(text).replace("t-shirt", "tshirt").replace("t shirt", "tshirt")
    tokens = re.findall(r"[^\W_]+", folded)
    latin = [token for token in tokens if token.isascii()]
    other = [token for token in tokens if not token.isascii()]
    for token in [*reversed(latin), *other]:
        category = _category_of_token(token)
        if category is not None:
            return category
    return None


CATEGORY_NOUN: dict[Category, str] = {
    Category.TOPS: "top",
    Category.OUTERWEAR: "jacket",
    Category.BOTTOMS: "pants",
    Category.SHOES: "shoes",
}
"""A plain English noun for a category, used to rebuild keywords when the item has no style."""

GENDER_KEYWORD: dict[Gender, str] = {Gender.MEN: "men", Gender.WOMEN: "women"}
"""The word added to a search keyword for a gender the shopper stated. Unisex adds nothing."""
