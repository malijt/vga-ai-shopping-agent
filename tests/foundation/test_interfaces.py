"""The protocols in vga.interfaces (plan feature 1.2.4)."""

import pytest

from vga.interfaces import (
    Clock,
    ImageRanker,
    Pipeline,
    StoreSearcher,
    SystemClock,
    Understander,
)


class DummyClock:
    def monotonic(self) -> float:
        return 0.0

    async def sleep(self, seconds: float) -> None:
        return None


class DummyUnderstander:
    async def understand(self, req):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class DummyStoreSearcher:
    async def search(self, item, stores):  # type: ignore[no-untyped-def]
        return []


class DummyImageRanker:
    async def score(self, query, products):  # type: ignore[no-untyped-def]
        return {}


class DummyPipeline:
    async def run(self, req, settings, overrides=None, on_step=None):  # type: ignore[no-untyped-def]
        raise NotImplementedError


class Empty:
    pass


@pytest.mark.parametrize(
    ("protocol", "dummy"),
    [
        (Clock, DummyClock),
        (Understander, DummyUnderstander),
        (StoreSearcher, DummyStoreSearcher),
        (ImageRanker, DummyImageRanker),
        (Pipeline, DummyPipeline),
    ],
)
class TestRuntimeCheckable:
    def test_a_dummy_with_the_right_method_passes(self, protocol: type, dummy: type) -> None:
        assert isinstance(dummy(), protocol)

    def test_an_object_without_the_method_fails(self, protocol: type, dummy: type) -> None:
        assert not isinstance(Empty(), protocol)


class TestSystemClock:
    def test_is_a_clock(self) -> None:
        assert isinstance(SystemClock(), Clock)

    def test_monotonic_does_not_go_backwards(self) -> None:
        clock = SystemClock()
        first = clock.monotonic()

        assert clock.monotonic() >= first
