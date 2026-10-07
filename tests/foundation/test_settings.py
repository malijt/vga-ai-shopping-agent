"""Settings model and loader (plan feature 1.3.1)."""

import re
from pathlib import Path

import pytest
import yaml

from tests.factories import make_budget, make_settings
from vga.errors import ConfigError
from vga.models import MixPreset, SettingsOverride, TierMix
from vga.settings import (
    DEFAULT_SETTINGS_PATH,
    ENV_OVERRIDES,
    UNDATED_SNAPSHOT_IDS,
    Settings,
    load_dotenv,
    load_settings,
)

VALID_SNAPSHOT = "example-model-2026-01-31"
# Low-entropy and built at run time, so no secret scanner mistakes it for a real key.
FAKE_KEY = "sk-" + "a" * 24
VALID_REVISION = "0123456789abcdef0123456789abcdef01234567"
# The FashionSigLIP revision measured in spikes/siglip/REPORT.md. Changing it means re-running
# the spike's quality check, so this test must change with it.
MEASURED_SIGLIP_REVISION = "c56244cc94f92419e8369fa71efdaf403b124ce8"
# The OpenAI model pinned in config/settings.yaml: chosen by the user on 2026-10-08; OpenAI lists no
# dated snapshot for it, so the versioned name is the pin. Changing it means re-running the
# Understand eval and adding a prompts/CHANGELOG.md entry.
PINNED_OPENAI_MODEL = "gpt-6-luna"


@pytest.fixture
def settings_file(tmp_path: Path):
    def write(**values: object) -> Path:
        path = tmp_path / "settings.yaml"
        path.write_text(yaml.safe_dump(values), encoding="utf-8")
        return path

    return write


def detail_of(error: pytest.ExceptionInfo[ConfigError]) -> str:
    return error.value.detail or ""


class TestShippedSettingsFile:
    def test_loads_cleanly_with_no_environment(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={})

        assert settings.results == 30
        assert settings.max_per_store == 6

    def test_matches_the_prd_defaults(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={})

        assert settings.country == "AE"
        assert settings.timeout_s == 6
        assert settings.rps_per_store == 1
        assert settings.tier_mix.as_tuple() == (25, 25, 25, 25)
        assert settings.outfit_results_per_garment == 12
        assert settings.store_cache_ttl_s == 600
        assert settings.store_cooldown_s == 900
        assert settings.rps_images_per_host == 5

    def test_openai_model_is_pinned_to_gpt_6_luna(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={})

        assert settings.openai_model == PINNED_OPENAI_MODEL

    def test_the_pinned_model_is_a_dated_snapshot_or_a_verified_undated_one(self) -> None:
        pinned = load_settings(DEFAULT_SETTINGS_PATH, env={}).openai_model

        assert pinned is not None
        assert re.search(r"-\d{4}-\d{2}-\d{2}$", pinned) or pinned in UNDATED_SNAPSHOT_IDS

    def test_the_yaml_explains_why_the_model_has_no_date(self) -> None:
        text = DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8")

        assert "2026-10-08" in text
        assert "no dated snapshot" in text.lower()
        assert "CHANGELOG.md" in text

    def test_the_environment_can_still_override_the_pinned_model(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={"OPENAI_MODEL": VALID_SNAPSHOT})

        assert settings.openai_model == VALID_SNAPSHOT

    def test_siglip_is_pinned_to_the_measured_revision_and_switched_on(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={})

        assert settings.siglip_revision == MEASURED_SIGLIP_REVISION
        assert settings.image_ranker == "siglip"

    def test_yaml_file_agrees_with_the_code_defaults_except_the_pinned_and_market_settings(
        self,
    ) -> None:
        from_file = load_settings(DEFAULT_SETTINGS_PATH, env={}).model_dump()
        defaults = Settings().model_dump()

        differing = {name for name in defaults if from_file[name] != defaults[name]}

        # fx_rates and extra_store_countries are empty in the code (no rate means no conversion, and
        # no other country is searched) and filled in by the shipped file for the Kuwaiti stores.
        assert differing == {
            "image_ranker",
            "siglip_revision",
            "openai_model",
            "fx_rates",
            "extra_store_countries",
        }

    def test_the_code_defaults_leave_the_models_unpinned(self) -> None:
        assert Settings().image_ranker == "off"
        assert Settings().siglip_revision is None
        assert Settings().openai_model is None


