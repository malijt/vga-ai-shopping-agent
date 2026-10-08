# Modest and ethnic wear discovery: Kuwait first (Module 2.7, 2026-10-08)

Why this exists: the user asked for more stores, because the thirteen enabled ones do not cover what
the demo should find: **abayas, kaftans, burqas and kurtis for women; thobes, kurtas and shalwar
kameez for men.** The user asked for stores in Kuwait first. This file is the overview of that pass:
every candidate, what was sent to it, and the verdict. Each store that qualified has its own report
next to this file.

## Result in one paragraph

Nineteen candidates were listed from web search. Sixteen were contacted with the honest client, 86
requests in all. **Six qualify and need no code** (Shopify `/search/suggest.json`, `robots.txt`
leaves search open, a currency the app already carries): five in Kuwait, priced in dinar (Daraat,
Shadow, Her Highness Q8, Veil Essentials, Al Jazeera Clothing), and Gul Ahmed UAE, priced in dirham.
**One more is readable but needs a new reader** (Ambrose Abayas, WooCommerce). Four are readable
Shopify stores outside the Gulf that price in dollars, rupees or pounds (reserve only). Two refused
the honest client and are dropped. Three could not be judged. Together the six fill most of the
gaps: kaftans and abayas at budget prices (the first abaya below AED 600), a Kuwaiti abaya label,
men's shalwar kameez and kurtas, women's kurtis, and men's dishdashas. Two gaps stay open: adult
men's thobes are thin (three seen at one store), and no Kuwaiti store was found that sells men's
shalwar kameez.

## Method and limits

- **Finding the shops.** `WebSearch` only. Search summaries were treated as hints. `WebFetch` and a
  browser were never used on a store's own site.
- **Shopify or not.** Before any request, each host name was looked up in DNS (a question to the
  resolver, not to the store). An address in `23.227.38.0/24`, or a CNAME to `shops.myshopify.com`,
  is Shopify. The first request then confirmed it.
- **Requests.** `scripts/qualify_store.py` and nothing else: User-Agent
  `vga-shopping-agent-demo/0.1 (store-qualification research)`, `robots.txt` first and judged with
  protego on the full URL, https only, no cookies, no retries, at least 1 s apart, a stop at the
  first 403, 429 or challenge. One store at a time, with a pause between Shopify stores. No UCP/MCP,
  agent, cart, checkout, account or `/api/` address was requested. The comment addressed to AI agents
  that opens each Shopify `robots.txt` was recorded as data and not acted on.
- **The network, and a decision by the user.** From about 13:00 the machine's own network could not
  open a connection to several of Shopify's addresses (see `CHANGELOG.md`). No refusal was ever
  received: a connect time-out, not a 403 or a 429, which this project classes as "unreachable", not
  "blocked" (`docs/how-to-add-a-store.md`, 1.1 rule 5). At about 14:02 one request to Daraat's
  `robots.txt` timed out the same way. **The user then enabled Cloudflare WARP on the machine and
  told the orchestrator to try again.** WARP was confirmed on at about 14:06, and every Shopify
  request in this file after that (14:07 to 14:14) went through it. The User-Agent and every rule
  above were unchanged, and no Shopify store answered with a refusal. Why this was judged to be
  inside Rule 2: Shopify's edge answers a client it does not want with an HTTP 429 or 403 (it did so
  earlier in the day), not with a silent connect time-out; the app had sent it about twenty
  searches, not a flood; and a Cloudflare Community thread that week reports the same time-outs
  from Pakistani providers to other Cloudflare-served addresses. **What is not known:** whether the
  time-outs were a routing fault or Shopify dropping this network's address. If it was the second,
  using another network path is a departure from "dropped, never bypassed". It is recorded as a
  deliberate decision in the plan (section 12.3), not left silent.
- **The six non-Shopify stores** were contacted between 14:03 and 14:05, while WARP was being
  switched on. Which network carried each of those requests is not known.
- **Limits.** One machine, one day, about twelve minutes of requests. Prices are what the answers
  showed; sales are transient. AED figures for dinar prices use the project's fixed rate
  (1 KWD = 11.92 AED, `config/settings.yaml`). Terms of use were not read for any store.
  "Not seen" means "not in these answers".

## Overview

