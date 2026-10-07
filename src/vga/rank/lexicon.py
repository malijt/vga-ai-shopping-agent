"""Word lists and small text helpers for the text and price ranking (plan 7.1.1 and 7.1.2).

English only: store titles are English. Everything here is plain data plus pure functions, so the
ranking stays deterministic and needs no model.

What lives here
- ``tokenize`` / ``canon``: one way to cut a title into lowercase words, shared by every ranker.
- The colour lexicon: ``normalise_colour``, ``find_colours`` and ``colour_affinity``.
- The category lexicon: which title words mean tops, outerwear, bottoms, shoes or dresses (dresses
  and ethnic wear), and which words name a garment or accessory outside those five (jumpsuit, bag,
  belt, sheila, ...).
- Gender cues in a title ("men's", "for women").

Store titles are untrusted data. Nothing here evaluates or executes them; they are only compared
with these word lists.
"""

import re
from dataclasses import dataclass
from typing import Literal

from vga.models import Category, Gender

Shade = Literal["dark", "light"]

# --------------------------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------------------------

_APOSTROPHES = re.compile("['" + chr(0x2019) + "`]")  # straight, curly and back quote
_WORD = re.compile(r"[^\W_]+")
_COMPOUNDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bt[\s-]?shirts?\b"), "tshirt"),
    (re.compile(r"\bco[\s-]?ords?\b"), "coord"),
    (re.compile(r"\b(?:two|2|three|3)[\s-]?pieces?\b"), "twopiece"),
    # "Night Dress" and "Sleep Gown" are nightwear. Dresses and gowns are a category, so the
    # two-word spellings are folded into the one-word nightwear marker (see OUT_OF_SCOPE_OVERRIDES).
    (re.compile(r"\b(?:night|sleep)[\s-]+(?=(?:dress|gown|shirt)(?:es|s)?\b)"), "nightwear "),
)


def tokenize(text: str) -> list[str]:
    """Lowercase words of ``text``. Apostrophes vanish ("men's" is ``mens``), ``&`` and ``+`` read
    as "and", hyphens and slashes split words, and a few compounds stay whole (``t-shirt`` is
    ``tshirt``, ``co-ord`` is ``coord``, ``two-piece`` is ``twopiece``)."""
    lowered = _APOSTROPHES.sub("", text.lower()).replace("&", " and ").replace("+", " and ")
    for pattern, replacement in _COMPOUNDS:
        lowered = pattern.sub(replacement, lowered)
    return _WORD.findall(lowered)


def singular(token: str) -> str:
    """Crude plural to singular, enough to match "blazers" with "blazer". Used for overlap only;
    the category word lists spell out their own plurals so that "short sleeve" is not "shorts"."""
    if len(token) <= 3:
        return token
    if token.endswith("ies"):
        return token[:-1]  # hoodies, booties, beanies: fashion nouns end in -ie, not -y
    if token.endswith(("sses", "xes", "ches", "shes")):
        return token[:-2]
    if token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


_SYNONYMS: dict[str, str] = {
    "trainer": "sneaker",
    "kick": "sneaker",
    "jumper": "sweater",
    "pullover": "sweater",
    "pant": "trouser",
    "tee": "tshirt",
    "overcoat": "coat",
    "topcoat": "coat",
    "raincoat": "coat",
    "jean": "jeans",
    "bootie": "boot",
    "windbreaker": "jacket",
}
"""Words that mean the same thing in a title, folded to one spelling before overlap is counted."""


def canon(token: str) -> str:
    """Singular form with a few synonyms folded together, for comparing title and request words."""
    base = singular(token)
    return _SYNONYMS.get(base, base)


STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "for", "with", "without",
        "from", "by", "as", "is", "are", "be", "it", "its", "this", "that", "these", "those",
        "me", "my", "i", "want", "need", "looking", "look", "find", "show", "get", "buy",
        "some", "any", "new", "style", "like", "similar", "please", "one", "pair", "set",
        "under", "below", "over", "above", "less", "than", "max", "maximum", "up", "about",
        "around", "cheap", "cheaper", "affordable", "budget", "price", "priced", "best",
        "aed", "sar", "usd", "kwd", "qar", "omr", "bhd", "dirham", "dirhams", "riyal", "riyals",
    }
)  # fmt: skip
"""Words that carry no product meaning, including price words: price is a filter, never a
search term (BRD Rule 7)."""

# --------------------------------------------------------------------------------------------
# Colours (7.1.1)
# --------------------------------------------------------------------------------------------