class TestTierMix:
    def test_mix_not_summing_to_100_raises_a_clear_error(self, settings_file) -> None:
        path = settings_file(tier_mix={"budget": 25, "mid_range": 25, "premium": 25, "luxury": 20})

        with pytest.raises(ConfigError) as error:
            load_settings(path, env={})

        assert "tier_mix" in detail_of(error)
        assert "sum to 100, got 95" in detail_of(error)
        assert "tier_mix" in str(error.value)

    def test_valid_custom_mix_is_loaded(self, settings_file) -> None:
        path = settings_file(tier_mix={"budget": 40, "mid_range": 30, "premium": 20, "luxury": 10})

        assert load_settings(path, env={}).tier_mix == MixPreset.VALUE_FIRST.mix


class TestEnvironmentOverrides:
    def test_env_var_overrides_yaml(self, settings_file) -> None:
        path = settings_file(image_ranker="off", log_level="INFO")

        settings = load_settings(path, env={"VGA_IMAGE_RANKER": "siglip", "VGA_LOG_LEVEL": "debug"})

        assert settings.image_ranker == "siglip"
        assert settings.log_level == "DEBUG"

    def test_every_documented_variable_reaches_its_field(self) -> None:
        env = {
            "OPENAI_MODEL": VALID_SNAPSHOT,
            "VGA_USER_AGENT": "my-bot/1.0 (test)",
            "VGA_IMAGE_RANKER": "siglip",
            "VGA_LOG_DIR": "logs-elsewhere",
            "VGA_LOG_LEVEL": "WARNING",
            "VGA_LOG_PROMPTS": "1",
            "VGA_DEBUG_DUMP": "true",
            "VGA_DAILY_LLM_CALL_CAP": "7",
            "VGA_UI_FIXTURE": "1",
        }

        settings = load_settings(DEFAULT_SETTINGS_PATH, env=env)

        assert settings.openai_model == VALID_SNAPSHOT
        assert settings.user_agent == "my-bot/1.0 (test)"
        assert settings.image_ranker == "siglip"
        assert settings.log_dir == "logs-elsewhere"
        assert settings.log_level == "WARNING"
        assert settings.log_prompts is True
        assert settings.debug_dump is True
        assert settings.daily_llm_call_cap == 7
        assert settings.ui_fixture is True
        assert set(env) == set(ENV_OVERRIDES)

    def test_empty_env_value_means_not_set(self, settings_file) -> None:
        path = settings_file(image_ranker="siglip")

        assert (
            load_settings(path, env={"VGA_IMAGE_RANKER": "", "OPENAI_MODEL": "  "}).image_ranker
            == "siglip"
        )

    @pytest.mark.parametrize("empty", ["", "   ", "\t"])
    def test_an_empty_openai_model_falls_through_to_the_yaml_value(
        self, settings_file, empty: str
    ) -> None:
        path = settings_file(openai_model="gpt-6-luna")

        settings = load_settings(path, env={"OPENAI_MODEL": empty})

        assert settings.openai_model == "gpt-6-luna"

    @pytest.mark.parametrize("empty", ["", "   "])
    def test_an_empty_openai_model_with_no_yaml_value_is_unset_not_an_empty_string(
        self, settings_file, empty: str
    ) -> None:
        settings = load_settings(settings_file(), env={"OPENAI_MODEL": empty})

        assert settings.openai_model is None

    @pytest.mark.parametrize("empty", ["", "  "])
    def test_every_optional_variable_left_empty_changes_nothing(self, empty: str) -> None:
        without = load_settings(DEFAULT_SETTINGS_PATH, env={})

        with_empty = load_settings(DEFAULT_SETTINGS_PATH, env=dict.fromkeys(ENV_OVERRIDES, empty))

        assert with_empty == without

    def test_an_empty_settings_path_means_the_default_file(self) -> None:
        settings = load_settings(env={"VGA_SETTINGS_PATH": ""})

        assert settings == load_settings(DEFAULT_SETTINGS_PATH, env={})

    def test_the_api_key_is_never_a_setting(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={"OPENAI_API_KEY": FAKE_KEY})

        assert FAKE_KEY not in settings.model_dump_json()
        assert "OPENAI_API_KEY" not in ENV_OVERRIDES

    def test_bad_env_value_names_the_variable(self) -> None:
        with pytest.raises(ConfigError) as error:
            load_settings(DEFAULT_SETTINGS_PATH, env={"VGA_IMAGE_RANKER": "magic"})

        assert "image_ranker" in detail_of(error)
        assert "VGA_IMAGE_RANKER" in detail_of(error)

    def test_settings_path_comes_from_the_environment(self, settings_file) -> None:
        path = settings_file(results=12)

        assert load_settings(env={"VGA_SETTINGS_PATH": str(path)}).results == 12


