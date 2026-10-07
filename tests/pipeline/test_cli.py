"""Plan 13.3.1: ``python -m vga.search`` prints the response as JSON; a problem prints the plain
message and exits non-zero. These tests run the real command line code against the fake world.

They are plain (not ``async``) tests on purpose: the command runs its own event loop with
``asyncio.run``, as it does for a user, and that cannot be started from inside a running loop.
"""

import base64
import json
import logging
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.factories import make_image_bytes, make_settings
from tests.fakes import FakeClock, FakeImageRanker, FakeUnderstander
from tests.pipeline.world import StoreWorld, store_for
from vga.errors import InvalidInputError, VgaError
from vga.interfaces import Understander
from vga.log import LOG_FILE_NAME
from vga.models import SearchResponse
from vga.pipeline import SearchPipeline
from vga.search import PipelineBuilder, main
from vga.settings import Settings
from vga.stores import StoreRegistry, StoreSearchEngine

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _no_leftover_log_handlers() -> Iterator[None]:
    """``main`` installs the JSON log handlers; take them away again after each test."""
    yield
    root = logging.getLogger("vga")
    for handler in [h for h in root.handlers if getattr(h, "_vga_handler", False)]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(logging.NOTSET)


@pytest.fixture
def cli_settings(tmp_path: Path) -> Settings:
    return make_settings(log_dir=str(tmp_path / "logs"))


@pytest.fixture
def stores(world: StoreWorld) -> list:
    stores = [store_for("alpha"), store_for("beta")]
    for store in stores:
        world.add(store)
    return stores


def builder(
    world: StoreWorld, clock: FakeClock, understander: Understander | None = None
) -> PipelineBuilder:
    """What ``build_pipeline`` does, with the fakes: the real engine over the fake network."""

    def build(settings: Settings) -> SearchPipeline:
        engine = StoreSearchEngine(settings, StoreRegistry(world.stores()), clock=clock)
        return SearchPipeline(
            understander or FakeUnderstander(),
            engine,
            FakeImageRanker(),
            world.stores(),
            clock=clock,
            on_close=engine.aclose,
        )

    return build


def run_cli(
    argv: list[str],
    world: StoreWorld,
    clock: FakeClock,
    settings: Settings,
    *,
    understander: Understander | None = None,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    code = main(argv, build=builder(world, clock, understander), settings=settings)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --------------------------------------------------------------------------------------------
# --help
# --------------------------------------------------------------------------------------------


def test_help_documents_every_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["--help"])

    assert stopped.value.code == 0
    out = capsys.readouterr().out
    for flag in ("--text", "--image", "--budget", "--currency", "--verbose"):
        assert flag in out
    assert "PNG, JPG or WebP" in out
    assert "tier" not in out.lower()


def test_the_module_runs_as_python_dash_m_and_prints_its_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "vga.search", "--help"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0
    assert "--budget" in result.stdout
    assert result.stderr == ""


# --------------------------------------------------------------------------------------------
# A normal search
# --------------------------------------------------------------------------------------------


