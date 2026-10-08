# Store notes summary and terms-of-use checklist

> Written 2026-10-08 (plan feature 16.2.3) from the store files in `config/stores/`, the notes in
> this folder and the reports in [`../store-qualification/`](../store-qualification/SUMMARY.md). It
> first covered thirteen stores and was extended the same day when six more were enabled (the modest
> and ethnic wear pass, [record](../store-qualification/modest-ethnic-wear-discovery.md)). It was
> checked against the store files and the current code. No store was contacted to write it.

Nineteen stores are enabled. All are Shopify storefronts, read through Shopify's public
`/search/suggest.json` endpoint (at most 10 products per call). Eleven are in the UAE and price in AED.
Eight are in Kuwait and price in Kuwaiti dinar (KWD); the app shows an approximate AED figure beside
the dinar price (ADR 0006).

**Nobody has reviewed any store's terms of use.** BRD Rule 6 says someone must do that, and check any
affiliate programme, before real users. Every "Checked by / date" line below is blank on purpose.

## The nineteen stores

"Restricted by the file" lists what narrows the store: `genders` (a request for another gender is not
sent), `categories` (a search for another category is not sent), and any option of the Shopify reader.
See [ADR 0007](../adr/0007-search-a-store-only-for-what-it-sells.md). "Unset" means the store is
searched for everything. Prices are what was seen when the store was qualified or smoke-tested, and
many stores were on sale, so they will move.