class TestOpenAiModel:
    @pytest.mark.parametrize(
        "alias",
        [
            "gpt-5-mini",
            "gpt-5",
            "gpt-4o-latest",
            "latest",
            "gpt-5-mini-2026",
            "model-2026-13-01",
            "model-2026-02-30",
            "gpt-6-luna-latest",
            "gpt-5-chat-latest",
            "luna",
            "gpt-6",
            "gpt-6-luna-2",
            "GPT-6-Luna",
            "gpt-5.6-luna",
        ],
    )
    def test_alias_style_names_are_rejected_with_a_clear_message(
        self, settings_file, alias: str
    ) -> None:
        with pytest.raises(ConfigError) as error:
            load_settings(settings_file(openai_model=alias), env={})

        assert "openai_model" in detail_of(error)
        assert "dated snapshot" in detail_of(error)
        assert alias in detail_of(error)

    def test_the_rejection_names_both_allowed_forms(self, settings_file) -> None:
        with pytest.raises(ConfigError) as error:
            load_settings(settings_file(openai_model="gpt-6-luna-latest"), env={})

        assert "-YYYY-MM-DD" in detail_of(error)
        assert "gpt-6-luna" in detail_of(error)
        assert "undated snapshot" in detail_of(error)

    @pytest.mark.parametrize(
        "snapshot", ["gpt-5-mini-2025-08-07", "example-model-2026-01-31", "o3-mini-2025-01-31"]
    )
    def test_dated_snapshots_are_accepted(self, settings_file, snapshot: str) -> None:
        assert load_settings(settings_file(openai_model=snapshot), env={}).openai_model == snapshot

    def test_an_undated_snapshot_from_the_verified_list_is_accepted(self, settings_file) -> None:
        settings = load_settings(settings_file(openai_model="gpt-6-luna"), env={})

        assert settings.openai_model == "gpt-6-luna"

    def test_the_verified_undated_list_holds_exactly_gpt_6_luna(self) -> None:
        # Adding an id means reading OpenAI's model page for it first (see the comment on the
        # constant). This test makes that a deliberate change, not a drive-by edit.
        assert set(UNDATED_SNAPSHOT_IDS) == {"gpt-6-luna"}

    def test_the_undated_exception_is_the_whole_id_not_a_prefix(self, settings_file) -> None:
        for longer in ("gpt-6-luna-preview", "gpt-6-luna-mini", "xgpt-6-luna"):
            with pytest.raises(ConfigError, match="openai_model"):
                load_settings(settings_file(openai_model=longer), env={})

    def test_the_undated_snapshot_is_accepted_from_the_environment_too(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={"OPENAI_MODEL": "gpt-6-luna"})

        assert settings.openai_model == "gpt-6-luna"

    def test_unset_is_allowed(self, settings_file) -> None:
        assert load_settings(settings_file(openai_model=None), env={}).openai_model is None

    def test_alias_from_the_environment_is_rejected(self) -> None:
        with pytest.raises(ConfigError) as error:
            load_settings(DEFAULT_SETTINGS_PATH, env={"OPENAI_MODEL": "gpt-5-mini"})

        assert "OPENAI_MODEL" in detail_of(error)