_DARK_WORDS = frozenset({"dark", "deep"})
_LIGHT_WORDS = frozenset({"light", "pale", "pastel"})


@dataclass(frozen=True)
class Colour:
    """A normalised colour: canonical ``name``, broader ``family`` and an optional ``shade``.

    ``normalise_colour("dark brown")`` is ``Colour("brown", "brown", "dark")``. A few names carry a
    shade of their own (navy is dark blue, ivory is light white).
    """

    name: str
    family: str
    shade: Shade | None = None

    @property
    def label(self) -> str:
        """Shopper-facing name, for example ``Black`` or ``Off-white``."""
        return self.name.capitalize()


_Synonym = str | tuple[str, Shade]

# (name, family, default shade, synonyms). A synonym given as a pair also fixes the shade.
_COLOUR_TABLE: tuple[tuple[str, str, Shade | None, tuple[_Synonym, ...]], ...] = (
    ("black", "black", None, ("jet black", "onyx", "noir", "ebony")),
    ("white", "white", None, ("snow", "pure white", "bright white", "optic white")),
    ("off-white", "white", "light", ("offwhite", "eggshell")),
    ("ivory", "white", "light", ()),
    ("cream", "beige", "light", ()),
    ("beige", "beige", None, ("nude", "sand", "oatmeal", "ecru")),
    ("taupe", "beige", None, ("greige",)),
    ("khaki", "green", None, ()),
    ("olive", "green", "dark", ("olive green", "army green", "military green")),
    ("grey", "grey", None, ("gray", "heather grey", "heather gray", "marl")),
    ("charcoal", "grey", "dark", ("slate", "graphite", "anthracite", "gunmetal")),
    ("silver", "metallic", None, ("metallic silver",)),
    ("gold", "metallic", None, ("golden", "rose gold")),
    ("bronze", "metallic", None, ("copper",)),
    ("brown", "brown", None, ("mocha", "chestnut", "walnut", ("chocolate", "dark"),
                              ("espresso", "dark"))),
    ("tan", "brown", "light", ("cognac", "caramel")),
    ("camel", "brown", "light", ()),
    ("burgundy", "red", "dark", ("maroon", "wine", "oxblood", "bordeaux", "claret")),
    ("red", "red", None, ("scarlet", "crimson", "ruby")),
    ("pink", "pink", None, ("rose", "dusty pink", ("blush", "light"), ("baby pink", "light"))),
    ("fuchsia", "pink", None, ("magenta", "hot pink", "fuchsia pink", "shocking pink",
                               "neon pink")),
    ("orange", "orange", None, ("tangerine",)),
    ("coral", "orange", None, ("salmon", "coral pink")),
    ("peach", "orange", "light", ("apricot",)),
    ("rust", "orange", "dark", ("terracotta", "burnt orange", "burnt sienna")),
    ("yellow", "yellow", None, ("canary", ("lemon", "light"), ("butter", "light"))),
    ("mustard", "yellow", "dark", ("ochre", "mustard yellow")),
    ("green", "green", None, ("lime", ("bottle green", "dark"), ("forest green", "dark"))),
    ("emerald", "green", None, ("emerald green", "jade")),
    ("sage", "green", "light", ("sage green", "pistachio")),
    ("mint", "green", "light", ("mint green",)),
    ("teal", "green", None, ()),
    ("blue", "blue", None, ("cobalt", "royal blue", ("sky blue", "light"),
                            ("baby blue", "light"), ("powder blue", "light"))),
    ("navy", "blue", "dark", ("navy blue", "midnight blue", "midnight", "indigo")),
    ("turquoise", "blue", None, ("aqua", "cyan")),
    ("purple", "purple", None, ("violet", ("plum", "dark"), ("aubergine", "dark"),
                                ("grape", "dark"))),
    ("lilac", "purple", "light", ("lavender", "mauve")),
    ("multi", "multi", None, ("multicolour", "multicolor", "multicoloured", "multicolored",
                              "multi colour", "multi color")),
)  # fmt: skip

_MAX_PHRASE = 3


def _build_colour_index() -> dict[tuple[str, ...], Colour]:
    index: dict[tuple[str, ...], Colour] = {}
    for name, family, shade, synonyms in _COLOUR_TABLE:
        entries: list[tuple[str, Shade | None]] = [(name, shade)]
        for synonym in synonyms:
            if isinstance(synonym, tuple):
                entries.append((synonym[0], synonym[1]))
            else:
                entries.append((synonym, shade))
        for phrase, phrase_shade in entries:
            key = tuple(tokenize(phrase))
            if not key or len(key) > _MAX_PHRASE:
                msg = f"bad colour phrase {phrase!r}"
                raise ValueError(msg)
            if key in index:
                msg = f"colour phrase {phrase!r} is listed twice"
                raise ValueError(msg)
            index[key] = Colour(name, family, phrase_shade)
    return index


