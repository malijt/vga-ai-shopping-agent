"""Shared by the command-line tests: run ``main`` against a temporary repository root.

Nothing here touches the network or OpenAI, and nothing waits on real time. The repository root
is a temporary folder, so no test writes into ``eval/results/`` of the real checkout.
"""

import csv
import io
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from eval.harness.cli import main
from eval.harness.queries import QUERIES_PATH, load_queries
from eval.harness.wiring import Wiring, WiringFactory
from tests.factories import make_settings
from tests.fakes import FakeClock, FakeImageRanker
from tests.harness.helpers import ToyPipeline
from tests.harness.live_parts import LiveParts, make_stores, ok_link_fetch
from vga.interfaces import Clock
from vga.models import Product, QueryImage
from vga.settings import Settings

TODAY = date(2026, 10, 7)
LOAD_SECONDS = 10.0


class SlowToLoadRanker(FakeImageRanker):
    """Stands in for the FashionSigLIP ranker: ``warm_up`` loads the model (10 s on the fake
    clock), and a ranker that was not warmed up loads it inside its first ``score`` call."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        ready: bool = True,
        fails: bool = False,
        embedding: Sequence[float] = (0.1, 0.2, 0.3),
    ) -> None:
        super().__init__(default=0.8, embedding=embedding)
        self._clock = clock
        self._ready = ready
        self._fails = fails
        self.loaded = False
        self.loads = 0
        self.warm_ups = 0

    def _load(self) -> None:
        if not self.loaded:
            self.loaded = True
            self.loads += 1
            self._clock.advance(LOAD_SECONDS)

    async def warm_up(self) -> bool:
        self.warm_ups += 1
        if self._fails:
            msg = "the weights are corrupt"
            raise RuntimeError(msg)
        if self._ready:
            self._load()
        return self._ready

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        if query is not None and self._ready:
            self._load()
        return await super().score(query, products)


class Cli:
    """Runs ``main`` against a temporary repository root and keeps what it printed."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.out = io.StringIO()
        self.err = io.StringIO()

    def run(
        self,
        *argv: str,
        wiring: WiringFactory | None = None,
        settings: Settings | None = None,
        clock: Clock | None = None,
        today: date | None = None,
    ) -> int:
        return main(
            list(argv),
            wiring_factory=wiring,
            settings=settings or make_settings(),
            clock=clock or FakeClock(),
            today=lambda: today or TODAY,
            root=self.root,
            stdout=self.out,
            stderr=self.err,
        )

    @property
    def printed(self) -> str:
        return self.out.getvalue()

    @property
    def errors(self) -> str:
        return self.err.getvalue()


def put_photos(root: Path) -> None:
    """The five private photos, as 1-byte stand-ins (the fake pipeline ignores their content)."""
    for query in load_queries(QUERIES_PATH, require_images=False):
        if query.image:
            target = root / query.image
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"photo")


def wiring_over(live: LiveParts, fetch: object = ok_link_fetch) -> WiringFactory:
    stores = make_stores()

    def factory(settings: Settings) -> Wiring:
        return Wiring(
            pipeline_factory=lambda u, s, r: ToyPipeline(u, s, r, stores),
            stores=stores,
            link_fetch=fetch,  # type: ignore[arg-type]
            build_boundaries=live.boundaries,
        )

    return factory


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fill_sheet(path: Path, good_queries: int) -> None:
    """Label every result of the first ``good_queries`` queries good and the rest not good."""
    ids = [query.id for query in load_queries(QUERIES_PATH, require_images=False)]
    rows = read_rows(path)
    for row in rows:
        row["label"] = "1" if ids.index(row["query_id"]) < good_queries else "0"
    write_rows(path, rows)