class TestOtherFields:
    @pytest.mark.parametrize("value", ["siglip", "off"])
    def test_image_ranker_accepts_only_siglip_or_off(self, settings_file, value: str) -> None:
        assert load_settings(settings_file(image_ranker=value), env={}).image_ranker == value

    @pytest.mark.parametrize("value", ["clip", "gpt", "none", "SigLIP2"])
    def test_other_image_rankers_are_rejected(self, settings_file, value: str) -> None:
        with pytest.raises(ConfigError, match="image_ranker"):
            load_settings(settings_file(image_ranker=value), env={})

    def test_unquoted_yaml_off_means_off(self, tmp_path: Path) -> None:
        path = tmp_path / "s.yaml"
        path.write_text("image_ranker: off\n", encoding="utf-8")

        assert load_settings(path, env={}).image_ranker == "off"

    def test_siglip_revision_must_be_a_commit_hash(self, settings_file) -> None:
        assert (
            load_settings(settings_file(siglip_revision=VALID_REVISION), env={}).siglip_revision
            == VALID_REVISION
        )
        for bad in ("main", "v1", VALID_REVISION[:-1], VALID_REVISION.upper()):
            with pytest.raises(ConfigError, match="siglip_revision"):
                load_settings(settings_file(siglip_revision=bad), env={})

    def test_unknown_key_is_rejected_so_typos_fail_loudly(self, settings_file) -> None:
        with pytest.raises(ConfigError, match="reslts"):
            load_settings(settings_file(reslts=10), env={})

    def test_every_invalid_field_is_listed_together(self, settings_file) -> None:
        path = settings_file(results=0, timeout_s=-1, image_ranker="x")

        with pytest.raises(ConfigError) as error:
            load_settings(path, env={})

        for name in ("results", "timeout_s", "image_ranker"):
            assert name in detail_of(error)

    @pytest.mark.parametrize(
        "agent",
        [
            "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "",
            "bad\nagent",
        ],
    )
    def test_user_agent_must_be_honest(self, settings_file, agent: str) -> None:
        with pytest.raises(ConfigError, match="user_agent"):
            load_settings(settings_file(user_agent=agent), env={})

    def test_ranking_weights_must_not_all_be_zero(self, settings_file) -> None:
        with pytest.raises(ConfigError, match="ranking_weights"):
            load_settings(
                settings_file(ranking_weights={"text": 0, "image": 0, "price": 0}), env={}
            )

    def test_missing_file_is_a_clear_error(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_settings(tmp_path / "nope.yaml", env={})

    def test_file_that_is_not_a_mapping_is_a_clear_error(self, tmp_path: Path) -> None:
        path = tmp_path / "s.yaml"
        path.write_text("- just\n- a list\n", encoding="utf-8")

        with pytest.raises(ConfigError, match="mapping"):
            load_settings(path, env={})

    def test_unparsable_yaml_is_a_clear_error(self, tmp_path: Path) -> None:
        path = tmp_path / "s.yaml"
        path.write_text("key: [unclosed\n", encoding="utf-8")

        with pytest.raises(ConfigError, match="could not be read"):
            load_settings(path, env={})

    def test_empty_file_gives_the_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "s.yaml"
        path.write_text("", encoding="utf-8")

        assert load_settings(path, env={}) == Settings()


class TestSiglipScoreRange:
    """``clip((cos - lo) / (hi - lo), 0, 1)`` needs 0 <= lo < hi <= 1 (spikes/siglip/REPORT.md)."""

    def test_defaults_are_the_measured_constants(self) -> None:
        settings = Settings()

        assert settings.siglip_cos_lo == 0.45
        assert settings.siglip_cos_hi == 0.90

    def test_the_shipped_file_carries_the_same_constants(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={})

        assert (settings.siglip_cos_lo, settings.siglip_cos_hi) == (0.45, 0.90)

    @pytest.mark.parametrize(("lo", "hi"), [(0.3, 0.8), (0, 1), (0.0, 0.01), (0.99, 1.0)])
    def test_valid_ranges_are_accepted(self, settings_file, lo: float, hi: float) -> None:
        settings = load_settings(settings_file(siglip_cos_lo=lo, siglip_cos_hi=hi), env={})

        assert (settings.siglip_cos_lo, settings.siglip_cos_hi) == (lo, hi)

    def test_one_value_alone_is_checked_against_the_default_of_the_other(
        self, settings_file
    ) -> None:
        assert load_settings(settings_file(siglip_cos_lo=0.1), env={}).siglip_cos_lo == 0.1
        assert load_settings(settings_file(siglip_cos_hi=0.7), env={}).siglip_cos_hi == 0.7
        with pytest.raises(ConfigError, match="siglip_cos_lo"):
            load_settings(settings_file(siglip_cos_lo=0.95), env={})
        with pytest.raises(ConfigError, match="siglip_cos_lo"):
            load_settings(settings_file(siglip_cos_hi=0.4), env={})

    @pytest.mark.parametrize(("lo", "hi"), [(0.5, 0.5), (0.9, 0.45), (1, 0), (0, 0)])
    def test_lo_must_be_below_hi(self, settings_file, lo: float, hi: float) -> None:
        with pytest.raises(ConfigError) as error:
            load_settings(settings_file(siglip_cos_lo=lo, siglip_cos_hi=hi), env={})

        assert "siglip_cos_lo" in detail_of(error)
        assert "siglip_cos_hi" in detail_of(error)
        assert "must be below" in detail_of(error)

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("siglip_cos_lo", -0.1),
            ("siglip_cos_lo", 1.1),
            ("siglip_cos_hi", -0.5),
            ("siglip_cos_hi", 1.5),
            ("siglip_cos_lo", float("nan")),
            ("siglip_cos_hi", float("inf")),
        ],
    )
    def test_values_outside_zero_to_one_are_rejected(
        self, settings_file, name: str, value: float
    ) -> None:
        with pytest.raises(ConfigError, match=name):
            load_settings(settings_file(**{name: value}), env={})

    def test_a_non_number_is_rejected(self, settings_file) -> None:
        with pytest.raises(ConfigError, match="siglip_cos_hi"):
            load_settings(settings_file(siglip_cos_hi="high"), env={})