_COLOUR_INDEX = _build_colour_index()

COLOUR_NAMES: frozenset[str] = frozenset(entry[0] for entry in _COLOUR_TABLE)
"""The canonical colour names (38 of them)."""


def split_colours(tokens: list[str]) -> tuple[list[Colour], list[str]]:
    """Find colours in ``tokens`` and return them with the tokens that were not part of one.

    The longest phrase wins ("hot pink" before "pink"). A "dark", "deep", "light", "pale" or
    "pastel" directly before a colour sets its shade and is consumed with it.
    """
    colours: list[Colour] = []
    rest: list[str] = []
    position = 0
    while position < len(tokens):
        shade: Shade | None = None
        start = position
        if tokens[position] in _DARK_WORDS | _LIGHT_WORDS and position + 1 < len(tokens):
            shade = "dark" if tokens[position] in _DARK_WORDS else "light"
            start = position + 1
        found: Colour | None = None
        length = 0
        for size in range(min(_MAX_PHRASE, len(tokens) - start), 0, -1):
            found = _COLOUR_INDEX.get(tuple(tokens[start : start + size]))
            if found is not None:
                length = size
                break
        if found is None:
            rest.append(tokens[position])
            position += 1
            continue
        colours.append(Colour(found.name, found.family, shade or found.shade))
        position = start + length
    return colours, rest


def find_colours(text: str | None) -> list[Colour]:
    """Every colour named in ``text``, in order. ``find_colours("Black Charcoal Pinstripe")`` is
    black then charcoal."""
    if not text:
        return []
    return split_colours(tokenize(text))[0]


def normalise_colour(text: str | None) -> Colour | None:
    """The first colour named in ``text``, or ``None``.

    ``normalise_colour("dark brown")`` is brown, shade dark; ``"Navy"`` is navy (blue family,
    dark); ``"gray"`` is grey; ``"banana"`` is ``None``.
    """
    colours = find_colours(text)
    return colours[0] if colours else None


def colour_affinity(wanted: Colour, found: Colour) -> float:
    """How well a colour found on a product fits the colour the shopper asked for, 0 to 1.

    - the same colour: 1, or 0.85 when the shopper asked for a shade the product does not state,
      or 0.5 when the shades are opposite ("light blue" against "blue" that is dark)
    - the same family but another name (charcoal for grey): 0.5, or 0.3 with opposite shades
    - anything else: 0
    """
    opposite = wanted.shade is not None and found.shade is not None and wanted.shade != found.shade
    if wanted.name == found.name:
        if opposite:
            return 0.5
        return 0.85 if wanted.shade is not None and found.shade is None else 1.0
    if wanted.family == found.family:
        return 0.3 if opposite else 0.5
    return 0.0


# --------------------------------------------------------------------------------------------
# Categories (7.1.2)
# --------------------------------------------------------------------------------------------


def _with_plurals(*words: str) -> frozenset[str]:
    forms: set[str] = set()
    for word in words:
        forms.add(word)
        if word.endswith("y") and word[-2] not in "aeiou":
            forms.add(word[:-1] + "ies")
        elif word.endswith(("s", "x", "ch", "sh")):
            forms.add(word + "es")
        else:
            forms.add(word + "s")
    return frozenset(forms)


