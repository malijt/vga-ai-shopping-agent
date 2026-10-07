"""A photo comparison that did not happen must not be remembered as "no image scores".

If the image ranker failed, came back empty when the model should be working, or was cut short by
the deadline, the first response says so. A re-run that still has the photo's embedding then tries
the comparison again instead of reusing the empty answer, and a re-run with nothing to compare with
repeats the warning, because the results are still ranked without the photo.
"""

from collections.abc import Sequence

from tests.factories import make_search_request, make_settings
from tests.fakes import FakeClock
from tests.pipeline.builders import photo_search, rerun
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.spies import SpyImageRanker
from vga.models import MixPreset, Product, QueryImage
from vga.pipeline import messages

EMBEDDING = [0.1, 0.2, 0.3]


class FlakyRanker:
    """Like the real one: it embeds the photo first and keeps the embedding on the query, then
    the first ``fail_first`` calls cannot compare any thumbnail (every score ``None``)."""

    def __init__(self, fail_first: int = 1, *, stall_first: FakeClock | None = None) -> None:
        self.calls = 0
        self._fail_first = fail_first
        self._stall = stall_first

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        assert query is not None
        self.calls += 1
        if query.embedding is None:
            query.embedding = list(EMBEDDING)
        if self.calls <= self._fail_first:
            if self._stall is not None:
                await self._stall.sleep(1000)
            return {product.key: None for product in products}
        return {product.key: 0.8 for product in products}


class RaisesBeforeEmbedding:
    """A ranker that breaks before it has anything to keep."""

    def __init__(self) -> None:
        self.calls = 0

    async def score(
        self, query: QueryImage | None, products: Sequence[Product]
    ) -> dict[str, float | None]:
        self.calls += 1
        msg = "model crashed"
        raise RuntimeError(msg)


def siglip(tmp_path):
    return make_settings(image_ranker="siglip", log_dir=str(tmp_path / "logs"))


def image_scores(response) -> set:
    return {scored.scores.image for scored in response.products}


async def test_a_rerun_tries_the_photo_comparison_again_and_then_keeps_the_scores(
    make_pipeline: PipelineMaker, two_stores: list, tmp_path, photo: bytes
) -> None:
    settings = siglip(tmp_path)
    ranker = FlakyRanker(fail_first=1)
    pipeline = make_pipeline(understander=photo_search(), image_ranker=ranker)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE in first.warnings
    assert image_scores(first) == {None}

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    assert ranker.calls == 2  # asked again, with the stored embedding and no photo
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE not in second.warnings
    assert image_scores(second) == {0.8}

    request, overrides = rerun(second, mix=MixPreset.LUXURY_FIRST.mix)
    third = await pipeline.run(request, settings, overrides)

    assert ranker.calls == 2  # the scores are in the cache now, so it is not asked a third time
    assert image_scores(third) == {0.8}
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE not in third.warnings


async def test_the_retry_uses_the_embedding_not_the_photo(
    make_pipeline: PipelineMaker, two_stores: list, tmp_path, photo: bytes
) -> None:
    settings = siglip(tmp_path)
    pipeline = make_pipeline(understander=photo_search(), image_ranker=FlakyRanker())
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    await pipeline.run(request, settings, overrides)

    spy = make_pipeline.ranker_spy
    assert isinstance(spy, SpyImageRanker)
    assert [(c.had_photo, c.had_embedding) for c in spy.calls] == [(True, False), (False, True)]


async def test_a_rerun_with_nothing_to_compare_with_repeats_the_warning(
    make_pipeline: PipelineMaker, two_stores: list, tmp_path, photo: bytes
) -> None:
    settings = siglip(tmp_path)
    ranker = RaisesBeforeEmbedding()
    pipeline = make_pipeline(understander=photo_search(), image_ranker=ranker)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    assert first.query_embedding is None  # the ranker broke before it made one

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    assert ranker.calls == 1  # there is no photo and no embedding, so it cannot be asked
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE in second.warnings
    assert image_scores(second) == {None}


async def test_a_comparison_cut_short_by_the_deadline_is_tried_again_on_a_rerun(
    make_pipeline: PipelineMaker, two_stores: list, tmp_path, photo: bytes, clock: FakeClock
) -> None:
    settings = siglip(tmp_path)
    ranker = FlakyRanker(fail_first=1, stall_first=clock)
    pipeline = make_pipeline(understander=photo_search(), image_ranker=ranker)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    assert any("longer than" in warning for warning in first.warnings)
    assert first.query_embedding == EMBEDDING

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    assert ranker.calls == 2
    assert image_scores(second) == {0.8}
    assert not any("longer than" in warning for warning in second.warnings)


async def test_a_ranker_that_is_switched_off_is_not_asked_again_on_a_rerun(
    make_pipeline: PipelineMaker, two_stores: list, settings, photo: bytes
) -> None:
    assert settings.image_ranker == "off"
    ranker = FlakyRanker(fail_first=100)  # always empty, as the "off" ranker is
    pipeline = make_pipeline(understander=photo_search(), image_ranker=ranker)
    first = await pipeline.run(make_search_request(image=photo, text="black blazer"), settings)
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE not in first.warnings  # nobody expected scores

    request, overrides = rerun(first, mix=MixPreset.VALUE_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    assert ranker.calls == 1
    assert messages.IMAGE_SIMILARITY_UNAVAILABLE not in second.warnings