| # | Store | Country, currency | Platform | Verdict | What was seen | Price seen | Requests | Report |
|---|---|---|---|---|---|---|---|---|
| 1 | **Daraat** (`www.daraat.com`) | KW, KWD | Shopify | **GO** | Kaftans (cotton, velvet), summer dresses. `abaya` returned kaftans | KWD 8 to 29 (about AED 95 to 346) | 9 | [daraat.md](daraat.md) |
| 2 | **Shadow** (`shadow.com.kw`) | KW, KWD | Shopify | **GO** | Abayas; also sheilas and caps (accessories) | abayas KWD 39 to 180 (about AED 465 to 2,146) | 8 | [shadow-kw.md](shadow-kw.md) |
| 3 | **Her Highness Q8** (`herhighnessq8.com`) | KW, KWD | Shopify | **GO** | Daraas, kaftans, dresses, sets; a few children's | KWD 28.5 to 85 (about AED 340 to 1,013) | 6 | [her-highness-q8.md](her-highness-q8.md) |
| 4 | **Veil Essentials** (`veilessentialskw.com`) | KW, KWD | Shopify | **GO** | Jilbabs, abayas, khimars | abayas KWD 11.9 to 26 (about AED 142 to 310) | 6 | [veil-essentials-kw.md](veil-essentials-kw.md) |
| 5 | **Al Jazeera Clothing** (`aljazeera-clothing.com`) | KW, KWD | Shopify | **GO**, thin | Dishdashas, mostly boys'; three men's. Search works only on the `/en/` path | men's dishdasha KWD 9 (about AED 107) | 12 | [al-jazeera-clothing.md](al-jazeera-clothing.md) |
| 6 | **Gul Ahmed UAE** (`uae.gulahmedshop.com`) | AE, AED | Shopify | **GO** | Men's shalwar kameez suits and kurtas, women's kurtis | AED 41.50 to 149 | 8 | [gul-ahmed-uae.md](gul-ahmed-uae.md) |
| 7 | **Ambrose Abayas** (`ambroseabayas.com`) | KW, KWD | WooCommerce | **Readable, needs a new reader** | 8 abayas for `abaya`; none for `kaftan` | KWD 35 to 50 (about AED 417 to 596) | 3 | below |
| 8 | Empress Clothing (`empress-clothing.com`) | US, USD | Shopify | Readable, reserve | Women's salwar kameez and kurta sets | USD 49.99 to 79.99 | 6 | below |
| 9 | Seerat Ethnic (`seeratethnic.com`) | IN, INR | Shopify | Readable, reserve | Women's kurta sets | INR 2,599 to 5,399 | 6 | below |
| 10 | My Little Jubba (`mylittlejubba.com`) | GB, GBP | Shopify | Readable, reserve | Men's and boys' thobe sets | GBP 148.75 to 387.50 | 6 | below |
| 11 | YallaWorld (`www.yallaworldx.com`) | GB, GBP | Shopify | Readable, reserve | Men's, boys' and babies' kanduras and dishdashas | GBP 8 to 35 | 6 | below |
| 12 | Yuehlia (`yuehlia.com`) | KW | WooCommerce by URL shape | **DROP (blocked)** | HTTP 403 on `robots.txt` | n/a | 1 | below |
| 13 | Riva Fashion (`www.rivafashion.com/en-kw`) | KW | Magento by URL shape | **DROP (blocked)** | `robots.txt` allowed the search page; the page answered HTTP 403 | n/a | 2 | below |
| 14 | AlMubarkiya (`almubarkiya.com`) | KW | WooCommerce by URL shape | **Not usable live** | `robots.txt` asks for 240 s between requests; the search page timed out | n/a | 2 | below |
| 15 | Karaz Online (`www.karazonline.com`) | KW | custom | **Not usable live** | `robots.txt` asks for 30 s between requests; a general department store | n/a | 2 | below |
| 16 | Sara Arabia (`saraarabia.com`) | Gulf | unknown | Undetermined | The guessed search address is a 404; the real one is not known | n/a | 3 | below |
| 17 | Boksha (`www.boksha.com`) | KW | custom marketplace | Not contacted | Search address unknown | n/a | 0 | |
| 18 | Dishdashah (`www.dishdashah.com`) | KW | custom app | Not contacted | A made-to-measure tailoring service, not a product search | n/a | 0 | |
| 19 | Aamsah (`www.aamsah.com`) | unknown | Shopify by DNS | Not contacted | Plain thobes; left for a later pass | n/a | 0 | |

Namshi, Centrepoint and Ounass came up in the searches with Kuwait pages. All three were dropped on
2026-10-07 (search disallowed, or a bot challenge) and were not contacted again.

## The stores that did not get a report of their own

**Ambrose Abayas** (3 requests). `robots.txt` (200, 323 bytes) disallows only WooCommerce's upload
folders, `add-to-cart` links and `/wp-admin/`. `/?s=abaya&post_type=product` answered 200 (510,526
bytes, 1.3 s) with eight server-rendered product cards (`div.product`, WoodMart theme): name, price,
link and picture on the store's own host, and `instock` in the card's class. `kaftan` answered 200
with no cards. Prices are written `35.00KWD`: **two decimals for a dinar price**, which the price
parser refuses today (it accepts three for KWD). Titles are names only ("Thunder", "Samra",
"RimalAl-Fidda"). The qualification script reported "no product data" because its card detection
does not know this theme; the cards were found by reading the saved page offline. Needs: a reader
for WooCommerce search pages, a decision on the two-decimal dinar price, and the image host on the
allow-list. This is the work the user opened on 2026-10-08 (below).