CATEGORY_WORDS: dict[Category, frozenset[str]] = {
    Category.TOPS: _with_plurals(
        "tshirt", "tee", "shirt", "blouse", "top", "tank", "cami", "camisole", "polo",
        "sweater", "jumper", "pullover", "hoodie", "sweatshirt", "bodysuit", "tunic",
        "henley", "turtleneck", "rollneck", "singlet",
    ),
    Category.OUTERWEAR: _with_plurals(
        "jacket", "blazer", "coat", "trench", "parka", "puffer", "bomber", "anorak",
        "windbreaker", "raincoat", "overcoat", "topcoat", "peacoat", "cape", "poncho",
        "shacket",
    ),
    Category.BOTTOMS: _with_plurals(
        "trouser", "pant", "jean", "skirt", "skort", "legging", "jegging", "jogger",
        "chino", "culotte", "sweatpant", "capri", "bermuda",
    )
    # "khakis" is the plural noun for trousers ("Cargo Khakis"). Only the plural: a single "khaki"
    # is usually a colour ("Khaki Bomber Jacket" is outerwear), and it is in the colour table.
    | frozenset({"jeans", "shorts", "palazzo", "leggings", "joggers", "khakis"}),
    Category.SHOES: _with_plurals(
        "shoe", "sneaker", "trainer", "boot", "bootie", "heel", "sandal", "slipper",
        "loafer", "mule", "pump", "slide", "espadrille", "oxford", "brogue", "derby",
        "moccasin", "clog", "wedge", "stiletto", "slingback", "plimsoll", "ballerina",
    )
    | frozenset({"footwear", "flats"}),
    Category.DRESSES: _with_plurals(
        # dresses and gowns
        "dress", "gown",
        # Gulf and North African one-piece garments
        "kaftan", "kaftaan", "caftan", "abaya", "jalabiya", "jalabiyah", "jellabiya",
        "djellaba", "jilbab", "kandura", "thobe",
        # South Asian garments and sets
        "kurta", "kurti", "kameez", "lehenga", "anarkali", "sharara", "gharara",
    ),
}  # fmt: skip
"""Title words that name a garment in one of the five categories. Dresses and ethnic wear is the
fifth (BRD, 2026-10-08): dresses, gowns, kaftans, abayas, jalabiyas, kurtas and similar one-piece
or ethnic garments. Words that are ambiguous in retail use are left out on purpose (cardigan,
gilet, vest, kimono, overshirt, corset, suit, maxi, saree): a product with only those words has no
inferred category, so it is kept rather than dropped. "Suit" is the clearest case: a South Asian
suit at Nishat Linen UAE and a men's suit at Sacoor Brothers UAE, with nothing in the title to
tell them apart."""

OUT_OF_SCOPE_WORDS: frozenset[str] = _with_plurals(
    # one-piece garments the BRD does not cover: "similar" to a dress means a dress-like garment,
    # and a jumpsuit, playsuit or romper has legs. A robe is a bathrobe or dressing gown.
    "jumpsuit", "playsuit", "romper", "robe",
    # accessories
    "bag", "handbag", "tote", "clutch", "backpack", "rucksack", "wallet", "purse", "pouch",
    "satchel", "crossbody", "holdall", "suitcase", "belt", "hat", "cap", "beanie", "bonnet",
    "fedora", "visor", "headband", "hairband", "scrunchie", "scarf", "shawl", "stole",
    "glove", "mitten", "sunglass", "eyewear", "jewellery", "jewelry", "necklace", "pendant",
    "earring", "bracelet", "bangle", "ring", "brooch", "anklet", "charm", "watch", "tie",
    "necktie", "bowtie", "cufflink", "lanyard", "keyring", "keychain", "umbrella",
    # head coverings sold next to abayas, kurtas and kandouras
    "sheila", "shayla", "hijab", "niqab", "dupatta", "turban", "ghutra", "shemagh",
    # hosiery and underwear
    "sock", "stocking", "bra", "bralette", "knicker", "thong",
    # care products that search pads in ("black boots" finds boot polish)
    "hanger", "polish", "cleaner", "shoelace", "insole",
    # beauty and home
    "perfume", "fragrance", "cologne", "parfum", "candle", "cosmetic", "makeup", "lipstick",
    "mascara", "skincare", "voucher",
) | frozenset({
    "glasses", "sunglasses", "tights", "briefs", "underwear", "lingerie", "swimwear",
    "pyjamas", "pajamas", "nightwear", "sleepwear", "loungewear", "hosiery", "luggage",
    "scarves", "headscarf", "headscarves",
})  # fmt: skip
"""Title words that name something outside the five categories: jumpsuits and other one-pieces
with legs, accessories (including the sheilas and hijabs sold next to abayas), underwear,
swimwear, sleepwear, beauty. A title whose last garment noun is one of these is dropped by the
category filter, for every request."""

OUT_OF_SCOPE_OVERRIDES: frozenset[str] = _with_plurals(
    "bikini",
    "swimsuit",
    "tankini",
    "pyjama",
    "pajama",
    "nightdress",
    "nightgown",
    "nightshirt",
    "nightie",
    "lingerie",
    "boxer",
    "bathrobe",
) | frozenset({"swim", "swimwear", "swimming", "nightwear", "sleepwear", "underwear", "dressing"})
"""Words that put a title out of scope wherever they sit ("Bikini Top" is not a top). Dresses and
gowns are a category now, so nightwear and robes that are named after them must be caught here:
"Nightdress", "Night Dress" (folded into ``nightwear`` by ``tokenize``) and "Dressing Gown"."""

