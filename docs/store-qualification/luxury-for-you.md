# Luxury For You qualification (2026-10-07)

**Verdict:** GO (conditional). The honest client received title, price, currency, image URL and product URL for 79 cards across three search pages, and `robots.txt` leaves the search path open (checked with protego). Conditions: (1) it needs the optional `css` extractor, (2) the price shown on each card is ambiguous between a list price and a "member" price (see Fields available), (3) each page is about 2.7 MB and took 7 to 15 s, which is expensive against a 30 s request deadline.

## Storefront

- Store: Luxury For You (LFY), a Dubai-founded, members-style luxury multi-brand e-tailer (public descriptions: 1,200+ designer brands, free membership, NFC-authenticated items).
- UAE English storefront: `https://luxuryforyou.com/ae_en/` (other locales exist, for example `us_en`). `https://www.luxuryforyou.com/` redirects (301) to the apex.
- Platform evidence: Next.js app (React streaming markup, `self.__next_f` payloads) in front of a Medusa commerce backend (image bucket hosts are named `medusa-*`), behind Cloudflare. This is inference from the HTML, not a documented fact.
- Catalogue seen: women and men, clothing, shoes, bags. Brands seen on result pages include Gucci, Prada, Fendi, Versace, Balenciaga, Moncler, Stella McCartney, Tory Burch, and some mid-range names (Max & Co, Vans, Karl Lagerfeld, BOSS).

## robots.txt

- Parser: **protego 0.7.0** (`Protego.parse(text).can_fetch(url, user_agent)`, UA = `vga-shopping-agent-demo/0.1 (store-qualification research)`). I also reviewed the file by eye; the stdlib `urllib.robotparser` was not used for any verdict.
- Fetched from `https://luxuryforyou.com/robots.txt`: 200, 1,074 bytes (the `www` host answered 301 to the apex first).
- Rules for `User-Agent: *` (the only group), quoted in full apart from the Sitemap lines:
  ```
  User-Agent: *
  Allow: /
  Disallow: /account/
  ```
- Search path: **no rule matches it**. Protego result for every URL actually requested: ALLOW for `https://luxuryforyou.com/ae_en/results?query=black%20blazer`, `...?query=jacket`, `...?query=shoes`, and for the product page `https://luxuryforyou.com/ae_en/products/blazer-delilah-21on`.
- Category/listing pages: ALLOW (protego) for `https://luxuryforyou.com/ae_en/categories/women-casual-jackets` (a URL form seen in search-engine results; not requested).
- Sitemap: ALLOW (protego) for `https://luxuryforyou.com/sitemap/default.xml` and `https://luxuryforyou.com/sitemap/products-1.xml`. 18 `Sitemap:` lines: `default.xml`, `categories.xml`, `collections.xml`, `products-1.xml` to `products-15.xml`, all under `https://luxuryforyou.com/sitemap/`. None was requested.
- Crawl-delay: none declared.

## Reachability

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://www.luxuryforyou.com/robots.txt` | 301 | 167 | 2.13 s | to `https://luxuryforyou.com/robots.txt` |
| 2 | `https://luxuryforyou.com/robots.txt` | 200 | 1074 | 2.15 s | text/plain |
| 3 | `https://luxuryforyou.com/ae_en/products/blazer-delilah-21on` | 200 | 2,637,347 | 7.68 s | the one product page; used before the search pages to find the search URL |
| 4 | `https://luxuryforyou.com/ae_en/results?query=black%20blazer` | 200 | 2,753,986 | 14.95 s | 28 cards |
| 5 | `https://luxuryforyou.com/ae_en/results?query=jacket` | 200 | 2,737,559 | 7.31 s | 28 cards |
| 6 | `https://luxuryforyou.com/ae_en/results?query=shoes` | 200 | 2,880,263 | 8.32 s | 23 cards |

All with HTTP/1.1, `server: cloudflare`. No challenge page, CAPTCHA or login wall in any body. `challenges.cloudflare.com` is referenced once in the product-page HTML (probably a Turnstile widget for a form), but the pages themselves served normal content.

## Search URL template

`https://luxuryforyou.com/ae_en/results?query={query}`

Found in the product page's own markup: suggested-search links such as `href="/ae_en/results?query=Sneakers"`. Percent-encode spaces (`black%20blazer`). Pagination was not tested (the page shows "You viewed 28 of 855 products" with Prev/Next controls).

## Data path

`css`: the product cards are server-rendered HTML in the response, no JSON endpoint was used.

Evidence:
- Search pages contain one JSON-LD block, type `ClothingStore` (the shop itself), **no** `Product` or `ItemList`, so `json_ld` does not work on search pages. The product page has a `Product` JSON-LD block (`name`, `description`, `image`, `sku`, `brand`, `offers`).
- Cards sit in `<div data-testid="products-list">` inside a React-streamed container `<div hidden id="S:9">` (the visible placeholder `data-testid="products-list-loader"` is a skeleton). A non-JavaScript client sees the cards in the hidden container; select by `data-testid`, not by the `S:9` id.
- Each card: `<a href="/ae_en/products/{slug}-{code}">` containing `<h4>` brand, `<p>` title, price `<span>` elements, a discount badge, and a hover overlay with `Available Color:` and `Available Sizes:`.

## Extraction strategy needed

`css` (plan module 6.4.5, an optional strategy; this store needs it). Use the `selectolax` **lexbor** backend (`from selectolax.lexbor import LexborHTMLParser`): with selectolax 1.0.0 (what `uv` installed today), `from selectolax.parser import HTMLParser` raises an ImportError saying the Modest backend is deprecated. Config selectors (observed):

