"""Which storefront platform a store runs on, for the limit that every store of one platform shares.

Several of our stores are tenants of one hosted platform (all nineteen shipped stores are Shopify
storefronts). Each store has its own address, and we keep to about one request a second to each of
them (BRD Rule 2), but the platform in front of them does not count per shop: on 2026-10-08 thirteen
different shops answered HTTP 429 within 11 milliseconds of each other. The limit is per client
across the whole platform, so the politeness has to be too: the stores of one platform share one
queue (``Settings.rps_per_platform``) and one cooldown.

The platform is read from what the store file already says, its extraction strategy: ``shopify``
means a Shopify storefront. ``StoreConfig`` does not change. A store that uses no strategy named
here is its own platform.
"""

from vga.models import StoreConfig

KNOWN_PLATFORMS = frozenset({"shopify"})
"""Extraction strategy names that also name the platform the store runs on. A strategy is added
here only when the platform it reads is shared by many shops (``json_ld`` or ``css`` read any
site, so they say nothing about the platform)."""


def platform_of(store: StoreConfig) -> str:
    """The name of the queue and cooldown ``store`` belongs to.

    ``platform:shopify`` for every Shopify storefront; ``own:<store id>`` for a store on no known
    platform, which therefore shares its queue with nobody. The two prefixes cannot clash with a
    store id (they contain a colon) or with the ``host:<name>`` key of an image host.
    """
    for strategy in store.extraction.strategies:
        if strategy.name in KNOWN_PLATFORMS:
            return f"platform:{strategy.name}"
    return f"own:{store.id}"
