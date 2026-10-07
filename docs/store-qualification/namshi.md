# Namshi qualification (2026-10-07)

**Verdict:** DROP (robots: `Disallow: ?q=` for `*` targets the search URL; decision rests on a conservative reading, see below)

No search-result page was requested, so there is no product data, no data path and no field check for this store. **Needs an orchestrator decision**, because the strict parser reads the file differently:

- Protego 0.7.0 on `robots.txt` exactly as served says the search URL is **allowed**. The rule's value `?q=` starts with neither `/` nor `*`, so strict RFC 9309 matching never matches any URL. `urllib.robotparser` says allowed too, on Python 3.12 and 3.14.
- Read for what it plainly says, the line `Disallow: ?q=` under `User-agent: *` blocks URLs with a `q=` search query, and the store's own search URL is `.../search?q={query}`. The other query-string rules in the same group are written as `/*name=`, so the missing `/*` looks like a typo, and the file also bans several scraper agents by name. Under BRD Rule 2 (respect robots.txt) the script applies such a rule conservatively as `*?q=`, which disallows the search URL, so the verdict is DROP.
- To overrule: re-run `uv run scripts/qualify_store.py https://www.namshi.com "black blazer" jacket shoes --search-path "/uae-en/search?q={query}"` after changing that one behaviour (the script's `MALFORMED_RULE` handling). That costs at most 4 further requests (3 searches and 1 product page). 6 of 12 requests are already used.

## Storefront

- UAE English storefront: **`https://www.namshi.com/uae-en/`** (confirmed by redirect and by the page's own links).
- `https://en-ae.namshi.com/...` also exists and answers `301` to `https://www.namshi.com/uae-en/...`. It is an alias, not a separate store.
- Namshi is a Noon-group company. Its page assets load from `f.nooncdn.com`.
- Reachable from this machine today, so the earlier timeout was transient. Responses were slow: `robots.txt` took 3.0 to 4.3 s in all three fetches, which is close to a 6 s per-phase timeout.

## robots.txt

Parser: **Protego 0.7.0**, through `scripts/qualify_store.py` (live run) and an offline replay of the saved body. `urllib.robotparser` was not used for the verdict. Three fetches of `https://www.namshi.com/robots.txt` (200, 452 bytes, `text/plain`) returned the same file, which has no crawl-delay and one sitemap line, `Sitemap: https://www.namshi.com/sitemap-index.xml`.

Group `User-agent: *` (applies to us; our token is not named anywhere):

```
User-agent: *
Disallow: /_svc/
Disallow: /_vs/
Disallow: /*discount_percent=
Disallow: /*arrival_date=
Disallow: ?q=
Disallow: /*nms_colour=
Disallow: /*nms_occasion=
Disallow: /*size_group=
```

Other groups: `GPTBot` has `Allow: /`; `BadBot`, `GoogleOther`, `python-requests`, `Bytespider` and `YandexBot` have `Disallow: /`.

Rule that applies to the search path: **`Disallow: ?q=`**.

| URL | Protego, file as served | Conservative reading (`?q=` as `*?q=`) |
|---|---|---|
| `https://www.namshi.com/uae-en/search?q=black%20blazer` | allowed | **disallowed** |
| `https://www.namshi.com/uae-en/women/search/?q=blazer` | allowed | **disallowed** |
| `https://www.namshi.com/uae-en/women-clothing/` | allowed | allowed |
| `https://www.namshi.com/uae-en/women-clothing/?discount_percent=30` | disallowed | disallowed |

Side finding for plan task 6.2.1: on this same file `urllib.robotparser` reports `.../women-clothing/?discount_percent=30` as allowed on both 3.12 and 3.14, while Protego disallows it (rule `/*discount_percent=`). A checker built on Protego still allows `?q=` unless it also applies the conservative reading, so the Namshi config must stay `enabled: false` regardless of the checker.

## Reachability

| # | URL | Status | Bytes |
|---|---|---|---|
| 1 | `https://www.namshi.com/robots.txt` | 200 | 452 |
| 2 | `https://en-ae.namshi.com/robots.txt` | 301 | 162 |
| 3 | `https://www.namshi.com/uae-en/robots.txt` (redirect target of #2) | 308 | 19 |
| 4 | `https://www.namshi.com/uae-en/robots.txt/` (redirect target of #3) | 200, `text/html`: the UAE **homepage**, not a robots file | 510,229 |
| 5 | `https://www.namshi.com/robots.txt` (script re-run) | 200 | 452 |
| 6 | `https://www.namshi.com/robots.txt` (final script run with Protego) | 200 | 452 |

No 403, 429, CAPTCHA, login wall or challenge page was seen. Request #4 was an unplanned side effect: the script followed same-site redirects for `robots.txt` and landed on the homepage. It is outside the permitted request list, so it is disclosed here; the script now refuses an HTML response in place of a robots file. No search page and no product page was requested.

## Search URL template

`https://www.namshi.com/uae-en/search?q={query}`

Source: the store's own homepage JSON-LD (`WebSite` with a `SearchAction`, `urlTemplate`), seen in request #4. Category pages use `/uae-en/<gender-or-category>/search/?q=...`. Neither form was fetched.

## Data path

**Not determined.** No search page was requested because the search path is disallowed.

The one thing observed (homepage only, not a search page): the UAE storefront is server-rendered HTML with 8 `application/ld+json` blocks (`WebSite`, `Organization`, `LocalBusiness`, and `ContactPoint` entries), so search pages might carry data in HTML. That is a guess and is not evidence for any strategy.

## Extraction strategy needed

Undetermined (nothing to extract from). If the robots question is ever resolved in favour of fetching, test `json_ld` and `embedded_json` first, then `css`.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | not checked | no product response fetched |
| price | not checked | no product response fetched |
| currency | not checked | no product response fetched |
| image URL | not checked | no product response fetched |
| product URL | not checked | no product response fetched |
| in stock | not checked | no product response fetched |
| colour | not checked | no product response fetched |

## Hosts

Candidates for `allowed_hosts` if the store were ever enabled:
- Store: `www.namshi.com`. `en-ae.namshi.com` is an alias that redirects; do not allow-list it.
- Image CDN: **unverified**. `f.nooncdn.com` serves the homepage's icons and static assets, but no product image was seen.
- Other hosts on the homepage (not store hosts): `s.go-mpulse.net`, `s2.go-mpulse.net` (an analytics/performance beacon).

## Price formats seen

None.

## Currency / tier hint

Currency: AED expected (not observed). Tier hint: **budget to mid**, from web search results (brands such as Nike, Mango, adidas, Puma, New Balance), not from observed prices.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| black blazer | `https://www.namshi.com/uae-en/search?q=black%20blazer` | not requested (robots) | n/a |
| jacket | `https://www.namshi.com/uae-en/search?q=jacket` | not requested (robots) | n/a |
| shoes | `https://www.namshi.com/uae-en/search?q=shoes` | not requested (robots) | n/a |

## Requests made

6 (see Reachability): three fetches of `www.namshi.com/robots.txt`, one fetch of `en-ae.namshi.com/robots.txt` and the two redirect hops it led to. Limit 12. At least 1 s between requests.

## Sample

`docs/store-qualification/samples/namshi/`:
- `robots.www.namshi.com.txt`: the complete robots file (452 bytes), usable as a fixture for the `?q=` ambiguity.
- `homepage-website-jsonld.json`: the homepage's `WebSite` JSON-LD with the search URL template, plus a few search links seen in the homepage HTML. No product data.

## Risks and fragility

- **Ambiguous robots rule.** A strict parser allows the search URL and the conservative reading blocks it. The business or the orchestrator must decide; the safe default is no request.
- **Anti-scraper posture.** The robots file bans several automated agents by name (including `python-requests`) while allowing `GPTBot`. A listed User-Agent, a 403 or a challenge is likely if the search path is tried anyway. The homepage loads Akamai mPulse (`go-mpulse.net`), which hints at Akamai in front of the site; bot protection was not tested.
- **Slow origin.** `robots.txt` takes 3 to 4 s. The 6 s timeout leaves little margin, which probably explains the timeout seen earlier today.
- **Redirect traps.** `/robots.txt` on the `en-ae` alias redirects to an HTML homepage; a naive client could read it as an empty robots file.
- Terms of use were not read (Rule 6). A partner or affiliate route through the Noon group would be the legitimate way to get Namshi data.
