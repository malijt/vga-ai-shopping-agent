"""The injection points the harness leaves open for the real application (Phase 16).

The real pipeline does not exist while the harness is built (Phase 13), and the harness must not
depend on the OpenAI SDK, ``httpx`` or ``open_clip`` (Dependency Inversion). Everything it needs
from the real application therefore comes in through ``Wiring``:

- ``pipeline_factory``: builds a ``Pipeline`` from the three boundary implementations. The harness
  calls it with recorders around the live parts (``--record``) or with stand-ins fed from a
  recording (``--replay``), so the real pipeline, ranking and price-range logic run in both cases.
- ``stores``: the enabled store configs, for the report and for the link checker's allowed hosts.
- ``link_fetch``: a polite page fetch for the link checker. May be ``None`` for an offline setup.
- ``build_boundaries``: builds the real ``Understander``, ``StoreSearcher`` and ``ImageRanker``.
  Only called for ``--record``, so ``--replay`` needs no OpenAI key and starts no model.

A wiring module exposes one function, ``(Settings) -> Wiring``, and is named on the command line
as ``--wiring package.module:function``.
"""

import importlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from eval.harness.errors import WiringError
from eval.harness.links import LinkFetch
from vga.interfaces import ImageRanker, Pipeline, StoreSearcher, Understander
from vga.models import StoreConfig
from vga.settings import Settings

PipelineFactory = Callable[[Understander, StoreSearcher, ImageRanker], Pipeline]


@dataclass(frozen=True)
class Boundaries:
    """The three places the pipeline touches the outside world."""

    understander: Understander
    searcher: StoreSearcher
    image_ranker: ImageRanker


@dataclass(frozen=True)
class Wiring:
    pipeline_factory: PipelineFactory
    stores: Sequence[StoreConfig]
    link_fetch: LinkFetch | None = None
    build_boundaries: Callable[[], Boundaries] | None = None


WiringFactory = Callable[[Settings], Wiring]


def load_wiring_factory(spec: str) -> WiringFactory:
    """Resolve ``package.module:function`` to the function that builds the wiring."""
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name or not attribute:
        msg = f"--wiring must look like package.module:function, got {spec!r}"
        raise WiringError(msg)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        msg = f"--wiring: the module {module_name!r} could not be imported ({exc})"
        raise WiringError(msg) from exc
    factory = getattr(module, attribute, None)
    if not callable(factory):
        msg = f"--wiring: {module_name!r} has no function named {attribute!r}"
        raise WiringError(msg)
    return factory  # type: ignore[no-any-return]