**Empress Clothing** (6). Shopify, `Shopify.country = "US"`, prices in US dollars. 27 distinct
women's salwar kameez and kurta sets. Not a Gulf store: it ships to Kuwait. Would need a dollar rate
(the dirham is pegged, so the rate is fixed) and a decision to search a store outside the Gulf.

**Seerat Ethnic** (6). Shopify, India, prices in rupees (`priceCurrency: INR`). 27 distinct women's
kurta sets. Its "Kurtis Kuwait" page is a landing page, not a Kuwaiti store.

**My Little Jubba** (6) and **YallaWorld** (6). Shopify. Both answered in pounds with
`Shopify.country = "GB"`. Men's thobe and kandura sets, many for boys and babies. Both sell garments
made in the UAE, but neither answered in a Gulf currency on the address tested. A market path
(`/en-us/` appeared in search results) may give another currency; not tested.

**Yuehlia** (1). HTTP 403 with a 5,517-byte page on `robots.txt`. A refusal is final: dropped.

**Riva Fashion** (2). `robots.txt` (200, 3,259 bytes) left `/en-kw/catalogsearch/result/` open and
states content signals `search=yes, ai-train=no`. The search page answered HTTP 403. Dropped.

**AlMubarkiya** (2). `robots.txt` (200, 101 bytes) has an empty `Disallow:` and, after blank lines,
`Crawl-delay: 240`. Protego did not attach the delay to the group, so the script waited 1 s and then
asked for the search page, which timed out while reading. A store that asks for four minutes
between requests cannot serve a live search, and the request sent after 1 s should not have been
sent that soon. Not pursued; not contacted again.

**Karaz Online** (2). `robots.txt` is `User-agent: *` and `Crawl-delay: 30`; the script honoured it.
The guessed search parameter was ignored and the page listed general merchandise (the real form
field is `word`, read from the saved page). A general department store that asks for 30 s between
requests: not usable for a live search inside a 30 s deadline. Not pursued.

**Sara Arabia** (3). `robots.txt` allows everything. `/search?q=abaya` and `/search?q=jalabiya` are
404 pages that reveal nothing about the real search address. The earlier pass named this store as
the lead for everyday abayas; it stays undetermined. Veil Essentials now fills that gap.

## What the six add, against what the user asked for

| Asked for | Before this pass | After the six |
|---|---|---|
| Abayas (women) | Hanayen, Maison Arabelle, Hamsa: nothing below about AED 600 | + Shadow (about AED 465 to 2,146) and Veil Essentials (about AED 142 to 310) |
| Kaftans (women) | Maison Arabelle, Hamsa, Manal Smaoui, Signature Studio, Nishat Linen UAE | + Daraat (about AED 200 to 346) and Her Highness Q8 (about AED 435 to 500) |
| Burqas (women) | none | Veil Essentials' jilbabs and khimars are the nearest. See the open question below |
| Kurtis (women) | none found by that word | + Gul Ahmed UAE (titled "Shirt", tagged `Kurti`, AED 79 to 149) |
| Thobes (men) | none | + Al Jazeera Clothing: three men's dishdashas seen, at KWD 9. Thin |
| Kurtas (men) | Nishat Linen UAE, Signature Studio | + Gul Ahmed UAE (AED 41.50 to 101.50) |
| Shalwar kameez (men) | none | + Gul Ahmed UAE (titled "Suits", AED 83.50 to 113.50) |

## Decisions (user, 2026-10-08)

1. **The store limit rises above 13.** It becomes 19 with the six stores here, each enabled only
   after its live smoke test passes (plan assumption A30).
2. **Qualify the Shopify candidates one at a time.** Done, as above.
3. **Non-Shopify stores are opened** for dishdasha and budget-abaya sources. Of those tested, only
   Ambrose Abayas is readable and usable; a reader for it is the next piece of work, on its own
   branch.

## Open questions for the user

- **What "burqa" should match.** In Gulf shops a niqab or khimar is a head or face covering, and the
  ranker drops `niqab` as an accessory. In South Asian use a burqa is the whole outer garment. The
  word lists now treat `burqa` as a garment like an abaya; khimars are left undecided.
- **Stores outside the Gulf.** Four readable stores sell exactly the asked-for garments but are
  American, Indian or British and price in other currencies. Adding one needs a rate and a decision
  to search outside the Gulf.
- **Men's thobes.** Still thin. YallaWorld and My Little Jubba are the readable sources, both in
  pounds.

## Not verified

Terms of use for every store. Behaviour from the machine's own network, and whether its time-outs to
Shopify were a routing fault. Which network carried the six non-Shopify stores' requests. A product
page for Al Jazeera Clothing (its currency was read from the home page). Market paths and other
currencies at My Little Jubba and YallaWorld. Paging and `limit` above 10. Whether Ambrose Abayas
has more than the eight abayas one search showed.
