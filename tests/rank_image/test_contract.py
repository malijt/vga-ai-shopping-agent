"""Every image ranker passes the shared `ImageRanker` contract suite (Liskov, plan 8.3.2)."""

import pytest

from tests.factories import make_settings
from tests.foundation.contracts import ImageRankerContract
from tests.rank_image.ml_fakes import REVISION
from tests.rank_image.support import ColourEmbedder, FakeThumbnails
from vga.interfaces import ImageRanker
from vga.rank.image import OffImageRanker, SiglipImageRanker, create_image_ranker


class TestOffRankerContract(ImageRankerContract):
    @pytest.fixture
    def ranker(self) -> ImageRanker:
        return OffImageRanker()


class TestFactoryOffContract(ImageRankerContract):
    @pytest.fixture
    def ranker(self) -> ImageRanker:
        return create_image_ranker(make_settings(image_ranker="off"), fetch_image=FakeThumbnails())


class TestSiglipRankerContract(ImageRankerContract):
    """The real orchestration, with a fake model and fake thumbnail downloads."""

    @pytest.fixture
    def ranker(self) -> ImageRanker:
        return SiglipImageRanker(
            embedder_provider=ColourEmbedder,
            fetch_image=FakeThumbnails(),
            cos_lo=0.45,
            cos_hi=0.90,
        )


class TestFactoryFallbackContract(ImageRankerContract):
    """`siglip` selected but no pinned revision: the factory's ranker degrades to all `None`."""

    @pytest.fixture
    def ranker(self) -> ImageRanker:
        settings = make_settings(image_ranker="siglip", siglip_revision=None)
        return create_image_ranker(settings, fetch_image=FakeThumbnails())


class TestFactoryFallbackWithoutTheMlPackagesContract(ImageRankerContract):
    """`siglip` selected with a pinned revision, but the optional packages cannot be imported: the
    real loader fails, whether or not the `ml` group is installed where the tests run."""

    @pytest.fixture
    def ranker(self, monkeypatch: pytest.MonkeyPatch) -> ImageRanker:
        def absent(name: str) -> object:
            raise ModuleNotFoundError(f"No module named {name!r}")

        monkeypatch.setattr("vga.rank.image.model.import_module", absent)
        settings = make_settings(image_ranker="siglip", siglip_revision=REVISION)
        return create_image_ranker(settings, fetch_image=FakeThumbnails())
