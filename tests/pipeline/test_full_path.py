"""The longest path through the pipeline with every boundary faked at its lowest level.

OpenAI is faked at HTTP (the real ``OpenAIUnderstander`` and the real SDK talk to it), the stores
at HTTP (the real engine and extractor), and the image model at the embedder (the real FashionSigLIP
ranker, with the engine's own thumbnail fetcher). Everything else is the real code. A shopper sends
a photo and text; a second search changes only the mix.
"""

from tests.factories import make_search_request, make_settings
from tests.pipeline.builders import rerun
from tests.pipeline.conftest import PipelineMaker
from tests.pipeline.world import StoreWorld
from tests.understand.fake_openai import FakeOpenAI, answer
from tests.understand.readings import make_reading, make_reading_budget, make_reading_item
from vga.models import Flag, GenderSource, InputType, MixPreset
from vga.understand import PROMPT_VERSION, OpenAIUnderstander
from vga.understand.budget import CallBudget

MODEL = "gpt-5-mini-2025-08-07"


async def test_a_photo_and_text_search_then_a_mix_change_costs_one_model_call_in_all(
    make_pipeline: PipelineMaker, world: StoreWorld, two_stores: list, tmp_path, clock, photo: bytes
) -> None:
    reading = make_reading(
        input_type=InputType.PHOTO_TEXT,
        items=[
            make_reading_item(
                colour="dark brown",
                gender="men",
                gender_source=GenderSource.EXPLICIT,
                search_keywords=["dark brown oversized blazer", "oversized blazer"],
            )
        ],
        budget=make_reading_budget(max_price=400.0, currency="AED"),
        edits=["dark brown"],
    )
    openai = FakeOpenAI(answer(reading, input_tokens=900, output_tokens=60))
    settings = make_settings(openai_model=MODEL, log_dir=str(tmp_path / "logs"))
    understander = OpenAIUnderstander(
        settings, openai.client(), clock=clock, budget=CallBudget(), jitter=lambda: 0.5
    )
    pipeline = make_pipeline(understander=understander, thumbnails=True)

    first = await pipeline.run(
        make_search_request(image=photo, text="same but dark brown, under 400 AED"), settings
    )

    assert len(openai.requests) == 1
    assert openai.requests[0].image_url is not None  # the photo went to OpenAI, once
    assert first.understood.prompt_version == PROMPT_VERSION
    assert first.understood.budget is not None
    assert first.understood.budget.max_price == 400
    assert (first.usage.llm_calls, first.usage.input_tokens, first.usage.output_tokens) == (
        1,
        900,
        60,
    )
    # the stated budget was applied: nothing over it in the two cheaper ranges, and the dearer
    # ones say so
    cheaper, middle, premium, luxury = first.groups[0].tiers
    assert all(s.product.price <= 400 for s in cheaper.results + middle.results)
    assert any(Flag.OVER_BUDGET in s.flags for s in premium.results + luxury.results)
    store_requests = world.all_requests()

    request, overrides = rerun(first, mix=MixPreset.LUXURY_FIRST.mix)
    second = await pipeline.run(request, settings, overrides)

    assert len(openai.requests) == 1  # still one model call, seen at the OpenAI boundary
    assert world.all_requests() == store_requests  # and no store or thumbnail request
    assert second.usage.llm_calls == 0
    assert second.understood == first.understood
    assert second.groups[0].tiers[3].target_count == 12
    await openai.aclose()