class TestMaxImageBytes:
    def test_default_is_eight_megabytes(self) -> None:
        assert Settings().max_image_bytes == 8_000_000

    def test_the_shipped_file_carries_the_same_cap(self) -> None:
        assert load_settings(DEFAULT_SETTINGS_PATH, env={}).max_image_bytes == 8_000_000

    @pytest.mark.parametrize("value", [1, 5_000_000, 20_000_000])
    def test_positive_values_are_accepted(self, settings_file, value: int) -> None:
        assert load_settings(settings_file(max_image_bytes=value), env={}).max_image_bytes == value

    @pytest.mark.parametrize("value", [0, -1, -8_000_000, 1.5, "big"])
    def test_zero_negative_and_non_integer_values_are_rejected(
        self, settings_file, value: object
    ) -> None:
        with pytest.raises(ConfigError, match="max_image_bytes"):
            load_settings(settings_file(max_image_bytes=value), env={})


class TestMaxResponseBytes:
    def test_default_is_two_megabytes(self) -> None:
        assert Settings().max_response_bytes == 2_000_000

    def test_the_shipped_file_carries_the_same_cap(self) -> None:
        assert load_settings(DEFAULT_SETTINGS_PATH, env={}).max_response_bytes == 2_000_000

    @pytest.mark.parametrize("value", [1, 500_000, 10_000_000])
    def test_positive_values_are_accepted(self, settings_file, value: int) -> None:
        assert (
            load_settings(settings_file(max_response_bytes=value), env={}).max_response_bytes
            == value
        )

    @pytest.mark.parametrize("value", [0, -1, -2_000_000, 1.5, "big"])
    def test_zero_negative_and_non_integer_values_are_rejected(
        self, settings_file, value: object
    ) -> None:
        with pytest.raises(ConfigError, match="max_response_bytes"):
            load_settings(settings_file(max_response_bytes=value), env={})


