"""The real Understander passes the same contract suite as the fake (plan 1.2.7, Liskov)."""

import pytest

from tests.foundation.contracts import UnderstanderContract
from tests.understand.conftest import RigFactory
from tests.understand.fake_openai import answer
from tests.understand.readings import make_reading
from vga.interfaces import Understander


class TestOpenAIUnderstanderHonoursTheContract(UnderstanderContract):
    @pytest.fixture
    def understander(self, rig: RigFactory) -> Understander:
        # The model answers every request with the same valid reading; the contract only needs a
        # well-formed result back, whatever the request.
        return rig(default=answer(make_reading())).understander
