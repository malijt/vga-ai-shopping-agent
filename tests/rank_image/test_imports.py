"""The ranker must work without the optional `ml` group, and without `transformers`.

Each check runs in a fresh interpreter, because `sys.modules` of the test process is shared and may
already hold `torch` (when the `ml` group is installed and a slow test ran first).
"""

import subprocess
import sys
import textwrap

from vga.settings import PROJECT_ROOT

HEAVY = ("torch", "open_clip", "huggingface_hub", "transformers", "tokenizers", "timm")


def run_python(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - our own interpreter, code written in this file
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        check=False,
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": f"{PROJECT_ROOT / 'src'}:{PROJECT_ROOT}", "PATH": ""},
        timeout=60,
    )


def test_importing_the_package_loads_no_heavy_library() -> None:
    result = run_python(
        f"""
        import sys
        import vga.rank.image
        import vga.rank.image.download
        loaded = [name for name in {HEAVY!r} if name in sys.modules]
        assert not loaded, loaded
        """
    )

    assert result.returncode == 0, result.stderr


def test_the_ranker_degrades_when_every_ml_package_and_transformers_cannot_be_imported() -> None:
    result = run_python(
        f"""
        import asyncio, sys
        for name in {HEAVY!r}:
            sys.modules[name] = None  # any `import name` now raises ImportError
        from vga.models import QueryImage
        from vga.rank.image import create_image_ranker, select_candidates
        from vga.settings import Settings
        from tests.factories import make_image_bytes, make_products

        async def fetch(product):
            raise AssertionError("no thumbnail may be fetched without a model")

        settings = Settings(
            image_ranker="siglip", siglip_revision="c56244cc94f92419e8369fa71efdaf403b124ce8"
        )
        ranker = create_image_ranker(settings, fetch_image=fetch)
        products = select_candidates(make_products(3))
        scores = asyncio.run(ranker.score(QueryImage(image=make_image_bytes()), products))
        assert scores == dict.fromkeys(p.key for p in products), scores
        """
    )

    assert result.returncode == 0, result.stderr
