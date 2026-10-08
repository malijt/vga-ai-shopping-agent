# Al Jazeera Clothing qualification (2026-10-08)

**Verdict:** GO, thin, pending the live smoke test. The honest client received title, price, image URL and product URL (plus availability) for 30 distinct products over four searches (40 records), from Shopify's public predictive search, and `robots.txt` leaves that path open (checked with protego). **The search only works on the store's English address, `/en/search/suggest.json`.** The plain `/search/suggest.json` answered HTTP 417 "Unsupported buyer locale" three times, because the store's default language is Arabic. Every price is in **Kuwaiti dinars (KWD)** with three decimals. The store is a Kuwaiti label of traditional menswear and it is thin for this demo: of the 30 distinct records, 18 are children's dishdashas (boys', youths', kids' and newborns'), 3 are men's dishdashas (all KWD 9, about AED 107), and 9 are men's underwear, nightwear and multipacks that are out of scope. Nine records (8 children's, 1 men's multipack) have variants at different prices, so the store file drops them (`max_price_spread: 1`). This is the store's name only; it has no relation to the news network.

## Storefront

- Store: Al Jazeera Clothing, `https://aljazeera-clothing.com/` (the apex answered with no redirect; `www.` was never requested). A Kuwaiti label of traditional menswear: dishdashas for men, youths and boys, plus underwear, nightwear and ghutras. Single brand: `vendor` is "JAZEERA" on all 30 distinct records. The shop name in the page data is "Aljazeera Clothing".
- Shopify shop `aljazeera-clothing.myshopify.com` (`Shopify.shop`), `Shopify.country` is `"KW"`, the theme is a custom one ("ALJ-v1-0-0-official", no theme-store id).
- **Language.** The default page is Arabic: `<html lang="ar" dir="rtl">` and `Shopify.locale = "ar"`. The page head declares three alternates: `x-default` and `ar` at `https://aljazeera-clothing.com/`, and `en` at `https://aljazeera-clothing.com/en`. The canonical address is the apex. English lives under the `/en` prefix, and the product links in the English search answer are `/en/products/<handle>`.
- Platform: Shopify. Evidence: robots.txt opens with `# Shopify storefront. Public product, collection, page, blog, policy, cart, and localized HTML is crawlable.`, its `Disallow: /96096026936` line is the shop id (the image folder `/s/files/1/0960/9602/6936/` is the same number and holds all 30 images), all 30 images are on `cdn.shopify.com`, the `/en/search/suggest.json` answer has Shopify's predictive-search shape, and the home page carries `Shopify.shop`, `Shopify.theme`, `Shopify.locale`, `Shopify.currency` and `Shopify.country`.
- Assortment seen in 40 search records (30 distinct handles): `type` "Apparel for kids" 18 and "Apparel for men" 12. By title: **21 dishdashas** (18 children's, including two "Sleeping Dishdasha" records, and 3 men's) and 9 men's records that are not dishdashas: a thermal set, a winter cotton set, a "6 Pcs" innerwear set, three pyjama sets, a "6 Pcs" half-pants set, a "6 Pcs" undershirt pack and a "12 Pcs" long-pants pack. All 9 carry the tag "Under Garments". No women's record was seen.
- The three adult dishdashas seen: "Men's Summer Dishdasha by Al Jazeera", "Men's Elegant Winter Dishdasha by Al Jazeera" and "Men's Winter Dishdasha by Al Jazeera", each KWD 9.
- **Wider assortment, from the saved home page only.** The Arabic home page (request 6) carries 86 handles that look like products in its page data. They are not search results and their titles were not read, so this is a hint and nothing more. Besides dishdashas it shows handles for boys' vests, boys' jackets, boys' shoes, men's and boys' sandals, bags, sunglasses (13), prayer mats, ghutras and shemaghs, passport holders, a perfume, socks, three girls' dresses (one a prayer dress, one a daraa), and two adult men's "sleeping dishdasha" products (`men-s-half-sleeve-stripes-summer-sleeping-dishdasha-by-al-jazeera` and `men-s-stripes-half-sleeve-v-neck-summer-sleeping-dishdasha-by-al-jazeera`). "Not seen" is not "not sold": no search record was a shoe, a jacket or a bag.
- The same page data shows a name-embroidery option on some dishdashas: "Custom name (+5.000 KWD)". The search `price` is the garment's base price and does not include it.

