# How to add a store

This guide takes you from "I think this shop might work" to "it is searched with the others", one step at a time. It is written for a developer who has never added a store. For a store built on **Shopify** it needs no code: a store is one YAML file, a few test files and a short note. For any other kind of store it needs code and a decision, see [section 6](#6-special-cases).

Every command and file name below was checked against the repository: the offline test skeleton in step 3 was run against a real store's recordings, and the options of the qualification script were read from its code and its `--help` (the script itself was not run against any store while this guide was written). The examples use a made-up shop, `Example Boutique UAE` at `www.boutique.example`. Swap in your own values.

## The steps

0. [Before you start](#0-before-you-start): the store limit, the rules, one branch.
1. [Qualify the store](#1-qualify-the-store-before-you-write-anything): is it allowed, and can an honest client read it?
2. [Write the store file](#2-the-store-file): `config/stores/<id>.yaml`, every key explained.
3. [Write the tests](#3-the-tests): recorded answers, an offline test and a one-time live smoke test.
4. [Write the store note](#4-the-store-note): `docs/store-notes/<id>.md`.
5. [Enable it, and check afterwards](#5-enable-it-and-check-afterwards).
6. [Special cases](#6-special-cases): not Shopify, another currency, a wrong price, one gender, some categories.
7. [The terms-of-use check that is still owed](#7-the-terms-of-use-check-that-is-still-owed).

A checklist for the pull request is at the [end](#the-pull-request-checklist).

## 0. Before you start

- **The store limit.** The business set the maximum at **13 stores** (BRD, "In scope" and "Out of scope"), and 13 are enabled. A 14th needs the business to raise the limit (it did so on 2026-10-08, from 6 to 10 and then to 13), or you swap one out by setting `enabled: false` on another store. Ask before you start.
- **The product rules that apply** (from `CLAUDE.md`): every result links to the store's own product page, only on a host on that store's `allowed_hosts`; respect `robots.txt`; no login-walled pages; no CAPTCHA solving; a store that blocks an honest client is **dropped, never bypassed**; a store is unused unless it says `enabled: true`.
- **Readable candidates already qualified but not added** (held in reserve): The Bear House UAE, Good Times and Heba Shaikh (priced in pounds, so it needs a rate, [section 6](#b-the-store-prices-in-another-currency)). Their reports are in `docs/store-qualification/`. Luxury For You was also readable but needs an extractor that is not built. Starting from a reserve store saves the qualification step; still read its report and re-run step 1.5 before you trust it, because stores change.
- **Make a branch** and plan one small pull request for the store. `CLAUDE.md` asks for a `CHANGELOG.md` entry in the same change.
- **Time-box it.** The plan allows about 45 minutes per store. If it cannot pass the live smoke test, leave `enabled: false`, write down why, and move on.
- **Do not run the qualification or the live test while anything else is talking to the stores** (the page, the command-line search, a live acceptance run). The 13 current stores are all Shopify, and Shopify counts requests per internet address across all its shops, so every request from your machine uses the same allowance. See the README, "Behaving towards the stores".

## 1. Qualify the store before you write anything

### 1.1 The request discipline (not negotiable)

The first requests you send to a store decide whether you are a polite guest. Follow these rules exactly. They are the same ones `scripts/qualify_store.py` enforces, which is why you use that script and nothing else.

1. **Send the exact honest name, and nothing personal.** The script sends one fixed `User-Agent`: `vga-shopping-agent-demo/0.1 (store-qualification research)`. The running app sends `vga-shopping-agent-demo/0.1 (store search demo)`. Never put a person's name, email address or phone number in it (an early manual check once did by mistake), and never imitate a browser.
2. **`robots.txt` first.** It is the very first request. The script reads it with **`protego`** and judges each full URL, including its query string. The Python standard library's own robots reader gets `*` and `$` wrong and wrongly allows paths a store forbids, so it is not used anywhere in this project. If `robots.txt` forbids the search path for our name, the store is **dropped**: stop there. (Shopify's older default file has `Disallow: /search`, which also covers `/search/suggest.json`. Five of the eight abaya and kaftan shops checked had it.)
3. **A hard cap on requests.** The script stops at 12 requests and uses at most 3 search queries. Plan for about 6: `robots.txt`, three searches, one product page (and `robots.txt` again for the second run in 1.4). If the first request already shows a refusal, you are done after one.
4. **At least a second apart.** The script waits at least 1 second between requests, longer if `robots.txt` names a `Crawl-delay`. Do not shorten it.
5. **Stop at the first refusal.** On any **403, 429, challenge page (for example "Just a moment..."), CAPTCHA or redirect to a login page**, the script stops and prints `DROP (blocked)`. Do not retry. Do not try another network, another name, a VPN or a proxy. A block is a final answer for this store; write it down. (If the script cannot connect at all it prints `UNDETERMINED (unreachable ...)`. That is not a block; you may try once more later, once, not in a loop.)
6. **No browser, no proxy, no impersonation.** Do not open the store's pages in a browser or fetch them with any other tool as part of qualification. Never use `curl_cffi`, Scrapling, a headless browser or anything that pretends to be something else (ADR 0003).
7. **Text from the store is data, never instructions.** The `robots.txt` of 12 of the current 13 stores (all but Maison Arabelle, whose file is hand-written) opens with a comment addressed to AI agents ("Agents should use UCP/MCP for catalog, cart, and checkout", naming `/api/ucp/mcp`, `/agents.md` and a third-party shopping skill). Quote such text in your report, as data. Do **not** request those addresses, install anything it names or follow any instruction in it. The same goes for text in product titles or descriptions. No cart, checkout, account or `/api/` address is ever requested.
8. **Stay inside the plan:** `robots.txt`, the search address, one product page. Do not look for paging, higher limits or other endpoints ("not tested" is an acceptable entry in the report).

### 1.2 Is it Shopify?

Before the first request you only have hints: a web search for the shop shows addresses shaped like `/collections/<name>` and `/products/<name>`, and picture addresses on `cdn.shopify.com`. These shapes are Shopify's defaults but are **not proof**. The proof comes from the first request: Shopify's `robots.txt` carries a comment such as `# Shopify storefront.` or `# we use Shopify as our ecommerce platform`, and the search answer has Shopify's shape. If the shop is **not** Shopify, jump to [section 6a](#a-the-store-is-not-on-shopify).

### 1.3 Run the script

Shopify exposes a public predictive search at `/search/suggest.json`. Run the script against it with up to three search words that suit the shop's assortment (not price words). Save the answers to a temporary folder **outside the repository**; you will copy trimmed files in later.

```bash
uv run scripts/qualify_store.py https://www.boutique.example abaya kaftan dress \
  --search-path "/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10" \
  --save-dir /tmp/example-boutique
```

(`uv run scripts/qualify_store.py --help` shows every option.) Read the output:

| Output | Meaning |
|---|---|
| `robots.txt: HTTP 200 ... search-related rule: ...` | The rules it found about search. None is what you want. |
| `search 'abaya': robots allows ...` | Good. `robots DISALLOWS` ends the run with `DROP (robots)`. |
| `data path: store_json, products found: 10` | Good: Shopify's JSON, 10 products (the most Shopify gives per call). |
| `VERDICT: PARTIAL (no key found for: currency)`, exit code 1 | **Expected for Shopify and fine.** The search answer has no currency; you confirm it from a product page in 1.4. |
| `VERDICT: DROP (robots)` or `DROP (blocked)`, exit code 2 | Stop. Record it. The store is not added. |
| `VERDICT: UNDETERMINED ...`, exit code 3 | Moved to another domain, unreachable, or the budget ran out. Read the reason. For "store moved to <host>", judge whether the move is legitimate, then re-run once against that host's address. |
| `requests made: N` | Put this number in your report. |

### 1.4 Confirm the currency from one product page

Pick one product from the saved first answer (`/tmp/example-boutique/search-1.json`): take its `url` field and drop everything from the `?` on, giving `https://www.boutique.example/products/<handle>`. Then run the script again with only that address:

```bash
uv run scripts/qualify_store.py https://www.boutique.example \
  --product-url https://www.boutique.example/products/<handle> \
  --save-dir /tmp/example-boutique
```

It checks `robots.txt` again, then fetches that one page, and ends with `VERDICT: UNDETERMINED (no query given)`. That is expected for this run: it only means no search was made. Look for the currency in the saved page (the page is large; do not commit it):

```bash
grep -o '"priceCurrency": *"[A-Z]*"' /tmp/example-boutique/product.html
```

You want `AED`, or another currency the app can convert ([section 6b](#b-the-store-prices-in-another-currency)). Also glance at the store's `Shopify.currency` in the same page if the JSON-LD is missing.

### 1.5 Read the saved answers and decide

Open `/tmp/example-boutique/search-1.json` (and the others). Check:

- **Every record has** `title`, `price`, `image`, `url`, and `available`. A record missing a field is dropped by the app, so a store where most records lack one is not worth adding.
- **Hosts.** Product `url`s are on the store's own host; `image` addresses are on `cdn.shopify.com` (or write down the other image host).
- **Prices look right.** Do `price`, `price_min` and `price_max` agree? If `price_max` is larger than `price_min` on the records you searched for, `price` is the cheapest variant and may not be the garment: see [section 6c](#c-the-search-price-is-wrong-for-products-with-several-variants).
- **Who and what it sells.** Count the records by gender (look at `type` and `tags`) and by garment. This decides `genders` and `categories` in step 2. "Not seen" is not "not sold": say what you saw and how many records you looked at.
- **Price level.** Note the lowest, highest and median price, to choose `tier_hint` (`budget`, `mid_range`, `premium` or `luxury`).
- **Fit.** Does it fill a gap? The README's "thin spots" list shows what is missing: menswear, abayas below about AED 600, heels, skinny jeans, satin blouses.

### 1.6 Record the evidence

All of this goes in the repository, because the reasons a store was added or dropped must not live in your head:

1. **`docs/store-qualification/<id>.md`**: the qualification report. Copy the headings of an existing one, for example `docs/store-qualification/hanayen.md`: Verdict; Storefront (how you know it is Shopify, which host answers without a redirect); `robots.txt` (the rules that matter, quoted, and the agent-comment quoted as data); Reachability (a table of **every** request: address, status, bytes, time); Search URL template; Data path; Fields available; Hosts; Price formats seen; Currency and tier hint; Queries tried; Requests made; Sample; Risks and fragility. Rejected stores get a report too, a short one: the single reason and the request count.
2. **`docs/store-qualification/samples/<id>/`**: the evidence files: `robots.txt` as served, `suggest-<query>.json` (the first 4 of 10 products is enough, each `body` string cut to 300 characters), and optionally `product-jsonld.json` (the one `Product` block of the product page).
3. **A row in `docs/store-qualification/SUMMARY.md`** (store, verdict, currency, price seen, report link), and a line in `CHANGELOG.md`.

To cut each product's `body` (store-supplied HTML, large, never used) to 300 characters in a saved answer:

```bash
uv run python -c "import json,sys; p=sys.argv[1]; d=json.load(open(p,encoding='utf-8')); [x.update(body=(x['body'] or '')[:300]) for x in d['resources']['results']['products'] if 'body' in x]; json.dump(d,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=1,sort_keys=True)" path/to/file.json
```

Keep fixtures and samples trimmed; the repository is private and the files are not for redistribution (plan risk R10).

## 2. The store file

Create `config/stores/<id>.yaml`. The **file name must equal the `id`** (`example-boutique.yaml` holds `id: example-boutique`). The app loads every `*.yaml` in the folder; no code lists the stores. A store is **off unless `enabled: true`**, so start with `enabled: false`.

An annotated example (every key; the comments name the evidence and the notes file, as the existing files do):

```yaml
# Example Boutique UAE: a UAE women's dress and kaftan label on Shopify (single brand).
# Data path: Shopify's public predictive search, /search/suggest.json, which robots.txt leaves open.
# Evidence: docs/store-qualification/example-boutique.md. Quirks and what would break this file:
# docs/store-notes/example-boutique.md
id: example-boutique         # a-z, 0-9, - and _, at most 40 characters; must equal the file name
name: Example Boutique UAE   # shown to the shopper; at most 60 characters; unique among enabled stores
country: AE                  # two-letter code of the market; see the note on countries below
currency: AED                # the suggest response has no currency; this is the store's (product page JSON-LD)
search_url_template: "https://www.boutique.example/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10"
allowed_hosts:
  - www.boutique.example     # product links and the search address: the host that answers with no redirect
  - cdn.shopify.com          # product images
extraction:
  strategies:
    - name: shopify          # the only built strategy; its options are explained below
      options:
        max_price_spread: 1  # only if a product's variants can differ in price (6c); otherwise leave out
genders:
  - women                    # only if the store sells for one gender (6d); otherwise leave out
categories:
  - dresses                  # only if the store sells only some categories (6e); otherwise leave out
tier_hint: mid_range         # budget | mid_range | premium | luxury; informational, see below
rps: 1                       # optional; requests a second to this store; never above 1
timeout_s: 6                 # optional; seconds per request; the global default is 6
max_response_bytes: 2000000  # optional; size cap for one response; the global default is 2 MB
max_variants: 2              # optional; at most this many keyword variants (1 to 3)
enabled: false               # true only after the live smoke test passes (step 5)
```

Leave out the optional keys you do not need. Real files to copy from: `config/stores/hanayen.yaml` (`genders`, `categories`, `tier_hint`), `signature-studio.yaml` (the `gender_fields` option, and a store that sells for both genders but only dresses), `maison-dvie.yaml` (the `image_width` option) and `hamsa-kw.yaml` (a dinar store with the `max_price_spread` price guard). No shipped file sets `rps`, `timeout_s`, `max_response_bytes`, `max_variants` or `name_field`: the global values apply, and the keys exist for a store that needs them.

### Every key

| Key | Required | What it does and how to choose it |
|---|---|---|
| `id` | yes | The store's short name. `a-z`, `0-9`, `-`, `_`, at most 40 characters. The file must be named `<id>.yaml`, or the loader refuses it. Used in logs, settings (`stores:`) and tests |
| `name` | no | What the shopper sees (`Product.store`). Defaults to `id`. At most 60 characters. **Must be unique among enabled stores**: the per-store cap of 6 results counts by this name |
| `country` | yes | Two-letter market code. A store is searched only if its country is `country` or listed in `extra_store_countries` in `config/settings.yaml`. For a new country, add it there too (Kuwait is `KW`). Without it the engine skips the store with "the store is for SA, which is not a country searched" and makes no request |
| `currency` | yes | Three-letter code of the prices in the search answer. Shopify's answer has none, so this comes from the product page (step 1.4) |
| `search_url_template` | yes | An `https://` address containing `{query}` and no other `{ }`. `{query}` goes in the path or query string, never in the host. Its host must be in `allowed_hosts`. Brackets are written as Shopify writes them; the app percent-encodes them |
| `allowed_hosts` | yes | The only hosts the app will fetch from or link to for this store. Plain lower-case host names: no `https://`, path, port, `*` or IP address. List the store's own host (the one that answered with no redirect: `www.` or the bare domain, not both unless both are used) and the image host. A redirect to a host not on the list is refused, and a product link or image on any other host is dropped |
| `extraction.strategies` | yes | A list. Only `shopify` is built. Do not add `fields` to it (rejected: the mapping is fixed). Options below |
| `rps` | no | Requests a second to this store. Defaults to the global `rps_per_store` (1). A test fails if any shipped store file sets it above 1 |
| `timeout_s` | no | Seconds allowed per request (up to 30). Defaults to the global 6. A slow store that needs more may be skipped by the 30-second deadline anyway |
| `max_response_bytes` | no | Size cap for one response. Defaults to the global 2,000,000 |
| `max_variants` | no | Send at most this many of the keyword variants (1 to 3). The global rule already sends one, and a second only if the first came back thin |
| `genders` | no | `women`, `men` or `unisex`, as a list that is never empty. A request for another gender is not sent to this store. Leave it out when the store sells for more than one gender, or you do not know |
| `categories` | no | Any of `tops`, `outerwear`, `bottoms`, `shoes`, `dresses`, as a non-empty list. The store is not searched for other categories (the shopper sees "Not searched: <store> does not sell shoes."). Leave it out when unsure |
| `tier_hint` | no | `budget`, `mid_range`, `premium` or `luxury`. Today only `luxury` has an effect: if no enabled store is `luxury`, the Luxury price range carries the warning "No luxury store was searched, so Luxury here only means the most expensive found". The other values document what you saw |
| `enabled` | no | Defaults to `false`. Only `true` makes the app use the store |

Unknown keys are rejected (`Extra inputs are not permitted`), so a typo cannot silently do nothing.

### The `shopify` options

All are optional and go under `options:` of the `shopify` strategy.

| Option | Default | What it does |
|---|---|---|
| `name_field` | `title` | Which field is the product name: `title` or `vendor`. Use `vendor` when `title` is a style code and the real name is in `vendor` (The Bear House) |
| `image_width` | `400` | Asks the image server for a picture this wide (a real image went from 108 KB to 20 KB). A positive whole number, or `null` to leave the address alone |
| `gender_fields` | `[type, tags]` | Which fields may say who a product is for, in the order that decides; `[]` turns the reading off. Recognised words: man, men, mens, menswear; woman, women, womens, womenswear, ladies; unisex. See the docstring of `src/vga/stores/extractors/shopify.py` |
| `max_price_spread` | off | A number of at least 1. Keep a record only when its highest variant price is at most this many times its lowest; drop the rest (6c) |

### Check the file

Nothing runs a search yet. Load it through the real loader (this makes no request). A mistake names the file and the field:

```bash
uv run python -c "from vga.stores.registry import load_store_configs; print([s.id for s in load_store_configs()])"
```

Real messages you may meet: `other.yaml: id: is 'example-boutique' but the file must be named example-boutique.yaml`; `example-boutique.yaml: (file): search_url_template host 'www.boutique.example' must be listed in allowed_hosts [...]`; `extraction.strategies.0 (shopify): unknown option(s) ['foo'] for the shopify strategy; allowed: [...]`; `categories.0: Input should be 'tops', 'outerwear', 'bottoms', 'shoes' or 'dresses'`.

## 3. The tests

Make `tests/stores/<id>/` (a folder named like the store id, with a hyphen if the id has one) holding:

```
tests/stores/<id>/
  conftest.py                  the `store` fixture: the real file through the real loader
  test_<id_with_underscores>.py   the offline test
  test_<id_with_underscores>_live.py   the one-time live smoke test (marked live)
  fixtures/
    robots.txt                 the store's file, byte for byte
    suggest-<query>.json       one saved answer per query, body cut to 300 characters
```

### 3.1 Fixtures (recorded answers)

Use the answers you already saved in step 1.3, so no extra request is needed:

1. Copy `/tmp/example-boutique/robots.txt` to `fixtures/robots.txt`.
2. Copy `search-1.json` to `fixtures/suggest-abaya.json`, `search-2.json` to `fixtures/suggest-kaftan.json`, and so on, named after the query each one answered (the order you gave on the command line).
3. Cut each product's `body` with the one-line command in step 1.6.
4. The offline test needs **at least 20 distinct valid products** in total (plan 12.x.2). Three queries of 10 products usually do; the same product answering two queries counts once. If you fall short, add another query in a **new** qualification run (and count its requests), never by hammering the store.

### 3.2 `conftest.py`

Copy `tests/stores/hanayen/conftest.py` and change the file name in `STORE_FILE`:

```python
"""Shared by the Example Boutique tests: the real store file, loaded the way the app loads it."""

import shutil
from pathlib import Path

import pytest

from vga.models import StoreConfig
from vga.settings import DEFAULT_STORES_DIR
from vga.stores.registry import load_store_configs

STORE_FILE = DEFAULT_STORES_DIR / "example-boutique.yaml"


@pytest.fixture
def store(tmp_path: Path) -> StoreConfig:
    """The store file through the real registry loader. Only this one file is copied into the
    folder the loader reads, so other stores' files cannot affect these tests."""
    shutil.copy(STORE_FILE, tmp_path)
    [loaded] = load_store_configs(tmp_path)
    return loaded
```

### 3.3 The offline test

This skeleton was run against Hanayen's real recordings (12 tests pass, `ruff check` is clean). Put your own values in the five constants, change the two image assertions if you set `image_width` or the pictures are not on `cdn.shopify.com`, and add tests for whatever is special about the store (below). Test through the real loader, the real extraction chain and the real search engine; fake only the network, as `tests/fakes.py` and `httpx.MockTransport` do.

```python
"""Example Boutique UAE store adapter, offline (plan 12.x.1 and 12.x.2).

The files in ``fixtures/`` are real answers from <date>: ``suggest-<query>.json`` is one
full Shopify ``/search/suggest.json`` response per query (only each product's ``body`` was cut to
300 characters) and ``robots.txt`` is the store's file, byte for byte. No network is used.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from protego import Protego
from tests.factories import make_item_intent, make_settings
from tests.fakes import FakeClock

from vga.models import Product, StoreConfig, StoreStatus
from vga.stores.engine import StoreSearchEngine
from vga.stores.extractors import ExtractionChain, default_registry
from vga.stores.extractors.chain import ChainOutcome
from vga.stores.normalise import dedupe_products
from vga.stores.urls import build_search_url

FIXTURES = Path(__file__).parent / "fixtures"
STORE_ID = "example-boutique"
DISPLAY_NAME = "Example Boutique UAE"
HOST = "www.boutique.example"
CURRENCY = "AED"
QUERIES = ["abaya", "kaftan", "dress"]
"""One saved answer per query: ``fixtures/suggest-<query>.json``."""


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def raw_count(query: str) -> int:
    data = json.loads(fixture_text(f"suggest-{query}.json"))
    return len(data["resources"]["results"]["products"])


def replay(store: StoreConfig, query: str) -> ChainOutcome:
    """The saved answer for ``query`` through the real extraction chain and validation."""
    return ExtractionChain(default_registry()).run(
        fixture_text(f"suggest-{query}.json"), store, build_search_url(store, query)
    )


# --- The store file (plan 12.x.1) --------------------------------------------------------------


def test_the_store_file_loads_through_the_real_registry_and_is_named_for_its_id(
    store: StoreConfig,
) -> None:
    assert store.id == STORE_ID
    assert store.display_name == DISPLAY_NAME
    assert store.currency == CURRENCY
    assert [strategy.name for strategy in store.extraction.strategies] == ["shopify"]


def test_the_search_url_is_shopifys_predictive_search_in_the_documented_shape(
    store: StoreConfig,
) -> None:
    assert store.search_url_template == (
        f"https://{HOST}/search/suggest.json?q={{query}}"
        "&resources[type]=product&resources[limit]=10"
    )
    assert build_search_url(store, "black abaya") == (
        f"https://{HOST}/search/suggest.json?q=black%20abaya"
        "&resources%5Btype%5D=product&resources%5Blimit%5D=10"
    )


def test_only_the_store_host_and_the_shopify_image_cdn_are_allowed(store: StoreConfig) -> None:
    assert store.allowed_hosts == [HOST, "cdn.shopify.com"]


def test_robots_txt_allows_the_search_path_and_still_closes_the_cart(store: StoreConfig) -> None:
    robots = Protego.parse(fixture_text("robots.txt"))
    agent = make_settings().user_agent

    for query in QUERIES:
        assert robots.can_fetch(build_search_url(store, query), agent)
    assert not robots.can_fetch(f"https://{HOST}/cart/", agent)  # parsed, not allow-all


# --- The saved answers through the real extraction chain (plan 12.x.2) -------------------------


@pytest.mark.parametrize("query", QUERIES)
def test_each_saved_answer_is_read_in_full(store: StoreConfig, query: str) -> None:
    outcome = replay(store, query)

    assert outcome.strategy == "shopify"
    assert outcome.examined == raw_count(query)
    # With a price option such as max_price_spread, some records are dropped on purpose: assert
    # the number you expect instead, and the reason in outcome.dropped.
    assert len(outcome.products) == outcome.examined
    assert outcome.dropped == {}


@pytest.mark.parametrize("query", QUERIES)
def test_every_product_has_the_six_required_fields_and_stays_on_allowed_hosts(
    store: StoreConfig, query: str
) -> None:
    for product in replay(store, query).products:
        assert product.title.strip()
        assert product.price > 0
        assert product.currency == CURRENCY
        assert product.store == DISPLAY_NAME
        assert urlsplit(product.product_url).hostname == HOST
        assert urlsplit(product.product_url).query == ""  # tracking parameters removed
        assert urlsplit(product.image_url).hostname == "cdn.shopify.com"
        assert parse_qs(urlsplit(product.image_url).query)["width"] == ["400"]


def test_the_saved_answers_give_at_least_twenty_distinct_valid_products(
    store: StoreConfig,
) -> None:
    every_product: list[Product] = [
        product for query in QUERIES for product in replay(store, query).products
    ]

    distinct, _repeats = dedupe_products(every_product)

    assert len(distinct) >= 20  # plan 12.x.2


# --- The whole search engine on the saved answers ----------------------------------------------


async def test_the_engine_reads_the_saved_answers_after_checking_robots_txt_once(
    store: StoreConfig,
) -> None:
    sent = QUERIES[:2]  # a store is sent at most two keyword variants, never a third
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                content=fixture_text("robots.txt").encode(),
                headers={"content-type": "text/plain"},
            )
        query = parse_qs(request.url.query.decode())["q"][0]
        return httpx.Response(
            200,
            content=fixture_text(f"suggest-{query}.json").encode(),
            headers={"content-type": "application/json; charset=utf-8"},
        )

    # The second variant is sent only when the first gave fewer than second_variant_below
    # products; each saved answer has ten, so raise the setting to see both requests.
    settings = make_settings(second_variant_below=50)
    engine = StoreSearchEngine(settings, clock=FakeClock(), transport=httpx.MockTransport(answer))
    try:
        [result] = await engine.search(
            make_item_intent(search_keywords=sent),
            [store.model_copy(update={"enabled": True})],  # the file's own flag is decided live
        )
    finally:
        await engine.aclose()

    assert result.status is StoreStatus.OK
    assert result.strategy == "shopify"
    assert [str(request.url) for request in seen] == [
        f"https://{HOST}/robots.txt",
        *[build_search_url(store, query) for query in sent],
    ]
    assert {request.headers["user-agent"] for request in seen} == {settings.user_agent}
```

Add a test for each thing your store file says, so the file cannot drift unnoticed:

- **`genders` set:** `assert store.genders == frozenset({Gender.WOMEN})`, `assert not store.sells_for_gender(Gender.MEN)` (Hanayen's test).
- **`categories` set:** `assert store.categories == frozenset({Category.DRESSES})` and `assert not store.sells_category(Category.SHOES)` (Hanayen's test).
- **`max_price_spread` set:** a test that the shipped file keeps the option, and one that shows the records that would have a wrong price are dropped (`tests/stores/hamsa-kw/test_hamsa_kw.py`).
- **A three-decimal currency:** a test that a price such as `"95.000"` is read as 95 dinars (Hamsa's test).
- **A quirk of the data** (a record type that is not a garment, a pre-sale price that is not used, a gender that only a tag gives): pin it with a real record, as the store notes' "Quirks seen" lists describe.

### 3.4 The one-time live smoke test

Copy `tests/stores/hamsa-kw/test_hamsa_kw_live.py` (or Hanayen's; Hamsa's also checks the currency) to `test_<id>_live.py` and change: the module docstring, `QUERIES` (two words that suit the assortment), `search_item`'s category, the currency check, and the final host check (`https://<host>/`). It is marked `live`, so it never runs by default or in CI. It builds the real `StoreSearchEngine` (honest name, `robots.txt` checked with `protego`, 1 request a second, a stop on any block), searches the two queries, and passes when each is `ok`, returns at least 3 valid products, and finishes within the store's timeout, using no more than 3 requests (`robots.txt` once and one search per query). It sets `enabled` itself, so it can run while the file says `enabled: false`.

Run it **once**, with nothing else talking to the stores and not within 15 minutes of any refusal:

```bash
uv run pytest -m live tests/stores/example-boutique -q
```

If it fails, **do not run it again in a loop**. Read the printed status and detail, fix the cause or leave the store disabled and write the reason in the store note.

### 3.5 Run what you wrote

```bash
uv run pytest tests/stores/example-boutique tests/fetch/test_registry.py tests/guards/scraping -q
uv run ruff check
```

`tests/fetch/test_registry.py` loads every shipped store file, and `tests/guards/scraping` includes a test that no shipped store file asks for more than 1 request a second.

## 4. The store note

Write `docs/store-notes/<id>.md`: what a developer needs when the adapter breaks. Copy the headings of `docs/store-notes/hanayen.md` (a Kuwaiti dinar store: `hamsa-kw.md`; a store with an extractor option: `signature-studio.md`):

1. **Header:** store id and display name, storefront address, config and test paths, links to the qualification report, **Status** (enabled or not, and the date of the live test).
2. **Data path:** `robots.txt`, the search request, how each field is mapped, where the currency comes from.
3. **Quirks seen:** anything surprising in the data (padding with unrelated products, a price that is not the garment's, gender in no field), each with evidence.
4. **What would break the adapter:** a table of change, what the engine reports (`blocked`, `robots_denied`, `error`, `timeout`) and what to do. The standard rows are in Hanayen's note: a block (disable it, never bypass), `robots.txt` closing search, Shopify changing the answer's shape, the store moving host, images moving host.
5. **Fallback if the endpoint changes:** normally "set `enabled: false`; the other stores keep working".
6. **Observed live:** the table from the live test (query, status, products, seconds, size), the request count, and the evidence for `genders` and `categories`.
7. **The `robots.txt` comment addressed to AI agents,** quoted as data and marked not acted on.
8. **Unverified** (what you did not test) and **Terms of use** (below).

## 5. Enable it, and check afterwards

1. The live smoke test passed. Edit the store file: `enabled: true`, and put the date and test path in the comment on that line, as the others do (`# the live smoke test passed on <date> (tests/stores/example-boutique)`). Set **Status: enabled** in the note.
2. Run everything. Do this locally: CI runs only the critical suite (143 tests), so this run is the only one that executes your new store's tests and the full guard suites.

   ```bash
   uv run pytest
   uv run ruff check
   uv run mypy src
   ```

3. Confirm the app now uses the store (this makes no request):

   ```bash
   uv run python -c "from vga.settings import load_settings; from vga.stores.registry import StoreRegistry; print([s.id for s in StoreRegistry.from_directory().active(load_settings())])"
   ```

4. Optionally run **one** real search that suits the store, with nothing else running (it asks every enabled store that sells the category, so keep it to one), and look at the JSON: the store should be in `stores_used` with products, not in `stores_skipped`, and there should be no warning that names it.

   ```bash
   uv run python -m vga.search --text "black abaya for women"
   ```

5. Update the counts and lists that name the stores: the README store table, the BRD/PRD/plan if the limit changed, `docs/store-qualification/SUMMARY.md`, and `CHANGELOG.md` (an "Added" entry, and "Found" for anything the live runs showed).
6. Know the cost: every Shopify store joins the same shared queue of 2 requests a second, so one more store adds about half a second to a full search.
7. Watch the first few searches for `blocked`, `robots_denied` or `cooldown` against the new store. If the store refuses, the app leaves it alone for 15 minutes. Do not retry; set `enabled: false` and write it in the note.

## 6. Special cases

### a. The store is not on Shopify

Only the `shopify` extraction strategy is built. A store on any other platform needs code: a new extractor class (`name`, `validate`, `extract`, see `src/vga/stores/extractors/base.py`) registered in `default_registry()`, with fixtures and tests of its own, and it gets its own request queue (`own:<id>`) because only Shopify is a known shared platform (`src/vga/fetch/platform.py`). That is a change to shared code, not a store file, and the plan keeps such work for later phases (17: the stores' agent endpoints; 18: store APIs and headless rendering, which needs a per-store terms sign-off; 19: category pages and a sitemap index). **Do not start it without the project owner's go-ahead.**

Also stop, and drop the store, in these cases (each was met in qualification): `robots.txt` disallows search; a bot challenge answers; the page is an empty JavaScript shell with no product data (a store that needs JavaScript is dropped, assumption A9); the search address redirects to an HTML page instead of JSON; the site's security certificate is invalid (the client will not bypass it); there is no `robots.txt` and the home page redirects to an unrelated domain.

### b. The store prices in another currency

1. Put its currency in the store file (`currency: KWD`).
2. Add a fixed rate to `fx_rates` in `config/settings.yaml` with its **source and date** in the comment, as the KWD entry does. Without a rate the app never converts that currency: its products get no budget comparison and are left out of the price ranges (with a warning). It never guesses.
3. A price with **three decimals** (`"245.000"`) is a price only for KWD, BHD and OMR; for any other currency it is refused (it more likely hides a thousands separator). Two decimals (`"535.00"`) are expected otherwise. A format that is neither is dropped with a logged reason; a new format is added to `src/vga/stores/prices.py` only when a store shows one.
4. If the store's country is not yet searched, add it to `extra_store_countries` (`config/settings.yaml`).
5. Confirm the currency on a product page, and check whether the store sells in several currencies by market (a `/en-us/` path or a region table): the file must pin the host that answers in the currency you set.
6. The page then shows the store's price and an approximate figure in the base currency, and ranges and budgets use that figure. Add a test like `tests/stores/test_kuwaiti_stores.py`. Read [ADR 0006](adr/0006-second-currency-fixed-rate.md).

### c. The search price is wrong for products with several variants

Shopify's `price` in the search answer is the **cheapest variant** of a product. If a shop lists a cheap item (a head scarf) as a variant of an expensive one (an abaya), `price` is the cheap one. To find out, list the records whose lowest and highest variant prices differ (run it on a saved answer):

```bash
uv run python -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); [print(p['title'][:40], p['price'], p['price_min'], p['price_max']) for p in d['resources']['results']['products'] if p.get('price_min')!=p.get('price_max')]" tests/stores/hamsa-kw/fixtures/suggest-abaya.json
```

On Hamsa's saved answer this prints the five abayas whose `price` is not the abaya's. If your garments show up in the list, set `max_price_spread` under the `shopify` options: `1` keeps only records whose variants all cost the same; `1.25` tolerates a small surcharge. Any other record is **dropped, never corrected**, as is a record whose `price_min` or `price_max` is missing, because the answer cannot say which variant is the garment. The cost is fewer products from that store. Pin it in the offline test and, in the store note, say how many records the rule removes. Never enable such a store without the option (`docs/store-notes/hamsa-kw.md`).

### d. The store sells for one gender

Set `genders` (for example `[women]`) when the evidence shows one gender, and say how many records you looked at. A request for another gender is then not sent to the store. If the store sells for several genders and names them in `type` or `tags`, leave `genders` out and let the extractor read the words (the `gender_fields` option: the first field that names a gender decides, so list `type` before `tags` when `type` is the reliable one). If nothing names a gender anywhere, the product's gender stays unknown and the ranker reads the title. Do not guess from the shop's name or look.

### e. The store sells only some categories

Set `categories` (for example `[dresses]`) when the shop sells only those garments, so that, say, a search for shoes is never sent to an abaya shop (it wastes a request and returns unrelated items). Be honest in the note: "not seen" is not "not sold". Leave `categories` out when the shop's `type` field is a collection label rather than a garment type, as at Manal Smaoui, and let the ranker sort by title.

### f. Other problems you may meet

| Symptom | What to do |
|---|---|
| The title is a style code and the name is in `vendor` | `name_field: vendor` |
| Pictures are huge or on another host | The default `image_width: 400` shrinks Shopify pictures; add the other host to `allowed_hosts` if the images are not on `cdn.shopify.com` |
| `www.` and the bare domain both answer | Qualify one, pin that host in `search_url_template` and `allowed_hosts`. A redirect to a host not on the list is refused |
| Same product repeated under several listings | The app collapses repeats within a search; say how many distinct products come back in the note |
| The answer is slow or big | `timeout_s` (up to 30), `max_response_bytes`, `max_variants: 1`. Luxury For You needs 15 s, about 3 MB and one variant, and also an extractor that is not built |
| The pre-sale (`compare_at`) price is at or below the price | The extractor never reads it; nothing to do, but note it |
| All prices are on sale | Note it: the budget band moves when the sale ends (Nishat Linen UAE) |

## 7. The terms-of-use check that is still owed

`robots.txt` is a technical signal, not a licence. Product rule 6 says: **before any real shopper uses this, someone must read each store's terms of use** (and any affiliate programme) and decide whether showing that store's prices and links, and searching it automatically, is allowed. Nothing about the 13 current stores has been reviewed.

For each new store:

1. Put the line **`Terms of use: not reviewed (demo only). BRD Rule 6 requires a review before real users.`** at the end of the store note, as the existing notes do.
2. Record anything in `robots.txt` that bears on it, as quoted data: a content-use line (Maison Arabelle's reads `ai-train=yes, search=yes, ai-retrieval=yes, ai-personalization=no`) and the stated preference for the store's own agent endpoint. These are for the terms review and for Phase 17, not for you to act on.
3. When the review happens, the reviewer reads the terms of use, the privacy policy and any rules for automated access; records the date, what was read and the decision in the store note; and says whether affiliate links or a partnership are possible. A consolidated per-store checklist (`docs/store-notes/SUMMARY.md`) is planned (plan 16.2.3) and did not exist when this guide was written; until it does, the note is the record.
4. A store whose terms forbid this use is switched off (`enabled: false`), not worked around.

## The pull request checklist

- [ ] The store limit was checked, and the business agreed to the new store.
- [ ] Qualification followed section 1: `robots.txt` first, at most 12 requests (about 6), at least a second apart, stopped at any refusal, no browser or proxy; the request count is in the report.
- [ ] `docs/store-qualification/<id>.md`, trimmed samples in `docs/store-qualification/samples/<id>/`, and a row in `SUMMARY.md`.
- [ ] `config/stores/<id>.yaml` loads; the file name equals the `id`; `rps` is not above 1; `enabled` is `false` until the live test passes.
- [ ] `tests/stores/<id>/`: conftest, offline test (at least 20 distinct valid products), live test; trimmed fixtures.
- [ ] The live smoke test was run once, alone, and passed; its output is in the note.
- [ ] `docs/store-notes/<id>.md`, with the terms-of-use line.
- [ ] `uv run pytest` (the complete suite, run locally: CI runs only the critical suite), `uv run ruff check` and `uv run mypy src` pass.
- [ ] If the currency or country is new: `fx_rates` (with source and date) and `extra_store_countries` updated.
- [ ] `CHANGELOG.md` entry; README store table and other store counts updated.
- [ ] No secret, no personal data in any User-Agent, and no real shopper photo in the commit.