ETHNIC_SET_STARTERS: frozenset[str] = _with_plurals("kurta", "kurti", "kameez")
"""A kurta or kameez sold with trousers or a shirt is a set ("Kurta Trouser", "Kameez Trousers"),
not a pair of trousers. When one of these comes before the last garment noun of another category,
the title has no single category."""

SET_WORDS_ANYWHERE: frozenset[str] = _with_plurals("coord", "twopiece", "twinset", "tracksuit")
"""A garment set: the title does not say which single category it is. The exception is a set
named after a dress-category garment ("2 Piece - Embroidered Gown", "Kurta Set"): that is one
outfit in the dresses category, so ``classify_title`` skips these set words for it."""

SET_WORDS_TRAILING: frozenset[str] = _with_plurals("set", "suit")
"""Same, but only when they come after the garment noun ("Linen Blazer Set"; "Suit Trousers"
is a pair of trousers)."""

CATEGORY_BY_WORD: dict[str, Category] = {
    word: category for category, words in CATEGORY_WORDS.items() for word in words
}
for _word in OUT_OF_SCOPE_WORDS:
    if _word in CATEGORY_BY_WORD:  # pragma: no cover - guards the lists above against overlap
        msg = f"{_word!r} is in both a category list and the out-of-scope list"
        raise ValueError(msg)

HEAD_WORDS: frozenset[str] = frozenset(canon(word) for word in CATEGORY_BY_WORD)
"""Canonical garment nouns: a request for a "blazer" weighs this word more than "oversized"."""

CUT_WORDS: frozenset[str] = frozenset({"with", "w", "featuring", "for", "in", "from", "by"})
"""A title is read up to the first of these: what follows describes details ("Mule in Black",
"Heels With Diamante Brooches", "Blazer ... for women"), not the garment."""

COORDINATORS: frozenset[str] = frozenset({"and"})
"""Between two different garments this means a combined listing ("Shirt and Trousers")."""

# --------------------------------------------------------------------------------------------
# Gender cues
# --------------------------------------------------------------------------------------------

_MEN_WORDS = frozenset({"men", "mens", "male", "menswear", "gents"})
_WOMEN_WORDS = frozenset({"women", "womens", "ladies", "lady", "ladys", "female", "womenswear"})
_UNISEX_WORDS = frozenset({"unisex"})

GENDER_WORDS: frozenset[str] = (
    _MEN_WORDS
    | _WOMEN_WORDS
    | _UNISEX_WORDS
    | frozenset(
        {"boys", "girls", "kids", "man", "woman", "boy", "girl", "his", "her", "him", "hers"}
    )
)
"""Words that describe who a product is for. They are not product words, so overlap ignores them."""


CHILDREN_WORDS: frozenset[str] = _with_plurals(
    "boy", "girl", "kid", "baby", "toddler", "infant", "junior"
)
"""Title words that mark a children's product ("Boys Crew Neck T-shirt")."""

_BABY_FORMS = frozenset({"baby", "babies"})


def is_childrens_title(title: str) -> bool:
    """Whether the title marks a children's product: boys, girls, kids, baby, toddler, infant or
    junior (each also in its plural).

    Whole words only, so "boyfriend" and "kidskin" do not count. "Baby" is skipped where it is a
    shade or a style and not a child: before a colour word ("Baby Blue", "Baby Pink") and in "Baby
    Doll".
    """
    tokens = tokenize(title)
    for index, token in enumerate(tokens):
        if token not in CHILDREN_WORDS:
            continue
        following = tokens[index + 1 : index + 2]
        if (
            token in _BABY_FORMS
            and following
            and (following[0] == "doll" or find_colours(following[0]))
        ):
            continue
        return True
    return False


def title_gender(title: str) -> Gender | None:
    """The gender a title clearly states, or ``None``.

    Only clear cues count: "men's", "mens", "for men", "women's", "ladies". A title that cues both
    ("Men's & Women's") or neither is ``None``; "unisex" is ``Gender.UNISEX``. Singular "man" and
    "woman" are not cues ("man-made").
    """
    tokens = set(tokenize(title))
    if tokens & _UNISEX_WORDS:
        return Gender.UNISEX
    men = bool(tokens & _MEN_WORDS)
    women = bool(tokens & _WOMEN_WORDS)
    if men == women:
        return None
    return Gender.MEN if men else Gender.WOMEN
