"""Store registry (plan 6.3.1): ``config/stores/*.yaml`` into ``StoreConfig`` (temporary files)."""

from pathlib import Path

import pytest
import yaml

from tests.factories import make_settings
from vga.errors import ConfigError
from vga.settings import DEFAULT_STORES_DIR
from vga.stores.extractors import ExtractorRegistry, ShopifyExtractor
from vga.stores.registry import StoreRegistry, load_store_configs

OH_POLLY = {
    "id": "oh-polly",
    "name": "Oh Polly",
    "country": "AE",
    "currency": "AED",
    "search_url_template": (
        "https://ohpolly.ae/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    ),
    "allowed_hosts": ["ohpolly.ae", "www.ohpolly.ae", "cdn.shopify.com"],
    "extraction": {"strategies": [{"name": "shopify"}]},
    "tier_hint": "mid_range",
    "enabled": True,
}

CLUB_L = {
    **OH_POLLY,
    "id": "club-l-london",
    "name": "Club L London",
    "search_url_template": (
        "https://www.clubllondon.ae/search/suggest.json?q={query}"
        "&resources[type]=product&resources[limit]=10"
    ),
    "allowed_hosts": ["www.clubllondon.ae", "cdn.shopify.com"],
    "tier_hint": "premium",
}


def write(folder: Path, name: str, data: object) -> Path:
    path = folder / name
    path.write_text(data if isinstance(data, str) else yaml.safe_dump(data), encoding="utf-8")
    return path


def test_a_missing_directory_gives_no_stores(tmp_path: Path) -> None:
    assert load_store_configs(tmp_path / "does-not-exist") == []


def test_an_empty_directory_gives_no_stores(tmp_path: Path) -> None:
    assert load_store_configs(tmp_path) == []
    assert StoreRegistry.from_directory(tmp_path).stores == []


def test_the_shipped_store_directory_loads_whatever_it_holds() -> None:
    """The directory is empty until the store-adapter phase; it must load either way."""
    stores = StoreRegistry.from_directory(DEFAULT_STORES_DIR).stores

    assert all(store.id for store in stores)


def test_valid_files_load_in_file_name_order(tmp_path: Path) -> None:
    write(tmp_path, "oh-polly.yaml", OH_POLLY)
    write(tmp_path, "club-l-london.yaml", CLUB_L)
    (tmp_path / "notes.txt").write_text("not a store", encoding="utf-8")

    stores = load_store_configs(tmp_path)

    assert [store.id for store in stores] == ["club-l-london", "oh-polly"]
    assert stores[1].currency == "AED"
    assert stores[1].extraction.strategies[0].name == "shopify"


def test_a_store_file_without_enabled_true_is_disabled_by_default(tmp_path: Path) -> None:
    write(tmp_path, "oh-polly.yaml", {k: v for k, v in OH_POLLY.items() if k != "enabled"})

    [store] = load_store_configs(tmp_path)

    assert store.enabled is False


# --------------------------------------------------------------------------------------------
# Invalid files name the file and the field
# --------------------------------------------------------------------------------------------


def load_error(folder: Path) -> ConfigError:
    with pytest.raises(ConfigError) as excinfo:
        load_store_configs(folder)
    return excinfo.value


def test_an_invalid_field_is_reported_with_the_file_and_the_field(tmp_path: Path) -> None:
    write(tmp_path, "oh-polly.yaml", {**OH_POLLY, "currency": "dirham"})

    error = load_error(tmp_path)

    assert "oh-polly.yaml" in str(error)
    assert "currency" in str(error)
    assert "oh-polly.yaml: currency" in (error.detail or "")


def test_a_template_without_the_query_placeholder_is_reported(tmp_path: Path) -> None:
    write(tmp_path, "oh-polly.yaml", {**OH_POLLY, "search_url_template": "https://ohpolly.ae/s"})

    error = load_error(tmp_path)

    assert "oh-polly.yaml" in str(error)
    assert "{query}" in str(error)


def test_a_host_that_is_not_listed_for_the_template_is_reported(tmp_path: Path) -> None:
    write(tmp_path, "oh-polly.yaml", {**OH_POLLY, "allowed_hosts": ["cdn.shopify.com"]})

    assert "allowed_hosts" in str(load_error(tmp_path))


def test_an_unknown_field_is_reported(tmp_path: Path) -> None:
    write(tmp_path, "oh-polly.yaml", {**OH_POLLY, "rps_limit": 2})

    error = load_error(tmp_path)

    assert "oh-polly.yaml: rps_limit" in (error.detail or "")


def test_a_missing_field_is_reported(tmp_path: Path) -> None:
    broken = {k: v for k, v in OH_POLLY.items() if k != "extraction"}
    write(tmp_path, "oh-polly.yaml", broken)

    assert "oh-polly.yaml: extraction" in (load_error(tmp_path).detail or "")


def test_a_file_whose_name_does_not_match_its_id_is_reported(tmp_path: Path) -> None:
    write(tmp_path, "ohpolly.yaml", OH_POLLY)

    assert "must be named oh-polly.yaml" in (load_error(tmp_path).detail or "")


@pytest.mark.parametrize("content", ["", "- just\n- a list\n", "plain text", "id: [unclosed"])
def test_a_file_that_is_not_a_mapping_of_settings_is_reported(tmp_path: Path, content: str) -> None:
    write(tmp_path, "oh-polly.yaml", content)

    assert "oh-polly.yaml" in str(load_error(tmp_path))


def test_an_unknown_extraction_strategy_is_reported_with_the_built_ones(tmp_path: Path) -> None:
    write(
        tmp_path,
        "oh-polly.yaml",
        {**OH_POLLY, "extraction": {"strategies": [{"name": "store_json", "fields": {}}]}},
    )

    detail = load_error(tmp_path).detail or ""

    assert "oh-polly.yaml: extraction.strategies.0 (store_json)" in detail
    assert "unknown extraction strategy" in detail
    assert "['shopify']" in detail


def test_bad_strategy_options_are_reported_with_the_option_named(tmp_path: Path) -> None:
    write(
        tmp_path,
        "oh-polly.yaml",
        {
            **OH_POLLY,
            "extraction": {"strategies": [{"name": "shopify", "options": {"name_field": "sku"}}]},
        },
    )

    assert "name_field" in (load_error(tmp_path).detail or "")


def test_every_problem_in_every_file_is_reported_together(tmp_path: Path) -> None:
    write(tmp_path, "oh-polly.yaml", {**OH_POLLY, "currency": "dirham"})
    write(tmp_path, "club-l-london.yaml", {**CLUB_L, "country": "UAE"})
    write(tmp_path, "good.yaml", {**OH_POLLY, "id": "good", "name": "Good"})

    detail = load_error(tmp_path).detail or ""

    assert "oh-polly.yaml: currency" in detail
    assert "club-l-london.yaml: country" in detail
    assert "good.yaml" not in detail


def test_two_enabled_stores_may_not_share_a_display_name(tmp_path: Path) -> None:
    write(tmp_path, "oh-polly.yaml", OH_POLLY)
    write(tmp_path, "club-l-london.yaml", {**CLUB_L, "name": "Oh Polly"})

    detail = load_error(tmp_path).detail or ""

    assert "oh-polly.yaml" in detail
    assert "'Oh Polly' is already used" in detail


def test_a_disabled_store_may_share_a_display_name(tmp_path: Path) -> None:
    write(tmp_path, "oh-polly.yaml", OH_POLLY)
    write(tmp_path, "club-l-london.yaml", {**CLUB_L, "name": "Oh Polly", "enabled": False})

    assert len(load_store_configs(tmp_path)) == 2


def test_the_user_message_is_plain_language_and_the_cause_is_in_the_detail(
    tmp_path: Path,
) -> None:
    write(tmp_path, "oh-polly.yaml", {**OH_POLLY, "currency": "dirham"})

    error = load_error(tmp_path)

    assert error.code == "config"
    assert "config/stores" in error.user_message
    assert "Traceback" not in error.user_message


def test_strategies_are_checked_against_the_given_registry(tmp_path: Path) -> None:
    write(
        tmp_path,
        "oh-polly.yaml",
        {**OH_POLLY, "extraction": {"strategies": [{"name": "shopify"}]}},
    )

    with pytest.raises(ConfigError, match="unknown extraction strategy"):
        load_store_configs(tmp_path, ExtractorRegistry([]))
    assert load_store_configs(tmp_path, ExtractorRegistry([ShopifyExtractor()]))


# --------------------------------------------------------------------------------------------
# Which stores are used
# --------------------------------------------------------------------------------------------


def registry_of(tmp_path: Path, *stores: dict[str, object]) -> StoreRegistry:
    for store in stores:
        write(tmp_path, f"{store['id']}.yaml", store)
    return StoreRegistry.from_directory(tmp_path)


def test_only_enabled_stores_in_the_configured_country_are_active(tmp_path: Path) -> None:
    registry = registry_of(
        tmp_path,
        OH_POLLY,
        {**CLUB_L, "enabled": False},
        {**OH_POLLY, "id": "saudi-shop", "name": "Saudi Shop", "country": "SA"},
    )

    active = registry.active(make_settings(country="AE"))

    assert [store.id for store in active] == ["oh-polly"]
    assert [store.id for store in registry.active(make_settings(country="SA"))] == ["saudi-shop"]


def test_a_store_without_enabled_true_is_never_active(tmp_path: Path) -> None:
    registry = registry_of(tmp_path, {k: v for k, v in OH_POLLY.items() if k != "enabled"})

    assert registry.active(make_settings()) == []


def test_settings_stores_narrows_the_active_list(tmp_path: Path) -> None:
    registry = registry_of(tmp_path, OH_POLLY, CLUB_L)

    chosen = registry.active(make_settings(stores=["club-l-london"]))

    assert [store.id for store in chosen] == ["club-l-london"]


def test_settings_stores_may_not_enable_a_disabled_store(tmp_path: Path) -> None:
    registry = registry_of(tmp_path, {**OH_POLLY, "enabled": False})

    assert registry.active(make_settings(stores=["oh-polly"])) == []


def test_lookup_by_id_and_by_display_name(tmp_path: Path) -> None:
    registry = registry_of(tmp_path, OH_POLLY, CLUB_L)

    assert registry.get("oh-polly") is not None
    assert registry.get("nope") is None
    club = registry.by_display_name("Club L London")
    assert club is not None
    assert club.id == "club-l-london"
    assert registry.by_display_name("Unknown") is None


def test_adding_a_store_with_a_known_id_replaces_it(tmp_path: Path) -> None:
    registry = registry_of(tmp_path, OH_POLLY)
    renamed = registry.stores[0].model_copy(update={"name": "Oh Polly UAE"})

    registry.add(renamed)

    assert len(registry.stores) == 1
    assert registry.by_display_name("Oh Polly UAE") is not None
    assert registry.by_display_name("Oh Polly") is None
