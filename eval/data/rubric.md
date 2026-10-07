# Labelling rubric: "good match", the top 10 and "working link"

Frozen with `queries.yaml` before any tuning. Do not change it after seeing results. If a real
flaw turns up, write down what you changed and why in the results file and re-label all queries.

Amended once, on 2026-10-08 and before any acceptance run (plan assumption A23, dresses became a
fifth category): the category row no longer calls "a dress" a miss for every request, and the
section "Dresses and ethnic wear" with worked examples 4 to 6 was added. Nothing else changed.

## The pass rule (quoted verbatim from `docs/02-prd.md`, "Acceptance test (10 queries)")

> **Pass:** for most of the 10 queries: ≥ 20 results, from ≥ 3 stores, ≤ 30 s, all links open the right product page, and a person marks ≥ 7 of the top 10 as good matches (same category, close colour/style), and each price range is within 1 result of its target count (or flagged "few options"). Record the results in a short table, plus every failure.

"Most" means at least 7 of the 10 queries (plan assumption A6). A query passes only if every
condition holds for it. This file defines the two human parts: good matches and working links.

## A good match

Judge the product against what the shopper asked for: the photo, the words, or both. For a photo
plus text, the photo gives the look and the text overrides it ("dark brown" beats the photo's
colour). Check three things.

| Check | Match | Near miss | Miss |
|---|---|---|---|
| **Category** (garment type) | Same type. A kind of the named type counts: any jacket for "jacket"; sneakers for sneakers | not used | Different type: hoodie for blazer, boots for sneakers, a dress for a blazer, a shirt for a gown, a bag, a sheila |
| **Colour** | The colour asked for or an everyday shade of it (jet black, chocolate for dark brown) | Neighbouring shade (charcoal for black, mid brown for dark brown) | Different colour family (navy for black, light tan for dark brown) |
| **Style / fit** | Has the headline words asked for (oversized, high-waisted, wide-leg, cotton) or, for a photo, the same silhouette | One headline word is close (relaxed for oversized), or the listing is silent | The opposite (slim for oversized) or another silhouette (cropped for long) |

**Good = category Match, no Miss anywhere, and at most one Near miss.** Anything else is Not good.
If the request states a gender, the product must be for that gender or unisex. Price is not part
of the label (it is scored under "price ranges ok"). Label with `1` (good) or `0` (not good); no
half marks and no blanks.

### Worked examples (request q06: "black oversized blazer for men under 400 AED")

1. **Clear good.** "Men's Oversized Wool-Blend Blazer, Black", 349 AED. Category, colour and
   style all match. Label `1`.
2. **Clear bad.** "Men's Black Oversized Hoodie". Colour and fit match, but a hoodie is not a
   blazer, so category is a Miss. A right colour never rescues a wrong category. Label `0`.
3. **Borderline.** "Men's Charcoal Relaxed-Fit Blazer". Category matches. Charcoal is a Near miss
   for black and "relaxed" is a Near miss for "oversized". Two Near misses, so label `0`. The
   same blazer in black would have only one Near miss and gets `1`.

### Dresses and ethnic wear (the fifth category, added 2026-10-08)

Dresses, gowns, kaftans, abayas, jalabiyas, kurtas and similar one-piece or ethnic garments are one
category. So any of them is a **Category Match** for a request in that category, and the kind is
then judged under **Style / fit**: for a gown, a long evening dress has the same silhouette, a
short dress is another silhouette (Miss), and a kaftan is a Near miss; for an abaya, another abaya
is the match, a kaftan-style abaya is a Near miss, and a short or fitted dress is a Miss.
Jumpsuits and swimwear are not in this category (a jumpsuit for a dress request is a Category
Miss). Accessories sold next to abayas, such as a sheila or a hijab, are never a match for any
garment. Dresses, gowns and kurtas are judged the same way for the **Colour** and **gender** rules
above.

Worked examples (request q01: a burgundy evening gown, photo only):

4. **Clear good.** "Evening Gown in Burgundy Velvet". Category, colour and silhouette all match.
   Label `1`.
5. **Clear bad.** "Burgundy Satin Shirt". A shirt is not a dress, so category is a Miss. Label `0`.
6. **Borderline.** "Wine Embroidered Kaftan". Category matches; wine is an everyday shade of
   burgundy; a kaftan is a Near miss on silhouette. One Near miss, so label `1`. The same kaftan
   in navy has a colour Miss as well as the Near miss, so label `0`.

## How to label the top 10

1. Use the labelling sheet the harness exports (`query_id, photo, group, rank, title, price, store, price_range, url, label`; `photo` is the file to open for that query, `group` is the garment for an outfit). Fill
   only `label`.
2. "Top 10" means ranks 1 to 10 of the result list, ordered by the app's overall match order across
   all price ranges together (not by price). Label exactly those ten rows.
3. Outfit photos have one list per garment. Label the top 10 of each list separately. The query
   passes "good@10" only if **every** garment list reaches 7. Record each garment's count.
4. If a list has fewer than 10 results, label what is there; the missing places count as `0`.
5. Open each product link and label from the product's own image and title. Do not use the app's
   reason sentence or score.
6. Label once. Do not change a label after seeing the totals.

## A working link

A result's link works only if all of these are true. One failing link fails "links ok" for that
query, because the PRD says all links.

1. It opens: HTTP 200 after at most 3 redirects, within 6 s, with no login wall, CAPTCHA, error or
   "not found" page.
2. The final address is `https` on the store's own site (a host on that store's `allowed_hosts`).
3. It is the product's own page, not the store's home page, a search page or a category listing.
4. The page shows the same product as the result card (same title and same item in the image). A
   sold-out product still counts if its page opens. A price that differs from the card is not a
   link failure; record it in the failures table with cause "store".

The harness checks 1 to 3 for every result (`--links all`, polite: robots.txt and about 1 request
per second per store). A person opens the top 10 of each query by hand to confirm point 4.