class TestRequestsPerPlatform:
    """The limit shared by all the stores of one platform (the shipped stores are all Shopify)."""

    def test_default_is_two_requests_a_second(self) -> None:
        assert Settings().rps_per_platform == 2

    def test_the_shipped_file_carries_the_same_rate(self) -> None:
        assert load_settings(DEFAULT_SETTINGS_PATH, env={}).rps_per_platform == 2

    def test_the_platform_allows_more_than_one_store_but_is_not_faster_than_the_stores_could_be(
        self,
    ) -> None:
        shipped = load_settings(DEFAULT_SETTINGS_PATH, env={})

        assert shipped.rps_per_store < shipped.rps_per_platform <= 5

    @pytest.mark.parametrize("value", [0.5, 1, 2, 5])
    def test_positive_rates_are_accepted(self, settings_file, value: float) -> None:
        loaded = load_settings(settings_file(rps_per_platform=value), env={})

        assert loaded.rps_per_platform == value

    @pytest.mark.parametrize("value", [0, -1, 5.5, 100, "fast"])
    def test_zero_negative_too_fast_and_non_number_rates_are_rejected(
        self, settings_file, value: object
    ) -> None:
        with pytest.raises(ConfigError, match="rps_per_platform"):
            load_settings(settings_file(rps_per_platform=value), env={})


