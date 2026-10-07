"""The shared ``Pipeline`` contract suite, run against the real pipeline (Liskov: the fake and the
real pipeline honour the same contract). The real engine, ranker and shaper run; only the stores'
HTTP, OpenAI and the image model are faked."""

import pytest

from tests.foundation.contracts import PipelineContract
from tests.pipeline.conftest import PipelineMaker
from vga.interfaces import Pipeline


class TestSearchPipelineContract(PipelineContract):
    @pytest.fixture
    def pipeline(self, make_pipeline: PipelineMaker, two_stores: list) -> Pipeline:
        return make_pipeline()
