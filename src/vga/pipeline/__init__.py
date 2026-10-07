"""Pipeline orchestration: ``SearchPipeline`` wires every step together (Phase 13).

What other phases import::

    from vga.pipeline import SearchPipeline, build_pipeline, pipeline_factory

- ``build_pipeline(settings)``: the real pipeline (registry from ``config/stores/``, one long-lived
  store engine, the image ranker, a lazily created OpenAI understander). ``await warm_up()`` loads
  the image model; ``await aclose()`` releases the HTTP client.
- ``SearchPipeline(understander, searcher, image_ranker, stores, clock=...)``: the same pipeline
  from any three boundaries, which is how the tests and the acceptance harness build it.
- ``pipeline_factory(stores)``: binds the stores so the pipeline fits the harness's
  ``Callable[[Understander, StoreSearcher, ImageRanker], Pipeline]``.

``python -m vga.search --text "..." --image photo.jpg`` runs it from the command line.
"""

from vga.pipeline.build import LazyUnderstander, PipelineFactory, build_pipeline, pipeline_factory
from vga.pipeline.errors import RequestTimeoutError
from vga.pipeline.pipeline import SearchPipeline
from vga.pipeline.validation import sniff_image_kind, validate_request

__all__ = [
    "LazyUnderstander",
    "PipelineFactory",
    "RequestTimeoutError",
    "SearchPipeline",
    "build_pipeline",
    "pipeline_factory",
    "sniff_image_kind",
    "validate_request",
]
