"""The one error shape (plan feature 1.2.5)."""

import pytest

from vga.errors import (
    GENERIC_USER_MESSAGE,
    CallBudgetExceededError,
    ConfigError,
    InvalidInputError,
    LlmError,
    StoreBlockedError,
    VgaError,
    user_message_for,
)

SUBCLASSES = [
    InvalidInputError,
    LlmError,
    StoreBlockedError,
    CallBudgetExceededError,
    ConfigError,
]
SECRET_DETAIL = "HTTP 403 from https://internal.example/path?token=abc123 (stack: line 42)"


@pytest.mark.parametrize("error_class", [VgaError, *SUBCLASSES])
class TestEveryErrorClass:
    def test_has_a_plain_language_default_message(self, error_class: type[VgaError]) -> None:
        message = error_class().user_message

        assert len(message) > 20
        assert message.endswith((".", "!"))
        assert "Traceback" not in message
        assert "Exception" not in message

    def test_detail_never_appears_in_str_or_repr(self, error_class: type[VgaError]) -> None:
        error = error_class(detail=SECRET_DETAIL)

        assert SECRET_DETAIL not in str(error)
        assert SECRET_DETAIL not in repr(error)
        assert "abc123" not in str(error.args)
        assert error.detail == SECRET_DETAIL

    def test_str_is_the_user_message(self, error_class: type[VgaError]) -> None:
        error = error_class("Please try again.", detail="x")

        assert str(error) == "Please try again."
        assert error.user_message == "Please try again."

    def test_is_a_vga_error_and_an_exception(self, error_class: type[VgaError]) -> None:
        assert issubclass(error_class, VgaError)
        assert issubclass(error_class, Exception)


class TestCodes:
    @pytest.mark.parametrize(
        ("error_class", "code"),
        [
            (VgaError, "error"),
            (InvalidInputError, "invalid_input"),
            (LlmError, "llm_failure"),
            (StoreBlockedError, "store_blocked"),
            (CallBudgetExceededError, "call_budget_exceeded"),
            (ConfigError, "config"),
        ],
    )
    def test_each_class_has_a_stable_code(self, error_class: type[VgaError], code: str) -> None:
        assert error_class().code == code

    def test_code_can_be_chosen_for_the_base_class(self) -> None:
        error = VgaError("Nothing matched.", code="no_match", detail="0 products")

        assert (error.code, error.user_message, error.detail) == (
            "no_match",
            "Nothing matched.",
            "0 products",
        )

    def test_codes_are_distinct(self) -> None:
        codes = [cls().code for cls in SUBCLASSES]

        assert len(codes) == len(set(codes))


class TestUserMessageFor:
    def test_uses_the_message_of_a_vga_error(self) -> None:
        assert user_message_for(InvalidInputError("Add a photo.")) == "Add a photo."

    def test_never_exposes_the_text_of_an_unexpected_exception(self) -> None:
        error = KeyError("/home/user/.env: secret path")

        assert user_message_for(error) == GENERIC_USER_MESSAGE
        assert "secret" not in user_message_for(error)