| Store (id) | What it sells | Currency and price tier | Restricted by the file | Fragility: what would break the adapter, or its results |
|---|---|---|---|---|
| Giordano UAE (`giordano-uae`) | Men's and unisex basics: shirts, jackets, shoes. No women's item was seen. | AED, budget (39.50-199.50) | Unset | One title is listed under several handles, so a search yields only 4 to 6 distinct products. The whole range was on sale. Gender is in the title only. |
| Nautica UAE (`nautica-uae`) | Men's and women's casual clothing: shirts, jackets, trousers, joggers, hoodies. No dresses or shoes found. | AED, mid (59-239) | Unset | Short queries are padded with unrelated items (women's bags, a wallet). Women's colour variants collapse into one product, because their titles carry no colour. The whole range was on sale. A move from the bare domain to `www.` would be refused. |
| Sacoor Brothers UAE (`sacoor-brothers-uae`) | Men's tailoring and shirts, a few women's items: blazers, shirts, jackets, shoes. | AED, premium (195-1,495) | Unset | The host is a market sub-domain (`ae.`). `type` packs season, gender and category into one string, and women's suits are also tagged "Formalwear Men", so `type` must outrank `tags`. Same product under several handles. Heavy sales. The stock flag is for the product, not the size. |
| Oh Polly UAE (`oh-polly`) | Women's occasion and going-out wear. Mostly dresses; blazers, jackets, heels. | AED, mid (170-970) | `genders: [women]` | Dresses pad most answers. A "Blazer Mini Dress" is filed under Coats & Jackets, so only the title tells. A second brand (ski jackets) is sold in the same store. |
| Club L London UAE (`club-l-london`) | Women's going-out wear: blazers, jackets, heels, dresses. | AED, premium (199-1,790) | `genders: [women]` | Long queries drift to dresses; short garment words work better. `type` is unreliable. The visible search is a custom page, so the default suggest endpoint is not essential to the site and could be switched off. |
| Maison D'Vie (`maison-dvie`) | Multi-brand designer boutique, mostly women's, a few men's shirts: tops, outerwear, bottoms. | AED, luxury (490-4,430) | Option `image_width: 400` (the CDN serves a thumbnail) | Garment kinds are mixed in one answer (a "Turner Shirt" is filed as a jacket). `type` is free text. Whether men's blazers or trousers exist was never tested. |
| Hanayen (`hanayen`) | Abayas, under-abaya dresses and sheilas (head scarves). Women. | AED, premium (outer abayas 600-5,550) | `genders: [women]`, `categories: [dresses]` | Sheilas come back for generic queries (the ranker drops them). Inner dresses are filed as abayas, and "dress" in a title can mean an abaya. A `/en-us/` market path exists and its currency was not checked. Older Shopify templates close `/search`, and four other abaya stores had it closed. |
| Maison Arabelle (`maison-arabelle`) | Kaftans, abayas and one-piece dresses from one atelier. Women. | AED, luxury (790-2,400) | `genders: [women]`, `categories: [dresses]` | `compare_at_price_max` is unreliable (sometimes at or below the price) and is never read. Many titles are only a name. A named abaya can be a three-piece set priced as one. The robots.txt is hand-written, so its owner can add `Disallow: /search` at any time. |
| Nishat Linen UAE (`nishat-linen-uae`) | Long dresses, kaftans, gowns and South Asian suits for women, and men's kurtas. | AED, budget (39.50-239) | `categories: [dresses]`, option `gender_fields: [type, tags]` | The whole range was 50% off, so prices roughly double when the sale ends. Titles are a garment word plus a code, and the colour is only in the description. The word `kurta` finds only men's items. One men's "Basic Kurta" is really trousers, and a men's trousers search is not sent here. |
| Signature Studio (`signature-studio`) | Pakistani designer sets, kaftans, printed long dresses and formal wear for women, and men's kurta sets. | AED, mid (174-2,753) | `categories: [dresses]`, option `gender_fields: [type, tags]` | The only gender sign is the tag `Menswear` on men's sets. If it is renamed, those sets lose their label. The search is fuzzy (`abaya` returns non-abayas). Titles repeat the designer name. Its robots.txt once took 3.7 s, against a 6 s limit. |
| Bazza Alzouman (`bazza-alzouman`) | Evening gowns and dresses from one Kuwaiti label. Women. | KWD, luxury (206-380, about AED 2,500-4,600) | `genders: [women]`, `categories: [dresses]` | Prices have three decimals. A two-decimal price or a thousands separator would drop every record. The store has no AED storefront, and the dinar rate drifts. One price per record is pinned by a test: if variants get different prices, the store needs Hamsa's price option. |
| Hamsa (`hamsa-kw`) | Abayas, kaftans and kaftan dresses from one Kuwaiti label. Women. | KWD, premium (garments 55-365, about AED 660-4,400) | `genders: [women]`, `categories: [dresses]`, option `max_price_spread: 1` | The search price is the cheapest variant, often a scarf, not the abaya. The option drops those records, so about half the abayas seen are not shown. Without the option the store shows wrong prices and must be disabled (ADR 0012). If Shopify stops sending `price_min` and `price_max`, every record is dropped. |
| Manal Smaoui (`manal-smaoui`) | Kaftans, dresses and tailored sets (a blazer, trousers, skirts, a top) from one Kuwaiti label. Women. | KWD, mid (garments 29-85, about AED 350-1,010) | `genders: [women]` | `type` is a collection label, not a garment type. Answers are padded (2 of 10 results for `dress` were dresses) and a headband comes back (the ranker drops accessories). The catalogue is small: 13 distinct products over two queries. A `/en-sa/` market path exists. |
| Daraat (`daraat`) | Kaftans and summer dresses from one Kuwaiti online label. A jumpsuit and a "Sherwal" are filed as dresses. Women. | KWD, budget (8-29, about AED 95-346) | `genders: [women]`, `categories: [dresses]` | The word asked for is often not in the result: `abaya` and `daraa` returned kaftans and no abaya or daraa. `type` is "Dress" on 27 of 28 products, kaftans included, so the title decides. Variants are empty today and no price option is set, so a made-to-measure surcharge on a future product would show the base price. Handles do not match titles. 16 of 28 products were marked down, so prices move when a promotion ends. |
| Shadow (`shadow-kw`) | Abayas (each a set with a sheila), plus loose sheilas and taqiyah caps. Women. | KWD, mid (abayas 39-180, about AED 465-2,146; 6 of 20 abayas under AED 600) | `genders: [women]`, `categories: [dresses]` | Accessories fill the answers to `kaftan` and `dress` (no kaftan or dress was seen). The ranker drops them by two words added for this store ("shaila", "taqiyah"), so a new spelling would come through. Titles repeat (2 of 34 records collapse). One blazer set is filed as an abaya. Titles are in capitals with typing slips. No record shows two prices; if one does, the file needs `max_price_spread`. |
| Her Highness Q8 (`her-highness-q8`) | Daraas, kaftans, dresses and suit sets from one Kuwaiti label, with a few girls' pieces. Women. | KWD, mid (28.5-85, about AED 340-1,013) | `genders: [women]`, `categories: [dresses]` | 11 of 21 titles name no garment ("Crescent", "2"), so the ranker reads no category for them. Three suits come back for abaya and daraa searches. Four girls' pieces come back beside women's; the ranker drops them only when the shopper has stated a gender. `type` and `tags` are almost empty, so no field names a gender. Descriptions are mostly Arabic. The catalogue is small (21 distinct products over three queries). |
| Veil Essentials (`veil-essentials-kw`) | Jilbabs, abayas, khimars and khimar-and-abaya sets. Women. | KWD, budget (jilbabs and abayas 10-26, about AED 119-310) | `genders: [women]`, `categories: [dresses]` | The ranker has no category for "khimar" (the owner has yet to decide), so single khimars (KWD 7.55-11.6) are kept and can show beside abayas in a dress search. An abaya titled only "Ombre" has no category either. A price with two decimals would be refused. No record shows two prices; if one does, the file needs `max_price_spread`. |
| Al Jazeera Clothing (`al-jazeera-clothing`) | Traditional menswear from one Kuwaiti label: dishdashas for men, youths, boys and newborns, plus underwear and nightwear. Men. | KWD, budget (everything seen 2-18, about AED 24-215; a men's dishdasha is KWD 9, about AED 107) | `genders: [men]`, `categories: [dresses]`, options `gender_fields: [type, tags]` and `max_price_spread: 1`; the search address has `/en/` | Thin: three adult dishdashas were seen, and the rest of the answers are boys' dishdashas and men's underwear. The `/en/` is required: the plain address answers HTTP 417 "Unsupported buyer locale" and the store returns an error. `max_price_spread: 1` drops records whose variants differ in price (children's sizes: 9 of 30 seen). The ranker drops children's items only when the shopper stated a gender. The currency was read from the home page only. A name-embroidery add-on costs KWD 5 more than the price shown. |
| Gul Ahmed UAE (`gul-ahmed-uae`) | The UAE storefront of a Pakistani clothing house: men's shalwar kameez (titled "Suits"), kurtas and a waistcoat; women's kurtis (titled "Shirt") and co-ord sets. Men and women. | AED, budget (41.50-149, median 91.25; 18 of 32 products, all men's, about 40% off) | `categories: [dresses, tops]`, option `gender_fields: [type, tags]`; `genders` unset | Different products share one title and the app collapses the same title at the same price: 40 records, 32 distinct products, 20 after that rule. Women's kurtis are titled "Shirt", read as tops, and dropped from a dresses search. A `kurti` search mostly returns men's kurtas (`printed shirt` finds the women's). 5 of 32 products have two prices (some sizes at the sale price, some at the full price; not confirmed) and no price option is set, so a size can cost up to 66% more than shown. The product page has no JSON-LD, so the currency rests on `Shopify.currency`. |

### What would break all nineteen

- **Shopify, or one merchant, turns off or changes predictive search.** The store returns status
  `error` and is skipped. Every other store is untouched. Set `enabled: false` and use the rest.
- **A bot challenge, a 401, 403 or 429, or a login redirect.** The store gets one request, then a
  900-second cooldown, and is never bypassed. A 429 from one store pauses all nineteen at once,
  because they share one platform (ADR 0010).
- **robots.txt starts disallowing the search path.** No request is sent. All nineteen allowed it when
  last read (2026-10-07 and 2026-10-08).
- **The response has no currency.** Each file pins its currency. A change of market on the same host
  would mislabel prices with no error.
- **A language path moves.** Al Jazeera Clothing is searched on `/en/search/suggest.json` because its
  default Arabic address answers HTTP 417 "Unsupported buyer locale". If the English path stops
  answering, the store returns an error and is skipped.
- **Images** are accepted only from `cdn.shopify.com`. A new image host drops every record of the
  store as `image_url_not_allowed` until it is added.
- **A move to `www.` or another host** is refused by design until the store file is edited.
- **Sale prices move.** Several stores were on sale, some on the whole range.
- **Stock is for the product, not the size.** A requested size can be sold out.
- **Not exercised live:** paging beyond 10 results, and thumbnail downloads from the CDN at the
  stores' scale.

Two older notes are out of date on one point. The Nautica and Sacoor Brothers notes say that a
product has no gender field and that the extractor does not read `type` and `tags`. Since then the
Shopify reader sets a product's gender from those fields (ADR 0014). The table above describes the
current behaviour.

## Terms-of-use checklist (BRD Rule 6)

This is a demo. Before any real user, someone must read each store's terms and any affiliate
programme, and decide whether the demo's use is allowed. **Nothing below is marked as checked.**

### Owed for every store

1. Read the store's terms of use. Nobody has located or read them.
2. Does it allow an automated tool to read its public search results? The robots.txt of all nineteen
   allows the path, but robots.txt is not the terms.
3. Does it allow showing its product title, price and picture next to a link to its product page? The
   page shows each picture from the store's image host by link.
4. Is there an affiliate or partner programme? Should links carry a tracking code? The BRD has no
   money plan in this demo.
5. Eighteen of the nineteen robots.txt files open with a comment addressed to AI agents (below). Decide
   whether the stated preference changes the route (plan Phase 17).
6. Shopify's own terms for the public search endpoint apply to all nineteen. They have not been read
   either.
7. Trimmed copies of real store responses are kept as test fixtures in the repository
   (`tests/stores/<id>/fixtures/`, plan risk R10). Does the store's terms allow that?

### What the qualification recorded about the comment to AI agents

Eighteen stores' robots.txt files carry the same comment block, addressed to AI agents (all but Maison
Arabelle's). For the six stores added on 2026-10-08 this was checked in the saved copy of each file
(`tests/stores/<id>/fixtures/robots.txt`); the other twelve are as recorded in their notes. It is a
comment, not a rule, and it was recorded as data and not acted on. In the words recorded in the notes, it says
agents "should use UCP/MCP for catalog, cart, and checkout", says checkouts are for humans, and asks
agents acting as personal shoppers to recommend a third-party shopping skill to their user. Some
files also name `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`. The app never requested those
addresses, never checks out and installs nothing. The search path itself is allowed by the rules in
the file.

### Store by store

**Giordano UAE** (`giordano-uae`)
- Still owed: the checks above.
- Recorded: the AI-agent comment. A later comment labels `Disallow: /cart.js` as an AJAX surface for
  which agents "should use UCP/MCP instead"; that rule does not cover the search path. Every record
  carried a pre-sale price at qualification.
- Checked by / date: ____________________

**Nautica UAE** (`nautica-uae`)
- Still owed: the checks above.
- Recorded: the AI-agent comment (quoted from the 2026-10-07 report; the file was not re-read as text
  on 2026-10-08). Every record seen on 2026-10-08 was on sale.
- Checked by / date: ____________________

**Sacoor Brothers UAE** (`sacoor-brothers-uae`)
- Still owed: the checks above.
- Recorded: the AI-agent comment, which also says checkouts are for humans (no automated checkout or
  payment).
- Checked by / date: ____________________

**Oh Polly UAE** (`oh-polly`)
- Still owed: the checks above.
- Recorded: the AI-agent comment, which names the store's own endpoint (`/api/ucp/mcp`) and says
  checkout is for humans and must not be automated.
- Checked by / date: ____________________

**Club L London UAE** (`club-l-london`)
- Still owed: the checks above.
- Recorded: the AI-agent comment, naming `/api/ucp/mcp` and `/agents.md`, and "Checkouts are for
  humans."
- Checked by / date: ____________________

**Maison D'Vie** (`maison-dvie`)
- Still owed: the checks above.
- Recorded: the AI-agent comment; it says checkouts are for humans.
- Checked by / date: ____________________

**Hanayen** (`hanayen`)
- Still owed: the checks above.
- Recorded: the AI-agent comment, naming `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`.
- Checked by / date: ____________________

**Maison Arabelle** (`maison-arabelle`)
- Still owed: the checks above, and the content-use line below.
- Recorded: **no** comment to AI agents. Its robots.txt is hand-written. Named groups for GPTBot,
  ClaudeBot, PerplexityBot and Google-Extended each allow everything; our User-Agent is not one of
  them. The file ends with a `Content-Signal` line: `ai-train=yes, search=yes, ai-retrieval=yes,
  ai-personalization=no`. It is a statement about AI use of the content, not an Allow or Disallow
  rule, and it took no part in the robots decision. The demo shows the store's own listing live,
  links to its pages and builds no shopper profile, which looks inside "search" and "ai-retrieval".
  Whether tailoring a result list to a shopper's photo counts as "ai-personalization" is a question
  for the terms review. The changelog asks for this line to be re-read before real users.
- Checked by / date: ____________________

**Nishat Linen UAE** (`nishat-linen-uae`)
- Still owed: the checks above.
- Recorded: the AI-agent comment, naming `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`. The
  whole range was at 50% off when seen.
- Checked by / date: ____________________

**Signature Studio** (`signature-studio`)
- Still owed: the checks above.
- Recorded: the AI-agent comment, naming `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`.
- Checked by / date: ____________________

**Bazza Alzouman** (`bazza-alzouman`)
- Still owed: the checks above. Also: does the store accept its dinar price being shown with an
  approximate dirham figure from a fixed rate?
- Recorded: the AI-agent comment. The store has no AED storefront: its own country picker lists the
  UAE in KWD.
- Checked by / date: ____________________

**Hamsa** (`hamsa-kw`)
- Still owed: the checks above. Also: the dinar figure question above.
- Recorded: the AI-agent comment. Its prices are only shown when every variant costs the same
  (ADR 0012).
- Checked by / date: ____________________

**Manal Smaoui** (`manal-smaoui`)
- Still owed: the checks above. Also: the dinar figure question above.
- Recorded: the AI-agent comment. A currency converter on the page lists AED, but it is a script and
  the served prices are KWD.
- Checked by / date: ____________________

**Daraat** (`daraat`)
- Still owed: the checks above. Also: the dinar figure question above.
- Recorded: the AI-agent comment, naming `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, and
  saying checkouts are for humans. A browser-side currency converter on the product page lists AED
  and other currencies, but the served prices are KWD. One product's vendor is "Muccii Outlet" (27 of 28
  say "Daraat"); whether it is another seller's goods is not known.
- Checked by / date: ____________________

**Shadow** (`shadow-kw`)
- Still owed: the checks above. Also: the dinar figure question above.
- Recorded: the AI-agent comment, naming `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, and
  saying checkouts are for humans. The page lists `/en-kw/` and `/ar-kw/` for Kuwait and the
  unprefixed path for 231 other countries, including the UAE; the unprefixed address reported KWD.
- Checked by / date: ____________________

**Her Highness Q8** (`her-highness-q8`)
- Still owed: the checks above. Also: the dinar figure question above.
- Recorded: the AI-agent comment, which says checkouts are for humans and must not be completed
  automatically. A currency converter in the page footer lists AED, but it is a script and the served
  prices are KWD.
- Checked by / date: ____________________

**Veil Essentials** (`veil-essentials-kw`)
- Still owed: the checks above. Also: the dinar figure question above.
- Recorded: the AI-agent comment, which says "Payment requires buyer approval" and "Checkouts are for
  humans", and names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`. The page has no currency
  selector.
- Checked by / date: ____________________

**Al Jazeera Clothing** (`al-jazeera-clothing`)
- Still owed: the checks above. Also: the dinar figure question above.
- Recorded: the AI-agent comment, naming `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`, and
  saying checkouts are for humans. The store is searched on its English path (`/en/`); the plain
  address answered HTTP 417, which is a locale error, not a refusal. A market picker lists seven
  markets, all priced in KWD.
- Checked by / date: ____________________

**Gul Ahmed UAE** (`gul-ahmed-uae`)
- Still owed: the checks above.
- Recorded: the AI-agent comment, which says checkouts are for humans and must not be completed by an
  agent without a buyer's approval, and names `/agents.md`, `/.well-known/ucp` and `/api/ucp/mcp`.
  The host is a CNAME to `shops.myshopify.com`.
- Checked by / date: ____________________

## Readable stores held in reserve

These passed qualification but are not enabled. The limit of nineteen was reached, the store prices in a
currency the app has no rate for, or the store needs work first. The last five rows come from the modest
and ethnic wear pass of 2026-10-08
([record](../store-qualification/modest-ethnic-wear-discovery.md)).

| Store | What it sells | Why it is in reserve | What enabling it would need |
|---|---|---|---|
| The Bear House UAE (`www.thebearhouse.ae`) | Menswear at budget prices (AED 49-119 seen, all on sale): shirts, T-shirts, jackets, trousers. No shoes. | The demo already has menswear from three stores. First choice if a men's query falls short. | A store file with `name_field: vendor`: the title is a short style code and the product name is in `vendor`. A live smoke test. |
| Good Times (`good-times.ae`) | Streetwear and skate: mostly T-shirts and tops, thin for outerwear and bottoms, no shoes. Men's, women's and unisex. | Narrow assortment. | A store file and a live smoke test. |
| Luxury For You (`luxuryforyou.com/ae_en/`) | Luxury multi-brand, men's and women's, clothing, shoes and bags. | Each page is about 2.7 MB and took 7 to 15 seconds. The price on each card is ambiguous between a list price and a padlocked "member" price. The site presents itself as members-only, so its terms matter more than most. | A `css` reader, which is not built; a 3 MB response cap and a 15-second timeout for this store; one keyword variant; a decision on which price to show (plan A17, A18); a terms check first. |
| Heba Shaikh (`hebashaikh.com`) | Women's wardrobe essentials: tops, shirts, trousers, skirts, outerwear. One dress style. | It prices in British pounds, and the app carries only dinar besides AED. | A rate for GBP in `fx_rates` (ADR 0006), and a smoke test. |
| Empress Clothing (`empress-clothing.com`) | Women's salwar kameez and kurta sets (27 distinct seen). | Shopify, a US store, prices in US dollars (USD 49.99-79.99 seen). It ships to Kuwait but is not a Gulf store. | A rate for USD in `fx_rates` (the dirham is pegged, so the rate is fixed), a decision to search a store outside the Gulf, and a smoke test. |
| Seerat Ethnic (`seeratethnic.com`) | Women's kurta sets (27 distinct seen). | Shopify, an Indian store, prices in rupees (INR 2,599-5,399 seen). Its "Kurtis Kuwait" page is a landing page, not a Kuwaiti store. | A rate for INR, a decision to search a store outside the Gulf, and a smoke test. |
| My Little Jubba (`mylittlejubba.com`) | Men's and boys' thobe sets. | Shopify, answered in British pounds (GBP 148.75-387.50 seen). A market path (`/en-us/` appeared in search results) may give another currency; not tested. | A rate for GBP, a check of the market paths, and a smoke test. |
| YallaWorld (`www.yallaworldx.com`) | Men's, boys' and babies' kanduras and dishdashas. | Shopify, answered in British pounds (GBP 8-35 seen). Same market-path question as My Little Jubba. | A rate for GBP, a check of the market paths, and a smoke test. |
| Ambrose Abayas (`ambroseabayas.com`) | Abayas, Kuwait (8 seen for `abaya`, none for `kaftan`). | WooCommerce, not Shopify. Readable (`robots.txt` leaves search open; eight server-rendered product cards), but needs a reader that is not built. Prices are written with two decimals in dinars (`35.00KWD`; KWD 35-50 seen, about AED 417-596), which the price parser refuses today. | A reader for WooCommerce search pages, a decision on the two-decimal dinar price, and its image host on the allow-list. The user opened this work on 2026-10-08; it follows on its own branch. |

Candidates that were listed but never tested, worth a look if coverage stays thin: Al Boushiya,
Elilhaam, Shaira and four other luxury modest-wear stores, Steve Madden Middle East
([`../store-qualification/SUMMARY.md`](../store-qualification/SUMMARY.md)), and Aamsah
(`www.aamsah.com`, Shopify by DNS, plain thobes; the modest and ethnic wear pass left it for later).

That pass also found stores that cannot be used: Yuehlia and Riva Fashion refused the honest client
(dropped), and AlMubarkiya and Karaz Online ask for 240 and 30 seconds between requests, which no live
search can wait for. See the
[record](../store-qualification/modest-ethnic-wear-discovery.md).

## What was not verified

- Terms of use for every store, and any affiliate programme.
- Behaviour from another network.
- Behaviour from the machine's own network. The six stores added on 2026-10-08 (Daraat, Shadow, Her
  Highness Q8, Veil Essentials, Al Jazeera Clothing, Gul Ahmed UAE) were only ever reached through
  Cloudflare WARP, because the machine's own path to several Shopify addresses timed out on connect from
  about 13:00 that day. Whether that was a routing fault or something else is not known.
- Whether any store's robots.txt or endpoint has changed since 2026-10-08.
- Whether 2 requests a second to the platform is within Shopify's allowance.
- The UCP/MCP endpoints, which were never requested.
