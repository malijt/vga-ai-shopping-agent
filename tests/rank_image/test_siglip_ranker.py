"""The SigLIP ranker's orchestration (8.1.2, 8.1.3, 8.2.1), with a fake model and fake downloads."""

import builtins
import gc
import math
import socket
import threading
from collections.abc import Sequence
from typing import Any

import pytest
from PIL import Image

from tests.factories import make_product
from tests.rank_image.support import (
    BLACK,
    BLUE,
    PINK,
    RED,
    WHITE,
    ColourEmbedder,
    FakeThumbnails,
    png,
    products_for,
    transparent_png,
)
from vga.models import Product, QueryImage
from vga.rank.image.siglip import ImageEmbedder, SiglipImageRanker

COS_LO = 0.45
COS_HI = 0.90


def make_ranker(
    embedder: ImageEmbedder,
    thumbnails: FakeThumbnails,
    *,
    cos_lo: float = COS_LO,
    cos_hi: float = COS_HI,
    **options: Any,
) -> SiglipImageRanker:
    options.setdefault("embedder_provider", lambda: embedder)
    return SiglipImageRanker(fetch_image=thumbnails, cos_lo=cos_lo, cos_hi=cos_hi, **options)


class TestScores:
    async def test_the_same_picture_scores_one(self) -> None:
        product = make_product(1)
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails({product.key: png(RED)}))

        scores = await ranker.score(QueryImage(image=png(RED)), [product])

        assert scores == {product.key: pytest.approx(1.0)}

    async def test_an_unrelated_picture_scores_clearly_lower(self) -> None:
        same, other = make_product(1), make_product(2)
        thumbnails = FakeThumbnails({same.key: png(RED), other.key: png(BLUE)})
        ranker = make_ranker(ColourEmbedder(), thumbnails)

        scores = await ranker.score(QueryImage(image=png(RED)), [same, other])

        assert scores[same.key] == pytest.approx(1.0)
        assert scores[other.key] == pytest.approx(0.0)

    async def test_a_partial_match_scores_between_the_two(self) -> None:
        product = make_product(1)
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails({product.key: png(PINK)}))

        scores = await ranker.score(QueryImage(image=png(RED)), [product])

        assert scores[product.key] == pytest.approx(0.5)

    async def test_the_cosine_bounds_decide_the_mapping(self) -> None:
        product = make_product(1)
        thumbnails = FakeThumbnails({product.key: png(PINK)})
        ranker = make_ranker(ColourEmbedder(), thumbnails, cos_lo=0.0, cos_hi=0.675)

        scores = await ranker.score(QueryImage(image=png(RED)), [product])

        assert scores[product.key] == pytest.approx(1.0)

    async def test_every_product_gets_an_entry_in_the_order_given(self) -> None:
        products = products_for({"Store A": 3, "Store B": 2})
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails())

        scores = await ranker.score(QueryImage(image=png(RED)), products)

        assert list(scores) == [p.key for p in products]


class TestNoScore:
    async def test_a_thumbnail_that_could_not_be_fetched_has_no_score(self) -> None:
        good, missing = make_product(1), make_product(2)
        thumbnails = FakeThumbnails({missing.key: None})
        ranker = make_ranker(ColourEmbedder(), thumbnails)

        scores = await ranker.score(QueryImage(image=png(RED)), [good, missing])

        assert scores[good.key] == pytest.approx(1.0)
        assert scores[missing.key] is None

    async def test_a_thumbnail_that_is_not_an_image_has_no_score(self) -> None:
        good, broken = make_product(1), make_product(2)
        thumbnails = FakeThumbnails({broken.key: b"<html>404 not found</html>"})
        ranker = make_ranker(ColourEmbedder(), thumbnails)

        scores = await ranker.score(QueryImage(image=png(RED)), [good, broken])

        assert scores[good.key] == pytest.approx(1.0)
        assert scores[broken.key] is None

    async def test_an_empty_download_has_no_score(self) -> None:
        product = make_product(1)
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails({product.key: b""}))

        scores = await ranker.score(QueryImage(image=png(RED)), [product])

        assert scores == {product.key: None}

    async def test_a_fetch_that_raises_costs_only_that_product_its_score(self) -> None:
        good, exploding = make_product(1), make_product(2)
        thumbnails = FakeThumbnails({exploding.key: RuntimeError("connection reset")})
        ranker = make_ranker(ColourEmbedder(), thumbnails)

        scores = await ranker.score(QueryImage(image=png(RED)), [good, exploding])

        assert scores[good.key] == pytest.approx(1.0)
        assert scores[exploding.key] is None

    async def test_when_every_thumbnail_fails_all_scores_are_none(self) -> None:
        products = products_for({"Store A": 3})
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails(default=b"junk"))

        scores = await ranker.score(QueryImage(image=png(RED)), products)

        assert scores == dict.fromkeys(p.key for p in products)

    async def test_without_a_photo_nothing_is_loaded_or_fetched(self) -> None:
        loaded: list[str] = []
        thumbnails = FakeThumbnails()

        def provider() -> ImageEmbedder:
            loaded.append("model")
            return ColourEmbedder()

        ranker = make_ranker(ColourEmbedder(), thumbnails, embedder_provider=provider)
        products = products_for({"Store A": 3})

        for query in (None, QueryImage(), QueryImage(image=b"")):
            scores = await ranker.score(query, products)
            assert scores == dict.fromkeys(p.key for p in products)

        assert loaded == []
        assert thumbnails.calls == []