class TestCurrencySettings:
    """The base currency, the fixed rates into it, and the countries whose stores are searched."""

    def test_the_code_defaults_have_no_rates_and_search_only_the_home_country(self) -> None:
        settings = Settings()

        assert settings.base_currency == "AED"
        assert settings.fx_rates == {}
        assert settings.extra_store_countries == []
        assert settings.searches_country("AE")
        assert not settings.searches_country("KW")

    def test_the_shipped_file_prices_in_aed_and_carries_one_rate_for_the_dinar(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={})

        assert settings.base_currency == "AED"
        # Changing this number means re-reading the sources named beside it in the YAML.
        assert settings.fx_rates == {"KWD": 11.92}

    def test_the_shipped_file_stays_uae_first_and_also_searches_kuwait(self) -> None:
        settings = load_settings(DEFAULT_SETTINGS_PATH, env={})

        assert settings.country == "AE"
        assert settings.extra_store_countries == ["KW"]
        assert settings.searches_country("AE")
        assert settings.searches_country("KW")
        assert not settings.searches_country("SA")

    def test_the_yaml_names_the_source_and_date_of_the_rate_and_calls_it_approximate(self) -> None:
        text = DEFAULT_SETTINGS_PATH.read_text(encoding="utf-8")

        assert "cbk.gov.kw" in text
        assert "2026-10-07" in text
        assert "approximate" in text.lower()
        assert "refresh" in text.lower()

    def test_a_table_of_rates_into_the_base_currency_is_accepted(self, settings_file) -> None:
        loaded = load_settings(
            settings_file(base_currency="AED", fx_rates={"KWD": 11.92, "BHD": 9.74}), env={}
        )

        assert loaded.fx_rates == {"KWD": 11.92, "BHD": 9.74}

    def test_a_whole_number_rate_is_accepted(self, settings_file) -> None:
        assert load_settings(settings_file(fx_rates={"USD": 4}), env={}).fx_rates == {"USD": 4.0}

    def test_the_base_currency_can_be_another_code_with_its_own_table(self, settings_file) -> None:
        loaded = load_settings(settings_file(base_currency="USD", fx_rates={"AED": 0.2723}), env={})

        assert (loaded.base_currency, loaded.fx_rates) == ("USD", {"AED": 0.2723})

    @pytest.mark.parametrize("code", ["kwd", "Kwd", "KW", "KWDD", "K1D", "", " KWD", "KWD "])
    def test_a_rate_key_must_be_exactly_three_upper_case_letters(
        self, settings_file, code: str
    ) -> None:
        with pytest.raises(ConfigError, match="fx_rates"):
            load_settings(settings_file(fx_rates={code: 11.92}), env={})

    @pytest.mark.parametrize("rate", [0, -1, -11.92, float("inf"), float("nan")])
    def test_a_rate_must_be_a_positive_finite_number(self, settings_file, rate: float) -> None:
        with pytest.raises(ConfigError, match="fx_rates"):
            load_settings(settings_file(fx_rates={"KWD": rate}), env={})

    @pytest.mark.parametrize("rate", ["11.92", "", None, True, [11.92], {"rate": 11.92}])
    def test_a_rate_that_is_not_a_number_is_rejected(self, settings_file, rate: object) -> None:
        with pytest.raises(ConfigError, match="fx_rates"):
            load_settings(settings_file(fx_rates={"KWD": rate}), env={})

    @pytest.mark.parametrize("table", [[("KWD", 11.92)], "KWD", 11.92])
    def test_the_rate_table_must_be_a_mapping(self, settings_file, table: object) -> None:
        with pytest.raises(ConfigError, match="fx_rates"):
            load_settings(settings_file(fx_rates=table), env={})

    def test_the_base_currency_must_not_be_in_the_table(self, settings_file) -> None:
        with pytest.raises(ConfigError, match="AED") as error:
            load_settings(settings_file(base_currency="AED", fx_rates={"AED": 1.0}), env={})

        assert "fx_rates" in detail_of(error) or "base_currency" in detail_of(error)

    @pytest.mark.parametrize("code", ["aed", "AE", "DIRHAM", "", "A3D"])
    def test_the_base_currency_must_be_three_upper_case_letters(
        self, settings_file, code: str
    ) -> None:
        with pytest.raises(ConfigError, match="base_currency"):
            load_settings(settings_file(base_currency=code), env={})

    def test_other_countries_are_listed_by_two_letter_code(self, settings_file) -> None:
        loaded = load_settings(settings_file(extra_store_countries=["KW", "SA"]), env={})

        assert loaded.extra_store_countries == ["KW", "SA"]
        assert loaded.searches_country("SA")

    @pytest.mark.parametrize("value", [["KWT"], ["K"], [""], "KW", [1], [None]])
    def test_a_bad_country_list_is_rejected(self, settings_file, value: object) -> None:
        with pytest.raises(ConfigError, match="extra_store_countries"):
            load_settings(settings_file(extra_store_countries=value), env={})

    def test_the_home_country_is_searched_even_if_it_is_not_listed(self) -> None:
        settings = make_settings(country="SA", extra_store_countries=["KW"])

        assert settings.searches_country("SA")
        assert settings.searches_country("KW")
        assert not settings.searches_country("AE")


class TestWithOverrides:
    def test_applies_the_chosen_mix(self) -> None:
        override = SettingsOverride(tier_mix=MixPreset.LUXURY_FIRST.mix)

        assert make_settings().with_overrides(override).tier_mix == TierMix(
            budget=10, mid_range=20, premium=30, luxury=40
        )

    def test_without_a_mix_nothing_changes(self) -> None:
        settings = make_settings()

        assert settings.with_overrides(None) is settings
        assert settings.with_overrides(SettingsOverride(budget=make_budget())) is settings

    def test_does_not_modify_the_original(self) -> None:
        settings = make_settings()

        settings.with_overrides(SettingsOverride(tier_mix=MixPreset.VALUE_FIRST.mix))

        assert settings.tier_mix == MixPreset.EVEN.mix


