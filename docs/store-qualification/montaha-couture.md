# Montaha Couture qualification (2026-10-08)

**Verdict:** DROP for now (undetermined). The shop's TLS certificate does not verify for either `montahacouture.com` or `www.montahacouture.com`, so not even `robots.txt` could be read, and the project's rule is to check `robots.txt` first and to use certificate verification always. Nothing was bypassed. The site is probably a WooCommerce store priced in US dollars (from search-engine snippets, not from our requests), so even if the certificate were fixed it would be a "needs a new adapter" case, not a Shopify one. Re-test from another network, or after the owner renews the certificate.

## Storefront

- Store: Montaha Couture, `https://montahacouture.com/`, the online shop of the Kuwaiti designer Montaha Al Ajeel (Muntaha Al-Ajeel in some spellings): evening and cocktail dresses, kaftans and abayas, made in Kuwait.
- **How it is known to be the brand's own shop.** Web search returned pages on this domain titled "Montaha Couture", with product pages (`/product/blissey/`, `/product/abaya-1/`, `/product/dress-139-2/`, `/shop-list/`) and a news item about the designer ("Meet the First Kuwaiti designer to show at Paris Fashion Week"). This is the weakest evidence of the four stores found: no third-party article seen in the search links to this domain, and the domain was not cross-checked against the designer's social media (not reachable by an honest client). Treat the identification as probable, not confirmed.
- Platform (not contacted, so Level B only): the URL shapes `/product/{slug}/`, `/product-category/{category}/`, `/shop-list/` and `?add-to-cart={id}` are WooCommerce (WordPress) shapes, not Shopify's. Prices shown in search-engine snippets were in US dollars (dresses USD 720 to 1,045, kaftans USD 620 to 915, an abaya USD 1,140). These are the search engine's text, not an observation by this client.
- Sibling domains: none tested.

## robots.txt

Not read. Both attempts failed during the TLS handshake (below), before any HTTP exchange.

## Reachability

| # | URL | Result | Notes |
|---|---|---|---|
| 1 | `https://montahacouture.com/robots.txt` | ConnectError: `[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'montahacouture.com'` | no HTTP response; the handshake was rejected by the client's certificate check |
| 2 | `https://www.montahacouture.com/robots.txt` | ConnectError: the same error for `'www.montahacouture.com'` | one try of the `www` name, in case the certificate covered only that name; it does not |

I did not turn certificate verification off, retry, or look for another route: a certificate that does not match the host name is exactly the situation in which a client must not carry on. The other 5 hosts contacted in this pass all completed the handshake from the same machine and network, so the fault is on the shop's side (or on a path specific to this host), not in the local setup. The cause was not investigated further (no third request, no raw TLS probe).

## Search URL template, data path, extraction strategy, fields, hosts, price formats

Not established. For a future attempt: a WooCommerce shop usually answers `https://montahacouture.com/?s={query}&post_type=product` with an HTML results page; this URL was not requested, so it is a hypothesis, and `robots.txt` would have to allow it. The project has no HTML adapter yet; one would need a CSS or JSON-LD reader for WooCommerce product cards (title, price with currency symbol, image, link).

## Currency / tier hint

Search-engine snippets suggest **USD**, tier **luxury** (about USD 620 to 1,140, roughly AED 2,300 to 4,200 at the fixed AED 3.6725 per USD peg; computed from snippets, not observed). Not confirmed by any request.

## Requests made

2 (both failed in the TLS handshake). No HTTP response was received from this store.

## Sample

None (no data was fetched).

## Risks and fragility

- Invalid or mismatched certificate on both names; unknown whether temporary.
- Probably WooCommerce, so a different adapter from the six Shopify stores, and probably USD, a currency no enabled store uses.
- `?add-to-cart=` links appear in search-engine results for this domain. Such URLs change a cart and must never be requested.
- Identification as the brand's own shop is not cross-checked.
- Not tested: robots.txt, any search page, any product page, terms of use.