class TestTransparentImages:
    async def test_a_transparent_thumbnail_is_shown_to_the_model_on_white(self) -> None:
        product = make_product(1)
        embedder = ColourEmbedder()
        ranker = make_ranker(embedder, FakeThumbnails({product.key: transparent_png()}))

        await ranker.score(QueryImage(image=png(RED)), [product])

        # The first image the model saw is the query photo, the second is the thumbnail.
        assert embedder.seen_pixels == [RED, WHITE]
        assert BLACK not in embedder.seen_pixels

    async def test_a_transparent_photo_is_composited_on_white_too(self) -> None:
        product = make_product(1)
        embedder = ColourEmbedder()
        ranker = make_ranker(embedder, FakeThumbnails({product.key: png(WHITE)}))

        scores = await ranker.score(QueryImage(image=transparent_png()), [product])

        assert embedder.seen_pixels == [WHITE, WHITE]
        assert scores[product.key] == pytest.approx(1.0)

    async def test_the_model_only_ever_sees_rgb_images(self) -> None:
        product = make_product(1)
        embedder = ColourEmbedder()
        ranker = make_ranker(embedder, FakeThumbnails({product.key: transparent_png()}))

        await ranker.score(QueryImage(image=transparent_png()), [product])

        assert set(embedder.seen_modes) == {"RGB"}


class TestBatching:
    async def test_forty_thumbnails_go_through_the_model_in_batches_of_sixteen(self) -> None:
        products = products_for({"A": 10, "B": 10, "C": 10, "D": 10})
        embedder = ColourEmbedder()
        ranker = make_ranker(embedder, FakeThumbnails())

        await ranker.score(QueryImage(image=png(RED)), products)

        assert embedder.batch_sizes == [1, 16, 16, 8]  # the photo, then the thumbnails

    async def test_the_batch_size_is_a_parameter(self) -> None:
        products = products_for({"A": 10, "B": 10})
        embedder = ColourEmbedder()
        ranker = make_ranker(embedder, FakeThumbnails(), batch_size=8)

        await ranker.score(QueryImage(image=png(RED)), products)

        assert embedder.batch_sizes == [1, 8, 8, 4]

    async def test_a_thumbnail_that_cannot_be_decoded_does_not_spoil_its_batch(self) -> None:
        products = products_for({"A": 4})
        broken = products[1]
        embedder = ColourEmbedder()
        ranker = make_ranker(embedder, FakeThumbnails({broken.key: b"junk"}))

        scores = await ranker.score(QueryImage(image=png(RED)), products)

        assert embedder.batch_sizes == [1, 3]
        assert [scores[p.key] for p in products].count(None) == 1
        assert scores[broken.key] is None

    async def test_a_model_that_returns_the_wrong_number_of_vectors_is_caught(self) -> None:
        class ShortChanging(ColourEmbedder):
            def embed(self, images: Sequence[Image.Image]) -> list[list[float]]:
                rows = super().embed(images)
                return rows[:1] if len(images) > 1 else rows

        products = products_for({"A": 3})
        ranker = make_ranker(ShortChanging(), FakeThumbnails())

        scores = await ranker.score(QueryImage(image=png(RED)), products)

        assert scores == dict.fromkeys(p.key for p in products)

    @pytest.mark.parametrize("size", [0, -1])
    def test_a_batch_size_below_one_is_refused(self, size: int) -> None:
        with pytest.raises(ValueError, match="batch_size"):
            make_ranker(ColourEmbedder(), FakeThumbnails(), batch_size=size)

    def test_cosine_bounds_in_the_wrong_order_are_refused(self) -> None:
        with pytest.raises(ValueError, match="below"):
            make_ranker(ColourEmbedder(), FakeThumbnails(), cos_lo=0.9, cos_hi=0.45)