class TestDotenv:
    def test_loads_simple_lines_and_ignores_comments(self, tmp_path: Path) -> None:
        file = tmp_path / ".env"
        file.write_text(
            "# comment\n\nVGA_LOG_LEVEL=DEBUG\nexport VGA_LOG_DIR='my logs'\n"
            'VGA_USER_AGENT="agent/1.0 (x)"\nOPENAI_MODEL=  # empty with a comment\n'
            "VGA_DEBUG_DUMP=1 # trailing comment\n",
            encoding="utf-8",
        )
        environ: dict[str, str] = {}

        applied = load_dotenv(file, environ)

        assert environ == {
            "VGA_LOG_LEVEL": "DEBUG",
            "VGA_LOG_DIR": "my logs",
            "VGA_USER_AGENT": "agent/1.0 (x)",
            "OPENAI_MODEL": "",
            "VGA_DEBUG_DUMP": "1",
        }
        assert applied == list(environ)

    def test_real_environment_wins_over_the_file(self, tmp_path: Path) -> None:
        file = tmp_path / ".env"
        file.write_text("VGA_LOG_LEVEL=DEBUG\n", encoding="utf-8")
        environ = {"VGA_LOG_LEVEL": "ERROR"}

        load_dotenv(file, environ)

        assert environ["VGA_LOG_LEVEL"] == "ERROR"

    def test_an_empty_real_variable_does_not_block_the_file(self, tmp_path: Path) -> None:
        file = tmp_path / ".env"
        file.write_text("OPENAI_MODEL=gpt-6-luna\nVGA_LOG_LEVEL=DEBUG\n", encoding="utf-8")
        environ = {"OPENAI_MODEL": "", "VGA_LOG_LEVEL": "  "}

        applied = load_dotenv(file, environ)

        assert environ == {"OPENAI_MODEL": "gpt-6-luna", "VGA_LOG_LEVEL": "DEBUG"}
        assert applied == ["OPENAI_MODEL", "VGA_LOG_LEVEL"]

    def test_an_empty_line_in_the_file_does_not_wipe_a_real_value(self, tmp_path: Path) -> None:
        file = tmp_path / ".env"
        file.write_text("OPENAI_MODEL=\nVGA_LOG_LEVEL=\n", encoding="utf-8")
        environ = {"OPENAI_MODEL": "gpt-6-luna"}

        applied = load_dotenv(file, environ)

        assert environ["OPENAI_MODEL"] == "gpt-6-luna"
        assert applied == ["VGA_LOG_LEVEL"]

    def test_missing_file_is_fine(self, tmp_path: Path) -> None:
        assert load_dotenv(tmp_path / "absent.env", {}) == []

    def test_default_load_settings_reads_dotenv_into_the_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("VGA_LOG_LEVEL=ERROR\n", encoding="utf-8")
        # Register the variable with monkeypatch so it is removed again after the test.
        monkeypatch.setenv("VGA_LOG_LEVEL", "placeholder")
        monkeypatch.delenv("VGA_LOG_LEVEL")
        monkeypatch.setattr("vga.settings.DEFAULT_DOTENV_PATH", env_file)

        settings = load_settings(DEFAULT_SETTINGS_PATH)

        assert settings.log_level == "ERROR"

    def test_a_dotenv_with_empty_optional_lines_leaves_the_yaml_values_in_force(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The shape of a real .env: the key filled in, every optional variable present but empty.
        env_file = tmp_path / ".env"
        env_file.write_text(
            "OPENAI_API_KEY=\n" + "".join(f"{name}=\n" for name in ENV_OVERRIDES),
            encoding="utf-8",
        )
        for name in ["OPENAI_API_KEY", *ENV_OVERRIDES]:
            # Register each variable with monkeypatch so it is removed again after the test.
            monkeypatch.setenv(name, "placeholder")
            monkeypatch.delenv(name)
        monkeypatch.setattr("vga.settings.DEFAULT_DOTENV_PATH", env_file)

        settings = load_settings(DEFAULT_SETTINGS_PATH)

        assert settings == load_settings(DEFAULT_SETTINGS_PATH, env={})
        assert settings.openai_model is not None