## robots.txt

- Parser: **protego 0.7.0**, with the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, through `scripts/qualify_store.py`. The stdlib `urllib.robotparser` was not used.
- Fetched from `https://aljazeera-clothing.com/robots.txt`: 200, 3,656 bytes, no redirect, on all four fetches (requests 1, 5, 7 and 11). The saved copies (from two of the runs), the test fixture and the sample are byte-identical (md5). Shopify's current default file with this shop's id line.
- Group `User-agent: *` opens with `Allow: /`, then `Allow:` exceptions for paths that merely contain `account`, `orders` or `checkout`, then disallows. Every rule has a `/*/...` twin for localised paths, so the `/en/` prefix is covered. Rules that matter here, quoted:
  ```
  Allow: /
  Disallow: /admin
  Disallow: /cart/
  Disallow: /*/cart/
  Disallow: /checkout
  Disallow: /*/checkout
  Disallow: /account
  Disallow: /*/account
  Disallow: /cart.js
  Disallow: /recommendations/products
  Disallow: /collections/*sort_by*
  ```
  A second group is for `adsbot-google` only.
- Search path: **no rule matches `/search`, `/en/search/suggest.json` or `/en/products/...`**; they are covered by `Allow: /`. Protego result, run offline on the saved file: ALLOW for the four `/en/` search URLs requested, ALLOW for the three plain-address search URLs that were refused (so the 417 is Shopify's answer, not a robots matter), ALLOW for a product page under `/en/products/`, DISALLOW for `/cart/` and `/en/cart/`. An offline pass also says ALLOW for `/en/search?q=thobe` (the HTML search page, never requested).
- Sitemap: `https://aljazeera-clothing.com/sitemap.xml`. Crawl-delay: none.
- The comment block at the top is addressed to AI agents. Quoted as data, **not acted on**: "Agents should use UCP/MCP for catalog, cart, and checkout. Payment requires buyer approval." It also names `https://aljazeera-clothing.com/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, asks an agent that acts as a "personal assistant or personal shopper" to recommend that its user install a third-party shopping skill (`https://shop.app/SKILL.md`), says checkouts are for humans and must not be completed automatically, and gives a contact address (`bots@shopify.com`). These are comments, not robots rules. None of those URLs was requested, nothing was installed, and no cart, checkout or account address was touched. Review the stated preference at the terms-of-use step (BRD Rule 6).

## Reachability

All requests were sent on 2026-10-08 through WARP (see "Not verified / limits"), with the User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, robots.txt first in each run, at least a second apart.

| # | URL | Status | Bytes | Time | Notes |
|---|---|---|---|---|---|
| 1 | `https://aljazeera-clothing.com/robots.txt` | 200 | 3656 | 0.6 s | text/plain |
| 2 | `https://aljazeera-clothing.com/search/suggest.json?q=dishdasha&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 417 | 86 | 0.2 s | `{"status":417,"message":"Expectation Failed","description":"Unsupported buyer locale"}` |
| 3 | `https://aljazeera-clothing.com/search/suggest.json?q=thobe&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 417 | 86 | 0.2 s | same body |
| 4 | `https://aljazeera-clothing.com/search/suggest.json?q=men&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 417 | 86 | 0.2 s | same body |
| 5 | `https://aljazeera-clothing.com/robots.txt` (second run) | 200 | 3656 | 0.4 s | same bytes |
| 6 | `https://aljazeera-clothing.com/` (the Arabic home page) | 200 | 494352 | 1.5 s | fetched by mistake where a product page was meant; no JSON-LD `Product` on it |
| 7 | `https://aljazeera-clothing.com/robots.txt` (third run) | 200 | 3656 | 0.4 s | same bytes |
| 8 | `https://aljazeera-clothing.com/en/search/suggest.json?q=dishdasha&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 30468 | 0.5 s | application/json, 10 products |
| 9 | `https://aljazeera-clothing.com/en/search/suggest.json?q=thobe&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 28272 | 0.3 s | 10 products |
| 10 | `https://aljazeera-clothing.com/en/search/suggest.json?q=winter&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 29920 | 0.3 s | 10 products |
| 11 | `https://aljazeera-clothing.com/robots.txt` (fourth run, for the extra query) | 200 | 3656 | not recorded | same bytes |
| 12 | `https://aljazeera-clothing.com/en/search/suggest.json?q=men&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 26277 | 0.5 s | 10 products |

No challenge page, CAPTCHA or login wall, and no redirect. HTTP 417 is not a block (it is none of 403, 429, a challenge page or a login redirect): it is a locale error, and the plain address was not asked for again after the third refusal. Response headers were not recorded.

Requests 2 to 4 and 6 were wasted by the orchestrator's wrapper script, which did not treat a 417 as a stop (so it asked the plain address three times instead of once) and fetched the home page where it meant to fetch a product page. The `/en/` address was found from the home page's `hreflang="en"` link.

## Search URL template

`https://aljazeera-clothing.com/en/search/suggest.json?q={query}&resources[type]=product&resources[limit]=10`

(Brackets sent percent-encoded as `%5B` and `%5D`.) 10 asked for, 10 received each time. Larger limits and pagination were not tested.

**Why `/en/`.** The plain `/search/suggest.json?...` answered HTTP 417 with the 86-byte body `{"status":417,"message":"Expectation Failed","description":"Unsupported buyer locale"}` on all three tries (requests 2 to 4). The store's default locale is Arabic (`Shopify.locale = "ar"`), and the answer says the locale is unsupported. We read this as Shopify's predictive search not serving Arabic; that reading was not checked against Shopify's documentation. The English storefront under `/en` answers normally. The 417 body is saved as `tests/stores/al-jazeera-clothing/fixtures/suggest-417-unsupported-locale.json` and a test pins the failure.

## Data path

`store_json`, in the Shopify form handled by the `shopify` strategy.

Evidence: all four `/en/` responses are JSON `{"resources": {"results": {"products": [ ... ]}}}`; each product has `title`, `handle`, `url`, `price`, `price_min`, `price_max`, `compare_at_price_min`, `compare_at_price_max`, `available`, `image`, `featured_image`, `type`, `vendor`, `tags`, `body`, `id` and a `variants` list. The `variants` list is empty on 25 of the 30 distinct records and holds one entry (the variant the search matched) on 5.

## Extraction strategy needed

`shopify` (plan module 6.4.6): the same strategy as the thirteen enabled stores. Store-specific points:

- **The address has `/en/` in it** (see above). Pin the host `aljazeera-clothing.com`. Product links come back as `/en/products/<handle>?_pos=...&_psq=...&_psid=...&_ss=e` (and on 5 of 30 records `&variant=<id>`). The strategy keeps the path, so the link is `https://aljazeera-clothing.com/en/products/<handle>`, the English page.
- **Currency is KWD with three decimals** (`"9.000"`, `"2.250"`), the second-currency path of ADR 0006: `currency: KWD`, `country: KW`, and the shipped fixed rate. Handles do not always match titles ("Boys' Beige Summer Dishdasha" is `/en/products/beige-dishdasha-al-jazeera-for-kids-ramadan-edition-with-name-embroidery`), so always use `url`.
- **`price` is the cheapest variant.** On 9 of 30 distinct records `price_min` differs from `price_max`: eight children's dishdashas (KWD 12 to 14 twice, 6 to 7 four times, 5 to 6, and 2 to 2.25) and one men's multipack (6.6 to 9). The one ranged record that lists its variant shows a size, "Light Gray / 6 Months (18 Inch)" at KWD 12 with a maximum of 14, so the lowest price is the smallest size. The three adult dishdashas have one price each. `max_price_spread: 1` (ADR 0012) drops the nine. The other seven ranged records list no variant, so that they are sizes is an inference.
- **Gender is in `type`.** "Apparel for men" on all 12 men's records, "Apparel for kids" on all 18 children's; `tags` agree ("men", "A/W men", "men new" on the men's; "boys", "kids", "A/W boys" on the children's). "Apparel for men" names men; "Apparel for kids" names no gender word, so the children's products have no gender and only the title (and the type) mark them.
- **`type` is not a garment.** It is a who-for label, so a category cannot come from it; the title decides. `categories: [dresses]` keeps shirt, trousers, jacket and shoe searches away from the store.
- The `body` is store-supplied HTML (cut to 300 characters in the saved answers); never render it.

## Fields available

| Field | Available? | Where |
|---|---|---|
| title | yes | `title` ("Men's Summer Dishdasha by Al Jazeera"; 26 of 30 contain "by Al Jazeera") |
| price | yes, with the caveat above | `price`, a string with three decimals (`"9.000"`); `compare_at_price_*` is `"0.000"` on all 30 (nothing marked down) |
| currency | not in the response | KWD is store-level: `Shopify.currency` `{"active":"KWD","rate":"1.0"}`, `shop.paymentSettings.currencyCode` `"KWD"` and `Shopify.country` `"KW"` on the home page; no product page was read, so no JSON-LD `priceCurrency` |
| image URL | yes | `image` and `featured_image.url`, absolute `https://cdn.shopify.com/s/files/1/0960/9602/6936/files/...?v=...` on 30 of 30 |
| product URL | yes | `url` (relative, `/en/products/<handle>`, with tracking and sometimes `variant=`) or build from `handle` |
| in stock | yes, product level | `available` (true for 30 of 30) |
| colour | partly | in some titles ("Beige", "Light Grey") and in the variant title ("White / M / 52") |
| gender | yes, from `type` | "Apparel for men" or "Apparel for kids"; see above |

## Hosts

- Store host (search address and product links): `aljazeera-clothing.com`.
- Image CDN: `cdn.shopify.com`, observed path prefix `/s/files/1/0960/9602/6936/` on all 30 records.
- Candidate `allowed_hosts`: `aljazeera-clothing.com`, `cdn.shopify.com`.

## Price formats seen

Verbatim from the responses:

- Search JSON: `"price": "9.000"`, `"price_min": "12.000"`, `"price_max": "14.000"`, `"price": "2.000"` with `"price_max": "2.250"`, `"compare_at_price_max": "0.000"`.
- Observed over 30 distinct handles, field `price`: **KWD 2 to 18, median 6.3**. Men's (12): KWD 5 to 18, median 7.5; the three dishdashas KWD 9. Children's (18): KWD 2 to 12, median 6 (the maximum variant price is KWD 14). At the shipped fixed rate (1 KWD = 11.92 AED, ADR 0006) a men's dishdasha is about AED 107 and the whole range about AED 24 to 215.

## Currency / tier hint

**KWD** (not AED). Tier: **budget**: a men's dishdasha is KWD 9, about AED 107, and everything seen is under about AED 215.

AED storefront: none seen. The home page's market picker lists seven markets (AU, AE, BH, KW, SA, OM and QA) and prices every one of them in KWD ("KWD د.ك | ..."), the UAE included. This is the same evidence as Hamsa's region table, but from the home page, not a product page.

## Queries tried

| Query | URL | Status | Products found |
|---|---|---|---|
| dishdasha | `https://aljazeera-clothing.com/en/search/suggest.json?q=dishdasha&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 9 children's dishdashas and 1 men's ("Men's Summer Dishdasha", KWD 9); 3 with variable prices |
| thobe | `https://aljazeera-clothing.com/en/search/suggest.json?q=thobe&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 9 children's (including "Newborn White Dishdasha") and the same men's summer dishdasha; 2 with variable prices |
| winter | `https://aljazeera-clothing.com/en/search/suggest.json?q=winter&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10: 8 children's and 2 men's ("Men's Elegant Winter Dishdasha", "Men's Winter Dishdasha"); 5 with variable prices |
| men | `https://aljazeera-clothing.com/en/search/suggest.json?q=men&resources%5Btype%5D=product&resources%5Blimit%5D=10` | 200 | 10 men's records: 1 dishdasha and 9 thermal, innerwear, pyjama and multipack records; 1 with variable prices (the half-pants set) |
| dishdasha, thobe, men (plain address) | `https://aljazeera-clothing.com/search/suggest.json?q=...` | 417 | none; "Unsupported buyer locale" |

Across the four answers: 40 records, 30 distinct, 21 distinct after the price rule.

## Requests made

12, the script's cap, all to `aljazeera-clothing.com`: 4 for robots.txt (one per run), 3 refused searches on the plain address, 1 home page, 4 searches on the `/en/` address. No product page. No redirects. See the note under Reachability on the four wasted requests.

## Sample

`docs/store-qualification/samples/al-jazeera-clothing/`

- `suggest-dishdasha.json`, `suggest-thobe.json`, `suggest-winter.json`, `suggest-men.json`: the first 4 of the 10 products of each real `/en/` response, same structure; each `body` string cut to 300 characters.
- `robots.txt`: the file as served.
- No `product-jsonld.json`: no product page was read.

## Risks and fragility

- **The `/en/` path.** If the store makes English its default language, the English page may move to the apex and `/en/` may stop answering; if Shopify starts serving Arabic, the plain address may start working and `/en/` may become unnecessary. Either way the store file's address is the thing to change (see the store note).
- **Thin.** Three adult dishdashas were seen in 30 distinct records, and eight or nine of the ten records in each of the three dishdasha answers were children's items (the adult dishdashas were 1, 1 and 2 of 10). Most of what a shopper would get from this store for a search that does not state "men" is boys' dishdashas.
- **The price rule** drops 9 of 30 records, 8 of them children's. If the store adds a size surcharge to the adult dishdashas, those would be dropped too.
- Currency and price format: KWD with three decimals (supported since ADR 0006), confirmed only from the home page, not from a product page.
- Children's records carry no gender, so the ranker has to recognise them by title. Four (three "Youth", one "Newborn") have no "boys" or "kids" word in the title.
- A name-embroidery option adds KWD 5 on some dishdashas (home page data); the search price does not include it.
- `body` is store-supplied HTML; never render it. `url` carries tracking parameters; do not link to them.
- The robots.txt asks agents to prefer the store's UCP/MCP endpoint; review before real users.
- Not tested: HTML search page, `limit` above 10, Arabic queries, a product page, women's items, behaviour from the user's own network, terms of use.

## Not verified / limits

- **Network path.** All requests were sent on 2026-10-08 between about 14:07 and 14:14 local time (PKT) by the orchestrator with `scripts/qualify_store.py` (User-Agent `vga-shopping-agent-demo/0.1 (store-qualification research)`, robots.txt first, at least 1 s apart, one store at a time). From about 13:00 the machine's own network path to Shopify's addresses timed out on connect (no refusal was ever received; a Cloudflare Community thread reports the same kind of time-out from Pakistani providers that week). The user then enabled Cloudflare WARP on the machine and the requests went through it. The User-Agent and every other rule were unchanged, and no store answered with a refusal. Behaviour from the machine's own network is untested.
- **No product page was read.** The currency rests on the home page (`Shopify.currency`, `shop.paymentSettings.currencyCode`, the market picker), not on a product page's JSON-LD `priceCurrency`. The home page that was fetched has three JSON-LD blocks (Organization, BreadcrumbList, WebSite) and no `Product`. The request budget (12) was spent before a product page was asked for.
- That Shopify's predictive search does not serve Arabic at all (the 417 was seen three times on one afternoon, for three queries).
- That the seven ranged records without a listed variant differ by size.
- Whether women's items exist (none seen in 30 records or in the home page handles), and whether the shoes, jackets and bags suggested by the home page's handles can be found by search.
- Terms of use: not reviewed.