class TestThumbnailFetching:
    async def test_all_thumbnails_are_requested_at_the_same_time(self) -> None:
        products = products_for({"A": 10, "B": 10, "C": 10})
        thumbnails = FakeThumbnails()
        ranker = make_ranker(ColourEmbedder(), thumbnails)

        await ranker.score(QueryImage(image=png(RED)), products)

        assert thumbnails.max_in_flight == 30

    async def test_at_most_ten_products_are_fetched_per_store(self) -> None:
        products = products_for({"Store A": 14, "Store B": 3})
        thumbnails = FakeThumbnails()
        ranker = make_ranker(ColourEmbedder(), thumbnails)

        scores = await ranker.score(QueryImage(image=png(RED)), products)

        assert len(thumbnails.calls) == 13
        store_a = [p for p in products if p.store == "Store A"]
        assert [scores[p.key] is not None for p in store_a] == [True] * 10 + [False] * 4

    async def test_products_beyond_the_candidate_cap_are_not_fetched_and_score_none(self) -> None:
        products = products_for({"A": 4, "B": 4, "C": 4})
        thumbnails = FakeThumbnails()
        ranker = make_ranker(ColourEmbedder(), thumbnails, max_candidates=5)

        scores = await ranker.score(QueryImage(image=png(RED)), products)

        assert thumbnails.calls == [p.key for p in products[:4]] + [products[4].key]
        assert [scores[p.key] is not None for p in products] == [True] * 5 + [False] * 7

    async def test_the_default_cap_is_fifty_products(self) -> None:
        products = products_for({f"Store {i}": 10 for i in range(8)})
        thumbnails = FakeThumbnails()
        ranker = make_ranker(ColourEmbedder(), thumbnails)

        scores = await ranker.score(QueryImage(image=png(RED)), products)

        assert len(thumbnails.calls) == 50
        assert len(scores) == 80

    async def test_the_same_product_twice_is_fetched_once(self) -> None:
        product = make_product(1)
        thumbnails = FakeThumbnails()
        ranker = make_ranker(ColourEmbedder(), thumbnails)

        scores = await ranker.score(QueryImage(image=png(RED)), [product, product])

        assert thumbnails.calls == [product.key]
        assert scores == {product.key: pytest.approx(1.0)}

    async def test_the_ranker_opens_no_connection_of_its_own(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Downloads belong to the injected fetcher (allow-list, rate limit, timeout, size cap).
        def refuse(*args: object, **kwargs: object) -> None:
            msg = "the ranker tried to open a connection"
            raise AssertionError(msg)

        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket.socket, "connect_ex", refuse)
        products = products_for({"A": 3})
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails())

        scores = await ranker.score(QueryImage(image=png(RED)), products)

        assert all(score is not None for score in scores.values())

    async def test_a_product_the_fetcher_refuses_has_no_score_and_is_the_only_one(self) -> None:
        # Stands in for Phase 6's allow-list: an off-list image host comes back as None.
        allowed, off_list = make_product(1), make_product(2, image_url="https://evil.example/x.png")

        async def allow_listed_fetch(product: Product) -> bytes | None:
            return png(RED) if "evil" not in str(product.image_url) else None

        ranker = SiglipImageRanker(
            embedder_provider=ColourEmbedder,
            fetch_image=allow_listed_fetch,
            cos_lo=COS_LO,
            cos_hi=COS_HI,
        )

        scores = await ranker.score(QueryImage(image=png(RED)), [allowed, off_list])

        assert scores[allowed.key] == pytest.approx(1.0)
        assert scores[off_list.key] is None

    async def test_nothing_is_written_to_disk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        products = products_for({"A": 4})
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails())
        real_open = builtins.open
        writes: list[object] = []

        def watching_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if any(flag in str(mode) for flag in "wax+"):
                writes.append(file)
            return real_open(file, mode, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", watching_open)
        scores = await ranker.score(QueryImage(image=png(RED)), products)
        monkeypatch.undo()

        assert all(score is not None for score in scores.values())
        assert writes == []


class TestEmbeddingReuse:
    """Plan 8.1.3 / assumption A8: chip edits re-run with the stored vector, not the photo."""

    async def test_the_photos_embedding_is_stored_on_the_query(self) -> None:
        query = QueryImage(image=png(RED))
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails())

        await ranker.score(query, products_for({"A": 2}))

        assert query.embedding == [1.0, 0.0, 0.0]

    async def test_a_second_call_with_only_the_embedding_gives_the_same_scores(self) -> None:
        products = products_for({"A": 3, "B": 3})
        thumbnails = FakeThumbnails(
            {products[0].key: png(RED), products[1].key: png(PINK), products[2].key: png(BLUE)}
        )
        ranker = make_ranker(ColourEmbedder(), thumbnails)
        first_query = QueryImage(image=png(RED))

        first = await ranker.score(first_query, products)
        second = await ranker.score(
            QueryImage(image=None, embedding=first_query.embedding), products
        )

        assert second == first
        assert [first[p.key] for p in products[:3]] == [
            pytest.approx(1.0),
            pytest.approx(0.5),
            pytest.approx(0.0),
        ]

    async def test_scoring_from_the_embedding_does_not_embed_the_photo_again(self) -> None:
        embedder = ColourEmbedder()
        ranker = make_ranker(embedder, FakeThumbnails())
        products = products_for({"A": 2})

        await ranker.score(QueryImage(image=None, embedding=[1.0, 0.0, 0.0]), products)

        assert embedder.batch_sizes == [2]  # the two thumbnails only

    async def test_a_stored_embedding_is_used_even_when_the_photo_is_given_too(self) -> None:
        embedder = ColourEmbedder()
        ranker = make_ranker(embedder, FakeThumbnails())
        query = QueryImage(image=png(BLUE), embedding=[1.0, 0.0, 0.0])

        scores = await ranker.score(query, products_for({"A": 1}))

        assert list(scores.values()) == [pytest.approx(1.0)]  # red embedding vs red thumbnail
        assert embedder.batch_sizes == [1]

    async def test_the_stored_embedding_is_a_plain_list_of_floats_we_do_not_share(self) -> None:
        embedder = ColourEmbedder()
        query = QueryImage(image=png(RED))
        ranker = make_ranker(embedder, FakeThumbnails())

        await ranker.score(query, products_for({"A": 1}))

        assert isinstance(query.embedding, list)
        assert all(isinstance(value, float) for value in query.embedding)

    async def test_an_embedding_from_another_model_degrades_to_no_scores(self) -> None:
        products = products_for({"A": 2})
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails())
        wrong_size = QueryImage(image=None, embedding=[1.0, 0.0])

        scores = await ranker.score(wrong_size, products)

        assert scores == dict.fromkeys(p.key for p in products)

    @pytest.mark.parametrize("bad", [[], [math.nan, 0.0, 0.0], [math.inf, 0.0, 0.0]])
    async def test_an_unusable_stored_embedding_degrades_to_no_scores(
        self, bad: list[float]
    ) -> None:
        products = products_for({"A": 2})
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails())

        scores = await ranker.score(QueryImage(image=None, embedding=bad), products)

        assert scores == dict.fromkeys(p.key for p in products)