- card: `[data-testid="products-list"] a[href^="/ae_en/products/"]`
- brand: `h4`; title: `p`; image: first `img` `src`; link: the card's `href` (relative, make absolute)
- price: the `<span>` elements whose text matches `AED` followed by digits; strip the bidi marks (see Price formats)

Fallback to consider: the product page `Product` JSON-LD (one product per request, so it does not scale to a search).

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `<p>` in the card (brand is the separate `<h4>`); also the card `aria-label="Open product {brand} {title}"` |
| price | yes, ambiguous | two AED figures per card: a struck-through price and a second price in a tinted box with a padlock icon plus a `NN%` badge. In 79 of 79 cards the boxed price is lower. Which price a non-member pays is **not verified**: the page's string table contains "Member price applied" and "View member price", and the site describes "insider pricing" for members. The product-page JSON-LD `offers.price` is one number (2000 for the sampled product); it was not matched to either card price |
| currency | yes | literal `AED` in the card text; `priceCurrency: "AED"` in the product JSON-LD |
| image URL | yes | `img src`, absolute, `https://luxuryforyou.com/images/{id}-{hash}-fp.webp` (two sizes in `srcset`; a second image appears on hover) |
| product URL | yes | `a href`, relative `/ae_en/products/{slug}-{code}` (79 of 79 cards) |
| in stock | partial | cards list `Available Sizes:` (so presumably in stock); an explicit availability value exists only in the product page JSON-LD (`InStock`, one page checked) |
| colour | yes | hover overlay text `Available Color: Black` (one colour string per card) |

Other fields seen but not needed: brand (`<h4>`), discount percentage, size list.

## Hosts

- Store host (links): `luxuryforyou.com` (also `www.luxuryforyou.com`, which redirects).
- Image host actually used by all 79 result cards: `luxuryforyou.com` (path `/images/`).
- Other hosts present in the page HTML, not used by result cards: `medusa-images-bucket.luxuryforyou.com`, `cms-images.luxuryforyou.com`, `medusa-railway-bucket.s3.us-east-1.amazonaws.com` (appears 1,704 times in the page, not in cards), `d44a129f23331121403cac8a2bd9c5c6.r2.cloudflarestorage.com`.
- Candidate `allowed_hosts`: `luxuryforyou.com`, `www.luxuryforyou.com`. Do not add the AWS or R2 hosts unless a later check shows result images served from them.

## Price formats seen

Verbatim from the card text, with Unicode bidirectional isolate characters (U+2066 and U+2069) around the currency and the amount:

- `⁦⁦AED⁩ 6,900⁩` (struck-through list price)
- `⁦⁦AED⁩ 3,250⁩` (boxed price)
- `⁦⁦AED⁩ 23,698⁩`, `⁦⁦AED⁩ 450⁩`
- Pattern: `AED`, space, integer with comma thousands separator, no decimals. A parser must strip U+2066 to U+2069 before matching.
- Product JSON-LD: `"price": "2000"`, `"priceCurrency": "AED"`.
- Observed over 79 cards: list price AED 620 to 26,940; boxed price AED 450 to 23,698.

## Currency / tier hint

AED. Tier: **luxury** (designer houses such as Gucci, Prada, Fendi, Versace, Balenciaga; boxed prices up to about AED 23,700). A few lower-priced items exist (for example shoes from about AED 450), so the store spans premium to luxury.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| black blazer | `https://luxuryforyou.com/ae_en/results?query=black%20blazer` | 200 | 28 cards on the page, "28 of 855 products". Blazers and jackets, men and women mixed; matching looks loose (855 hits) |
| jacket | `https://luxuryforyou.com/ae_en/results?query=jacket` | 200 | 28 cards, "28 of 120 products" |
| shoes | `https://luxuryforyou.com/ae_en/results?query=shoes` | 200 | 23 cards; no "viewed" counter shown. Appears to include children's shoes (brand Tartine et Chocolat, a kidswear label) |

## Requests made

6 (2 for robots.txt including one redirect hop, 1 product page, 3 search pages).

## Sample

`docs/store-qualification/samples/luxury-for-you/`

- `search-black-blazer.html` (about 37 KB): title, `h1`, result counter, and the first 8 of 28 product cards from the `black blazer` response, with the cards' markup unchanged. Everything else was removed, and an HTML comment at the top says so. It parses with the selectors above.
- `product-jsonld.json` (under 1 KB): the `Product` JSON-LD block of the sampled product page, unchanged.

## Risks and fragility

- **Size and latency:** 2.6 to 2.9 MB per page, 7.3 to 15 s per request. A response-size cap in the HTTP core (module 6.1.1) must be at least about 3 MB for this store, or the cards will be cut off. Two or three keyword variants per query could use most of a 30 s deadline; budget one variant for this store.
- **Price semantics:** list price versus a padlocked "member" price (see Fields). A shopper who clicks through may see a different price. Decide how to show it (for example use the lower figure and label it, or use the struck-through figure) before the tier shaper uses it. Not verified by a signed-in view (no login is allowed).
- **Markup fragility:** the card selectors depend on Tailwind-style markup and on React streaming (`div[hidden]`). `data-testid="products-list"` is the most stable hook seen. If a stream is not completed, the cards may be missing from the HTML.
- **Relevance:** search matches are loose (855 hits for `black blazer`), results mix men and women and include children's items for `shoes`. Category and gender filters in the ranking layer matter more here than at other stores.
- **JSON-LD URL mismatch:** the product page's `offers.url` is `https://luxuryforyou.com/ae_en/blazer-delilah-21on` (no `/products/`), which differs from the page URL. Link to the card `href`, not to JSON-LD.
- **Terms of use:** not reviewed (demo only). The site positions itself as a members-only club; check its terms before real users.
- **Not tested:** pagination, second-page requests, the other locales, and whether the response differs from the user's network.
