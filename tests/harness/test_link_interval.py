"""A live link check is slow on purpose: at most one request every ``--link-interval`` seconds,
across all stores together, on top of the fetch engine's own per-store limit.

The engine already limits each store to about one request a second, but ten stores each asked once
a second is still ten requests a second from one address, and the platform limits the address.
These tests run on a fake clock, so nothing really waits.
"""

import asyncio
from itertools import pairwise

import pytest

from eval.harness.links import LinkResult
from eval.harness.runstore import REPORT_FILE
from eval.harness.spacing import SpacedLinkFetch
from tests.fakes import FakeClock
from tests.harness.cli_support import Cli, put_photos, wiring_over
from tests.harness.live_parts import LiveParts, ok_link_fetch

RUN = "eval/results/run-1"


class TimedFetch:
    """A link fetch that notes when each request started and takes ``seconds`` to answer."""

    def __init__(self, clock: FakeClock, seconds: float = 0.0) -> None:
        self._clock = clock
        self._seconds = seconds
        self.started: list[float] = []
        self.urls: list[str] = []

    async def __call__(self, url: str) -> LinkResult:
        self.started.append(self._clock.monotonic())
        self.urls.append(url)
        self._clock.advance(self._seconds)
        return await ok_link_fetch(url)


def gaps(times: list[float]) -> list[float]:
    return [round(b - a, 6) for a, b in pairwise(times)]


class TestTheSpacing:
    async def test_the_first_request_goes_at_once_and_the_rest_wait_their_turn(self) -> None:
        clock = FakeClock()
        inner = TimedFetch(clock)
        fetch = SpacedLinkFetch(inner, 2.0, clock)

        for number in range(4):
            await fetch(f"https://a.example/p/{number}")

        assert gaps(inner.started) == [2.0, 2.0, 2.0]
        assert clock.sleeps[0] == 2.0

    async def test_requests_to_different_stores_share_one_turn(self) -> None:
        clock = FakeClock()
        inner = TimedFetch(clock)
        fetch = SpacedLinkFetch(inner, 2.0, clock)

        await fetch("https://a.example/p/1")
        await fetch("https://b.example/p/1")
        await fetch("https://c.example/p/1")

        assert gaps(inner.started) == [2.0, 2.0]

    async def test_a_slow_answer_is_not_waited_for_twice(self) -> None:
        clock = FakeClock()
        inner = TimedFetch(clock, seconds=5.0)  # each request takes longer than the interval
        fetch = SpacedLinkFetch(inner, 2.0, clock)

        for number in range(3):
            await fetch(f"https://a.example/p/{number}")

        assert gaps(inner.started) == [5.0, 5.0]
        assert clock.sleeps == []

    async def test_requests_started_together_are_still_spaced(self) -> None:
        clock = FakeClock()
        inner = TimedFetch(clock)
        fetch = SpacedLinkFetch(inner, 2.0, clock)

        await asyncio.gather(*(fetch(f"https://a.example/p/{n}") for n in range(4)))

        assert gaps(sorted(inner.started)) == [2.0, 2.0, 2.0]

    async def test_a_gap_of_zero_means_no_spacing(self) -> None:
        clock = FakeClock()
        inner = TimedFetch(clock)
        fetch = SpacedLinkFetch(inner, 0.0, clock)

        for number in range(3):
            await fetch(f"https://a.example/p/{number}")

        assert clock.sleeps == []
        assert len(inner.urls) == 3

    async def test_the_answer_comes_back_unchanged(self) -> None:
        clock = FakeClock()
        fetch = SpacedLinkFetch(TimedFetch(clock), 2.0, clock)

        result = await fetch("https://a.example/p/1")

        assert result == await ok_link_fetch("https://a.example/p/1")

    async def test_a_request_that_fails_still_uses_up_its_turn(self) -> None:
        clock = FakeClock()
        started: list[float] = []

        async def failing(url: str) -> LinkResult:
            started.append(clock.monotonic())
            msg = "no route"
            raise OSError(msg)

        fetch = SpacedLinkFetch(failing, 2.0, clock)

        for number in range(2):
            with pytest.raises(OSError, match="no route"):
                await fetch(f"https://a.example/p/{number}")

        assert gaps(started) == [2.0]


class TestTheCommandLine:
    def record(self, cli: Cli, clock: FakeClock, *extra: str) -> TimedFetch:
        fetch = TimedFetch(clock)
        put_photos(cli.root)
        code = cli.run(
            "--record",
            str(cli.root / RUN / "recording"),
            "--pause",
            "0",
            *extra,
            wiring=wiring_over(LiveParts(), fetch),
            clock=clock,
        )
        assert code == 0, cli.errors
        return fetch

    def test_by_default_a_live_run_sends_a_link_request_every_two_seconds(self, cli: Cli) -> None:
        clock = FakeClock()

        fetch = self.record(cli, clock)

        assert len(fetch.urls) == 8  # two stores, four products each
        assert gaps(fetch.started) == [2.0] * 7

    def test_the_interval_can_be_chosen(self, cli: Cli) -> None:
        clock = FakeClock()

        fetch = self.record(cli, clock, "--link-interval", "5")

        assert gaps(fetch.started) == [5.0] * 7

    def test_an_interval_of_zero_turns_the_spacing_off(self, cli: Cli) -> None:
        clock = FakeClock()

        self.record(cli, clock, "--link-interval", "0")

        assert clock.sleeps == []

    def test_links_that_are_not_checked_cost_no_waiting(self, cli: Cli) -> None:
        clock = FakeClock()

        self.record(cli, clock, "--links", "none")

        assert clock.sleeps == []

    @pytest.mark.parametrize("value", ["-1", "soon"])
    def test_a_bad_interval_is_refused(self, cli: Cli, value: str) -> None:
        with pytest.raises(SystemExit) as caught:
            cli.run("--mock", "--link-interval", value)

        assert caught.value.code == 2

    def test_the_report_says_what_the_spacing_was(self, cli: Cli) -> None:
        self.record(cli, FakeClock(), "--link-interval", "3")

        text = (cli.root / RUN / REPORT_FILE).read_text(encoding="utf-8")
        assert "at most one link request every 3 s across all stores" in text

    def test_a_mock_run_checks_its_links_without_waiting(self, cli: Cli) -> None:
        clock = FakeClock()

        cli.run("--mock", "--link-interval", "2", clock=clock)

        assert clock.sleeps == []
        text = (cli.root / "eval" / "results" / "mock" / REPORT_FILE).read_text(encoding="utf-8")
        assert "link request every" not in text
