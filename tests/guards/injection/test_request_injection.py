"""Plan 14.3.1: injection through the REQUEST (the shopper's text and photo).

The attacker here is whoever wrote the text or printed the sign in the photo: the seven cases
``e01`` to ``e07`` of ``eval/data/edge_cases.yaml``. For each one, ``obedience.py`` scripts a fake
model that OBEYS: it returns what the attacker asked for (an invented category, a link or markup in
a keyword, control characters, a price word, a huge keyword, an order to search another site, a
price limit read off a sign) on every call, the corrective retry included. The real
``SearchPipeline``, ``OpenAIUnderstander`` and ``StoreSearchEngine`` then run end to end; only
OpenAI (at HTTP level), the store network, the image model and the clock are fake.

What must hold, whatever the model said:

- The shopper gets a valid response, or a plain ``VgaError`` message. Never a stack trace (any
  other exception escapes ``Rig.search`` and fails the test).
- Every store search is the store's own URL template with plain words in ``q``: no link, markup,
  control character, price word or extra parameter, and nothing the attacker named.
- Every request goes to https and to a host on a store's ``allowed_hosts``; none reaches the
  tripwire. Every link in the response stays on its store's hosts.
- Categories stay in the allowed set, and the understanding holds no link, no control character,
  no price word and no echo of the system prompt.

What this cannot show: that the REAL model behaves. That is the live eval's question. And a model
that obeys by inventing a plausible item whose words are harmless (see the section on invented
items) cannot be told from a model that understood; the code can only keep the damage to a search
for plain words.
"""

from typing import Any

import pytest

from tests.factories import make_chip_edits
from tests.guards.injection.conftest import RigFactory
from tests.guards.injection.obedience import OBEDIENCE, TWO_CALLS, Obedience
from tests.guards.injection.support import (
    Outcome,
    Rig,
    answers_every_query,
    assert_friendly,
    assert_hosts_allowed,
    assert_links_on_the_stores_hosts,
    assert_plain_keyword_queries,
    assert_requests_stay_on_the_stores_hosts,
    injection_cases,
    request_for,
)
from tests.pipeline.builders import rerun
from tests.pipeline.world import store_for
from tests.understand.eval_cases import result_problems
from tests.understand.fake_openai import Step, answer, http_error
from tests.understand.readings import make_reading, make_reading_item
from vga.models import (
    Category,
    Gender,
    GenderSource,
    InputType,
    ItemEdit,
    SearchRequest,
    StoreConfig,
)
from vga.pipeline import messages
from vga.understand import FALLBACK_MARKER, FALLBACK_WARNING, FALLBACK_WARNING_WITH_PHOTO
from vga.understand.prompt import system_prompt

CASES = injection_cases()


def parametrized(variants: list[Obedience]) -> pytest.MarkDecorator:
    return pytest.mark.parametrize("variant", variants, ids=[v.id for v in variants])


EVERY_VARIANT = parametrized(OBEDIENCE)
RESPONSE_VARIANTS = parametrized([v for v in OBEDIENCE if v.outcome == "response"])
ERROR_VARIANTS = parametrized([v for v in OBEDIENCE if v.outcome == "friendly_error"])
CONTROL_VARIANTS = parametrized([v for v in OBEDIENCE if v.name == "well_behaved"])
CORRECTED_VARIANTS = parametrized(
    [v for v in OBEDIENCE if v.id in TWO_CALLS and v.name != "model_is_down"]
)

OUTCOME_OF_EXPECTED = {"valid_schema": "response", "friendly_error": "friendly_error"}
"""How the edge-case file's ``expected`` reads at the pipeline: ``valid_schema`` is a response."""


def stores() -> list[StoreConfig]:
    return [store_for("alpha"), store_for("beta")]


def open_stores(
    make_rig: RigFactory, *steps: Step, default: Step | None = None, **options: Any
) -> Rig:
    """Two stores that answer every query, so that every search that happens has results."""
    chosen = stores()
    return make_rig(
        *steps,
        default=default,
        stores=chosen,
        bodies={store.id: answers_every_query(store) for store in chosen},
        **options,
    )


async def run(make_rig: RigFactory, variant: Obedience) -> tuple[Rig, Outcome]:
    rig = open_stores(make_rig, default=variant.answers)
    return rig, await rig.search(request_for(CASES[variant.case]))


