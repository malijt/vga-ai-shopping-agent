"""Start-up checks: the model must be set, and the key must exist when a client is built."""

import pytest
from openai import AsyncOpenAI

from tests.factories import make_settings
from tests.understand.fake_openai import API_KEY, FakeOpenAI
from vga.errors import ConfigError
from vga.understand import OpenAIUnderstander, create_openai_client


def test_an_unset_model_is_a_clear_config_error_at_construction() -> None:
    settings = make_settings(openai_model=None)

    with pytest.raises(ConfigError) as caught:
        OpenAIUnderstander(settings, FakeOpenAI().client())

    assert "openai_model" in str(caught.value)
    assert "OPENAI_MODEL" in str(caught.value)
    assert "pinned" in str(caught.value)


def test_an_unset_model_is_reported_before_any_client_is_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("vga.understand.understander.load_dotenv", lambda: [])

    # With no client and no key the model problem is still the one the developer sees first.
    with pytest.raises(ConfigError, match="openai_model"):
        OpenAIUnderstander(make_settings(openai_model=None))


def test_a_missing_api_key_is_a_clear_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("vga.understand.understander.load_dotenv", lambda: [])

    with pytest.raises(ConfigError) as caught:
        create_openai_client()

    assert "OPENAI_API_KEY" in str(caught.value)


def test_a_blank_api_key_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    monkeypatch.setattr("vga.understand.understander.load_dotenv", lambda: [])

    with pytest.raises(ConfigError):
        create_openai_client()


def test_the_default_client_does_its_own_no_retrying(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", API_KEY)
    monkeypatch.setattr("vga.understand.understander.load_dotenv", lambda: [])

    client = create_openai_client(timeout_s=12.0)

    assert isinstance(client, AsyncOpenAI)
    assert client.max_retries == 0
    assert client.timeout == 12.0


def test_the_key_is_never_part_of_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", API_KEY)

    assert API_KEY not in make_settings(openai_model="gpt-5-mini-2025-08-07").model_dump_json()