def test_it_prints_the_search_response_as_json(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(
        ["--text", "black oversized blazer"], world, clock, cli_settings, capsys=capsys
    )

    assert code == 0
    response = SearchResponse.model_validate_json(out)
    assert response.result_count > 0
    assert [group.category.value for group in response.groups] == ["outerwear"]
    assert json.loads(out)["request_id"] == response.request_id
    assert err == ""  # the JSON is the only thing on standard output; errors would be on stderr


def test_a_budget_flag_sets_the_budget_for_the_search(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = run_cli(
        ["--text", "black oversized blazer", "--budget", "200"],
        world,
        clock,
        cli_settings,
        capsys=capsys,
    )

    assert code == 0
    response = SearchResponse.model_validate_json(out)
    budget_range, mid_range, *_ = response.groups[0].tiers
    assert all(s.product.price <= 200 for s in budget_range.results + mid_range.results)
    assert any("over_budget" in s.flags for s in response.products if s.product.price > 200)


def test_a_budget_in_another_currency_is_reported_by_the_response(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = run_cli(
        ["--text", "black oversized blazer", "--budget", "100", "--currency", "usd"],
        world,
        clock,
        cli_settings,
        capsys=capsys,
    )

    assert code == 0
    assert any(
        "Your budget is in USD" in w for w in SearchResponse.model_validate_json(out).warnings
    )


def test_a_photo_file_is_read_sent_to_the_search_and_never_printed(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    photo = make_image_bytes("JPEG", (64, 64), (10, 120, 200)) + b"PRIVATE-PHOTO-TAIL" * 20
    path = tmp_path / "jacket.jpg"
    path.write_bytes(photo)
    understander = FakeUnderstander()

    code, out, _ = run_cli(
        ["--image", str(path), "--text", "black blazer"],
        world,
        clock,
        cli_settings,
        understander=understander,
        capsys=capsys,
    )

    assert code == 0
    [seen] = understander.calls
    assert seen.image == photo
    assert "PRIVATE-PHOTO-TAIL" not in out
    assert base64.b64encode(photo)[:60].decode() not in out
    assert SearchResponse.model_validate_json(out).result_count > 0


def test_a_png_saved_under_a_jpg_name_is_accepted(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "looks-like-a.jpg"
    path.write_bytes(make_image_bytes("PNG", (48, 48)))

    code, out, _ = run_cli(
        ["--image", str(path), "--text", "black blazer"], world, clock, cli_settings, capsys=capsys
    )

    assert code == 0
    assert SearchResponse.model_validate_json(out).result_count > 0


# --------------------------------------------------------------------------------------------
# Logs
# --------------------------------------------------------------------------------------------


def test_the_log_goes_to_the_log_file_and_not_to_standard_error(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, _, err = run_cli(
        ["--text", "black oversized blazer"], world, clock, cli_settings, capsys=capsys
    )

    assert code == 0
    assert err == ""
    log_file = Path(cli_settings.log_dir) / LOG_FILE_NAME
    lines = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert any(line["message"] == "search started" for line in lines)
    assert (
        len({line["request_id"] for line in lines if line["logger"].startswith("vga.pipeline")})
        == 1
    )


def test_verbose_also_prints_the_log_lines_to_standard_error(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(
        ["--text", "black oversized blazer", "--verbose"],
        world,
        clock,
        cli_settings,
        capsys=capsys,
    )

    assert code == 0
    SearchResponse.model_validate_json(out)  # standard output is still only the JSON
    logged = [json.loads(line) for line in err.splitlines()]
    assert any(line["message"] == "search finished" for line in logged)


# --------------------------------------------------------------------------------------------
# Problems: the plain message on standard error, a non-zero exit, nothing on standard output
# --------------------------------------------------------------------------------------------


def test_an_error_prints_its_plain_message_to_standard_error_and_exits_with_one(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    refusal = InvalidInputError(
        "We can only search for tops, outerwear, bottoms and shoes.", detail="secret detail"
    )

    code, out, err = run_cli(
        ["--text", "a handbag"],
        world,
        clock,
        cli_settings,
        understander=FakeUnderstander(error=refusal),
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert err == "We can only search for tops, outerwear, bottoms and shoes.\n"
    assert "secret detail" not in err


def test_a_file_that_is_not_a_photo_is_refused_with_a_plain_message(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "notes.jpg"
    path.write_text("these are my notes, not a picture")

    code, out, err = run_cli(["--image", str(path)], world, clock, cli_settings, capsys=capsys)

    assert code == 1
    assert out == ""
    assert "PNG, JPG or WebP" in err
    assert "Traceback" not in err
    assert world.all_requests() == 0


def test_a_photo_over_the_size_limit_is_refused_after_reading_only_a_little_past_it(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    small = make_settings(max_image_bytes=2_000, log_dir=str(tmp_path / "logs"))
    photo = make_image_bytes("JPEG", (64, 64)) + b"\x00" * 50_000
    path = tmp_path / "huge.jpg"
    path.write_bytes(photo)
    understander = FakeUnderstander()

    code, out, err = run_cli(
        ["--image", str(path)], world, clock, small, understander=understander, capsys=capsys
    )

    assert code == 1
    assert out == ""
    assert "larger than" in err
    assert understander.calls == []  # refused before any model call


def test_text_over_the_length_limit_is_refused_with_a_plain_message(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(["--text", "x" * 2001], world, clock, cli_settings, capsys=capsys)

    assert code == 1
    assert out == ""
    assert "longer than 2000 characters" in err


def test_a_missing_photo_file_is_refused_with_a_plain_message(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "nowhere" / "photo.jpg"

    code, out, err = run_cli(
        ["--image", str(missing), "--text", "blazer"], world, clock, cli_settings, capsys=capsys
    )

    assert code == 1
    assert out == ""
    assert "photo.jpg" in err
    assert str(tmp_path) not in err  # the message names the file, not the folders around it


def test_a_bad_currency_is_refused_with_a_plain_message(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_cli(
        ["--text", "blazer", "--budget", "100", "--currency", "dirhams"],
        world,
        clock,
        cli_settings,
        capsys=capsys,
    )

    assert code == 1
    assert out == ""
    assert "three letters" in err


def test_an_unexpected_failure_shows_only_the_generic_message(
    world: StoreWorld,
    stores: list,
    clock: FakeClock,
    cli_settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken(settings: Settings) -> SearchPipeline:
        raise RuntimeError("password=hunter2 in /private/path")

    code = main(["--text", "blazer"], build=broken, settings=cli_settings)

    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err.strip() == VgaError.default_message
    assert "hunter2" not in captured.err
    assert "Traceback" not in captured.err


def test_a_command_line_with_nothing_to_search_for_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main([])

    assert stopped.value.code == 2
    assert "--text" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["abc", "0", "-5", "inf"])
def test_a_budget_that_is_not_a_price_is_a_usage_error(
    value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        main(["--text", "blazer", "--budget", value])

    assert stopped.value.code == 2
    assert "not a price above zero" in capsys.readouterr().err