# --------------------------------------------------------------------------------------------
# What the shopper gets
# --------------------------------------------------------------------------------------------


@RESPONSE_VARIANTS
async def test_a_model_that_obeys_still_leaves_the_shopper_a_valid_response(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants the request to fail or to go somewhere else. Whatever the model said,
    # the shopper's real request is searched and a valid response comes back.
    _rig, outcome = await run(make_rig, variant)

    assert outcome.error is None, outcome.error
    response = outcome.response
    assert response is not None
    assert response.result_count > 0
    assert 1 <= len(response.understood.items) <= 4
    for warning in response.warnings:
        assert "Traceback" not in warning
        assert not any(bad.casefold() in warning.casefold() for bad in variant.forbidden)


@ERROR_VARIANTS
async def test_a_model_that_obeys_still_leaves_the_shopper_a_plain_error_message(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants the app to act on something that is not a request. There is nothing to
    # shop for, so the shopper is told in plain words what to do next. No stack trace, no internals,
    # none of the attacker's words.
    _rig, outcome = await run(make_rig, variant)

    assert outcome.response is None
    assert outcome.error is not None
    assert_friendly(outcome.error, variant.forbidden)


@ERROR_VARIANTS
async def test_a_request_that_ends_in_an_error_contacts_no_store(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants something searched even though there is nothing to shop for.
    rig, _ = await run(make_rig, variant)

    assert rig.shop.world.all_requests() == 0
    assert rig.shop.queries == []


@CONTROL_VARIANTS
async def test_a_well_behaved_model_gives_the_outcome_the_edge_case_file_expects(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The control run: with no attack obeyed, the pipeline ends exactly as the frozen file says.
    expected = OUTCOME_OF_EXPECTED[CASES[variant.case].expected]
    _rig, outcome = await run(make_rig, variant)

    assert variant.outcome == expected
    assert (outcome.response is not None) == (expected == "response")


# --------------------------------------------------------------------------------------------
# Where the requests go and what they carry
# --------------------------------------------------------------------------------------------


@EVERY_VARIANT
async def test_every_outgoing_request_goes_to_a_host_on_a_stores_allowed_hosts(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants a request sent to a server of its choosing, or to a private address.
    rig, _ = await run(make_rig, variant)

    assert_requests_stay_on_the_stores_hosts(rig.shop)


@EVERY_VARIANT
async def test_no_store_search_carries_a_link_markup_control_character_or_price_word(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants its link, its markup, an escape sequence or a price word inside the
    # words a store is searched for (BRD Rule 7), or an extra parameter in the store's URL.
    rig, _ = await run(make_rig, variant)

    assert_plain_keyword_queries(rig.shop.requests, variant.forbidden)


@EVERY_VARIANT
async def test_the_store_search_is_never_longer_than_a_keyword_may_be(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants the app to send a store an enormous query.
    rig, _ = await run(make_rig, variant)

    assert all(len(query) <= 80 for query in rig.shop.queries)


@EVERY_VARIANT
async def test_a_model_that_obeys_costs_one_call_or_two_and_a_bounded_search(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants a loop of corrective retries, or twenty garments to search.
    rig, _ = await run(make_rig, variant)

    assert len(rig.fake.requests) == (2 if variant.id in TWO_CALLS else 1)
    assert len(rig.shop.search_requests) <= 3 * len(rig.shop.stores)  # one garment, 3 keywords


@RESPONSE_VARIANTS
async def test_every_link_in_the_response_stays_on_its_stores_hosts(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants a result card that links somewhere else.
    rig, outcome = await run(make_rig, variant)

    assert outcome.response is not None
    assert_links_on_the_stores_hosts(outcome.response, rig.shop.stores)


# --------------------------------------------------------------------------------------------
# What the understanding holds
# --------------------------------------------------------------------------------------------


@RESPONSE_VARIANTS
async def test_the_understanding_keeps_categories_in_the_allowed_set_and_text_clean(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants an invented category, a link, a control character, a price word or the
    # system prompt in the result the rest of the app trusts.
    _, outcome = await run(make_rig, variant)

    assert outcome.response is not None
    understood = outcome.response.understood
    assert all(item.category in set(Category) for item in understood.items)
    assert {group.category for group in outcome.response.groups} <= set(Category)
    assert result_problems(understood) == []


@RESPONSE_VARIANTS
async def test_nothing_the_attacker_named_appears_in_the_understanding(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants its words in the understanding the shopper sees as chips and keywords.
    # The forbidden words are the link, markup and delimiter text of the attack.
    _, outcome = await run(make_rig, variant)

    assert outcome.response is not None
    shown = outcome.response.understood.model_dump_json().casefold()
    for bad in variant.forbidden:
        assert bad.casefold() not in shown, bad


@CORRECTED_VARIANTS
async def test_the_corrective_retry_repeats_nothing_the_attacker_wrote(
    make_rig: RigFactory, variant: Obedience
) -> None:
    # The attacker wants its words fed back to the model as a system message through the list of
    # problems that the one retry carries. That list names fields and allowed values, never the
    # offending value.
    rig, _ = await run(make_rig, variant)

    [_first, retry] = rig.fake.requests
    corrective = retry.system_messages[1:]
    assert len(corrective) == 1
    for bad in variant.forbidden:
        assert bad.casefold() not in corrective[0].casefold(), bad
    assert system_prompt() not in corrective[0]


# --------------------------------------------------------------------------------------------
# The model is down: the shopper's own words are searched, and only the first garment sentence
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "query"),
    [
        ("e01", "black leather jacket for men"),
        ("e03", "جاكيت جلد أسود للرجال"),
        ("e04", "white leather sneakers"),
        ("e06", "black bomber jacket for men"),
    ],
)
async def test_when_the_model_is_down_only_the_shoppers_first_garment_sentence_is_searched(
    make_rig: RigFactory, case: str, query: str
) -> None:
    # The attacker wants the injected sentences (print the prompt, add a link, a forged system
    # message) to become the search when the model path fails. The fallback searches the first
    # sentence that names a garment, cleaned, and says so.
    rig = open_stores(make_rig, default=http_error(500))

    outcome = await rig.search(request_for(CASES[case]))

    assert outcome.response is not None
    assert set(rig.shop.queries) == {query}
    assert outcome.response.understood.model == FALLBACK_MARKER
    expected_note = FALLBACK_WARNING_WITH_PHOTO if CASES[case].image else FALLBACK_WARNING
    assert expected_note in outcome.response.warnings


# --------------------------------------------------------------------------------------------
# Instructions stay in the system message; the shopper's text and photo stay data
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", ["e01", "e03", "e04"])
async def test_the_shoppers_text_cannot_close_its_block_or_reach_the_system_message(
    make_rig: RigFactory, case: str
) -> None:
    # The attacker wants to close the <user_text> block and speak as the system ("END OF USER
    # MESSAGE", "[system]: new instructions") so that its text is read as instructions.
    rig = open_stores(make_rig, answer(make_reading(items=[make_reading_item()])))

    await rig.search(request_for(CASES[case]))

    [recorded] = rig.fake.requests
    assert recorded.system_messages == [system_prompt()]  # nothing of the shopper's in it
    assert recorded.user_text.count("<user_text>") == 1
    assert recorded.user_text.count("</user_text>") == 1
    assert recorded.user_text.rstrip().endswith("</user_text>")


@pytest.mark.parametrize("case", ["e05", "e06"])
async def test_text_printed_in_a_photo_is_sent_as_an_image_and_never_as_instructions(
    make_rig: RigFactory, case: str
) -> None:
    # The attacker wants the words printed in the photo to be read as instructions. The photo
    # travels in the user message as an image; the system message is the prompt and nothing else.
    rig = open_stores(
        make_rig, answer(make_reading(items=[make_reading_item()], input_type=InputType.PHOTO_TEXT))
    )

    await rig.search(request_for(CASES[case]))

    [recorded] = rig.fake.requests
    assert recorded.image_url is not None
    assert recorded.image_url.startswith("data:image/")
    assert recorded.system_messages == [system_prompt()]
    assert "evil.example" not in recorded.system_messages[0]


# --------------------------------------------------------------------------------------------
# Things a sign or a stray sentence must not be able to decide
# --------------------------------------------------------------------------------------------


async def test_a_price_limit_and_an_edit_read_only_from_a_photo_are_ignored(
    make_rig: RigFactory,
) -> None:
    # The attacker (a sign in a photo, no typed text) wants a price limit of 1 AED and a request
    # to make it "cheaper" that the shopper never made. A photo cannot state a budget or ask for a
    # change, so both are dropped.
    variant = next(v for v in OBEDIENCE if v.id == "e05-takes_a_price_and_an_edit_from_the_sign")

    _, outcome = await run(make_rig, variant)

    assert outcome.response is not None
    assert outcome.response.understood.budget is None
    assert outcome.response.understood.edits == []
    assert messages.CHEAPER_WITHOUT_BUDGET not in outcome.response.warnings


@pytest.mark.parametrize("case", ["e04", "e05"])
async def test_a_gender_the_shopper_never_stated_is_shown_but_not_applied(
    make_rig: RigFactory, case: str
) -> None:
    # The attacker (text with no gender in it, or a sign) wants the model's claim that the shopper
    # "explicitly" asked for men's clothes to narrow the search (BRD Rule 8). The claim is
    # downgraded to a guess: it is shown, not applied. A women-only store is still searched, and
    # no gender word reaches any query.
    item = make_reading_item(
        category=Category.SHOES,
        colour="white",
        style="sneakers",
        gender=Gender.MEN,
        gender_source=GenderSource.EXPLICIT,
        search_keywords=["men white sneakers", "mens sneakers", "white sneakers for men"],
    )
    chosen = [store_for("alpha"), store_for("beta", genders=[Gender.WOMEN])]
    rig = make_rig(
        answer(make_reading(items=[item])),
        stores=chosen,
        bodies={store.id: answers_every_query(store) for store in chosen},
    )

    outcome = await rig.search(request_for(CASES[case]))

    assert outcome.response is not None
    [understood] = outcome.response.understood.items
    assert (understood.gender, understood.gender_source) == (Gender.MEN, GenderSource.INFERRED)
    assert rig.shop.world.sites["beta"].queries, "the women-only store was skipped for a guess"
    words = {word for query in rig.shop.queries for word in query.casefold().split()}
    assert not words & {"men", "mens", "man", "male"}
    assert messages.inferred_gender_note(Gender.MEN) in outcome.response.warnings


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING: validate_budget keeps a budget when the shopper's text holds no digit at all "
        "(so 'under four hundred dirhams' works). A price read from a sign in the photo then "
        "becomes the shopper's budget. See src/vga/understand/validation.py _validate_budget."
    ),
)
async def test_a_price_read_from_a_sign_is_not_the_budget_when_the_typed_text_has_no_number(
    make_rig: RigFactory,
) -> None:
    # The attacker (a sign in the photo, with a typed request that has no digit in it) wants a
    # price limit of 1 AED the shopper never wrote: it hides good results and shifts the price
    # ranges. The typed text is "black bomber jacket for men"; no number there matches 1.
    variant = next(v for v in OBEDIENCE if v.id == "e06-takes_a_price_from_the_sign")

    _, outcome = await run(make_rig, variant)

    assert outcome.response is not None
    assert outcome.response.understood.budget is None


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING: _validate_edits keeps whatever edits the model reports when the shopper typed "
        "text, without checking they are in that text. An order read from a sign ('cheaper') "
        "switches the request to the value-first mix and adds a 'you asked for cheaper' note. "
        "See src/vga/understand/validation.py _validate_edits."
    ),
)
async def test_an_edit_that_only_a_sign_asked_for_is_not_applied(make_rig: RigFactory) -> None:
    # The attacker (a sign in the photo) wants the search changed ("cheaper") as if the shopper
    # had asked. The typed text is "black bomber jacket for men": it asks for no change.
    variant = next(v for v in OBEDIENCE if v.id == "e06-puts_an_order_from_the_sign_in_the_edits")

    _, outcome = await run(make_rig, variant)

    assert outcome.response is not None
    assert outcome.response.understood.edits == []
    assert messages.CHEAPER_WITHOUT_BUDGET not in outcome.response.warnings


@pytest.mark.xfail(
    strict=True,
    reason=(
        "FINDING (low): the Rule 7 price lexicon lists 'discount(ed)' and 'sale' but not "
        "'discounts', 'sales', 'markdown' or 'NN percent off', so they reach a store search. "
        "See src/vga/understand/lexicon.py _PRICE_WORDS (its docstring says to extend it)."
    ),
)
@pytest.mark.parametrize("phrase", ["discounts", "sales", "markdown", "70 percent off"])
async def test_price_words_beyond_the_lexicon_do_not_reach_a_store(
    make_rig: RigFactory, phrase: str
) -> None:
    # The attacker (or a model told "add discounts to the keywords") wants a price word in a store
    # search (BRD Rule 7: price words are filters, never search terms). The lexicon is a finite
    # list; these are inflections and synonyms of words it already knows.
    item = make_reading_item(
        category=Category.OUTERWEAR,
        colour="black",
        style="leather jacket",
        search_keywords=[f"black leather jacket {phrase}", "leather jacket"],
    )
    rig = open_stores(make_rig, answer(make_reading(items=[item])))

    outcome = await rig.search(SearchRequest(text="black leather jacket"))

    assert outcome.response is not None
    sent = {word for query in rig.shop.queries for word in query.casefold().split()}
    assert not sent & set(phrase.split())


# --------------------------------------------------------------------------------------------
# A model that invents a plausible item: the limit of what code can prove
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "word"),
    [("e02", "PWNED"), ("e07", "mountain")],
    ids=["e02-a-word-the-attacker-chose", "e07-a-word-from-the-scenery"],
)
async def test_an_item_invented_to_look_valid_is_contained_to_a_search_for_plain_words(
    make_rig: RigFactory, case: str, word: str
) -> None:
    # The attacker wants "PWNED" (or a landscape) to be treated as a garment. A model that obeys
    # by returning a valid-looking top with that word as its keyword cannot be told from one that
    # understood, so a search for the word does happen. What the code does guarantee is that the
    # word is only ever a plain keyword to the stores' own hosts, and the response links to nothing
    # else. (The edge-case file expects a friendly error here; only the model can deliver it, and
    # only the live eval can show whether it does.)
    item = make_reading_item(
        category=Category.TOPS, colour=None, style=word, search_keywords=[word]
    )
    input_type = InputType.PRODUCT_PHOTO if CASES[case].image else InputType.TEXT
    rig = open_stores(make_rig, answer(make_reading(items=[item], input_type=input_type)))

    outcome = await rig.search(request_for(CASES[case]))

    assert outcome.response is not None
    assert set(rig.shop.queries) == {word}
    assert_hosts_allowed(rig.shop.requests, rig.shop.strays, rig.shop.allowed_hosts)
    assert_links_on_the_stores_hosts(outcome.response, rig.shop.stores)
    assert_plain_keyword_queries(rig.shop.requests)


# --------------------------------------------------------------------------------------------
# A chip edit is typed by the shopper too
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "colour",
    [
        "brown http://evil.example/x <b>cheap</b> under 100 AED",
        "brown www.evil.example\x00\u202e cheaper",
        "https://evil.example/only-a-link",
    ],
    ids=["link-markup-and-price", "bare-domain-and-control-characters", "only-a-link"],
)
async def test_a_chip_edit_cannot_put_a_link_markup_or_price_word_in_a_store_search(
    make_rig: RigFactory, colour: str
) -> None:
    # The attacker types an injection into the colour chip. The chip edit makes the pipeline
    # search again with keywords rebuilt from the item's fields, with no model call; those words
    # are cleaned like any others.
    rig = open_stores(
        make_rig, answer(make_reading(items=[make_reading_item(search_keywords=["black blazer"])]))
    )
    first = await rig.search(SearchRequest(text="black blazer"))
    assert first.response is not None
    asked_before = len(rig.shop.queries)
    request, overrides = rerun(
        first.response, chips=make_chip_edits(items=[ItemEdit(index=0, colour=colour)])
    )

    again = await rig.search(request, overrides)

    assert again.response is not None
    assert len(rig.shop.queries) > asked_before  # the stores were asked again
    assert len(rig.fake.requests) == 1  # and the model was not
    assert_plain_keyword_queries(rig.shop.requests, forbidden=("evil", "http", "www", "example"))
    assert_requests_stay_on_the_stores_hosts(rig.shop)
    shown = again.response.understood.items[0].colour or ""
    assert not any(bad in shown for bad in ("http", "evil", "<", ">", "\x00", "\u202e"))