class TestPhotoPrivacy:
    async def test_the_ranker_does_not_keep_the_photo(self) -> None:
        photo = png(RED, (9, 9))
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails())

        await ranker.score(QueryImage(image=photo), products_for({"A": 2}))
        gc.collect()

        held = [v for v in vars(ranker).values() if isinstance(v, bytes | bytearray | Image.Image)]
        assert held == []

    async def test_the_photo_bytes_on_the_query_are_left_for_the_caller_to_drop(self) -> None:
        photo = png(RED)
        query = QueryImage(image=photo)
        ranker = make_ranker(ColourEmbedder(), FakeThumbnails())

        await ranker.score(query, products_for({"A": 1}))

        assert query.image == photo


class TestSlowModelDoesNotBlockTheEventLoop:
    async def test_embedding_runs_off_the_event_loop_thread(self) -> None:
        main_thread = threading.get_ident()
        threads: list[int] = []

        class Recording(ColourEmbedder):
            def embed(self, images: Sequence[Image.Image]) -> list[list[float]]:
                threads.append(threading.get_ident())
                return super().embed(images)

        ranker = make_ranker(Recording(), FakeThumbnails())

        await ranker.score(QueryImage(image=png(RED)), products_for({"A": 2}))

        assert threads
        assert main_thread not in threads
