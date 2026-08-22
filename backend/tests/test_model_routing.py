"""Which model answers which turn.

The routing is deterministic on purpose — it reads the intent and mode the
understanding step already produced, plus how much evidence came back. Asking a
model which model to use would put a round trip in front of every answer to
save one behind it, and would fail in the same way `scope.py` exists to avoid:
a classifier that fails exactly when the model misreads the request.

These tests pin the two directions that cost real money if they slip —
de-escalation that stops working (everything runs on the expensive tier) and
escalation that stops working (hard questions get a shallow answer).
"""

import pytest

from app.llm.routing import MANY_SOURCES, Tier, classify, max_tokens_for, model_for


# ── de-escalation: the cheap path must stay cheap ────────────────

def test_summarising_the_article_in_front_of_you_is_the_fast_tier():
    """The most common turn in the app, and the one with nothing to reconcile."""
    assert classify(intent="SUMMARY", mode="ARTICLE", question="summarise this") is Tier.FAST


def test_extraction_from_a_couple_of_sources_is_the_fast_tier():
    for intent in ("FACT", "ENTITY", "SOURCE_LOOKUP"):
        assert classify(intent=intent, source_count=1, question="who is the chancellor") is Tier.FAST


def test_a_de_escalated_turn_is_not_dragged_up_by_one_word():
    """"Summarise why the bill passed" is still a summary of one article. A
    causal word in the sentence must not by itself buy the reasoning tier."""
    assert classify(intent="SUMMARY", mode="ARTICLE", question="summarise why this happened") is Tier.FAST


# ── escalation: the hard path must not be answered shallowly ─────

def test_multi_document_intents_reach_the_reasoning_tier():
    """These cannot be answered by restating one passage — the answer *is* the
    relationship between several."""
    for intent in ("COMPARISON", "TIMELINE", "TREND"):
        assert classify(intent=intent, source_count=3, question="x") is Tier.REASONING


@pytest.mark.parametrize(
    "question",
    [
        "why did the Federal Reserve cut rates",
        "how does this connect to the earlier ruling",
        "what does this mean for the election",
        "explain why the policy changed",
        "what are the implications of the tariff",
        "the sources contradict each other, which is right",
    ],
)
def test_cause_and_meaning_questions_escalate(question):
    assert classify(intent="QA", source_count=3, question=question) is Tier.REASONING


def test_many_publishers_escalate_because_they_may_disagree():
    """Past a handful of outlets, synthesis stops being summarising and starts
    being reconciliation."""
    assert classify(intent="QA", source_count=MANY_SOURCES, question="what happened") is Tier.REASONING
    assert classify(intent="QA", source_count=MANY_SOURCES - 1, question="what happened") is Tier.GENERAL


# ── the ordinary middle ──────────────────────────────────────────

def test_a_plain_news_question_uses_the_general_tier():
    assert classify(intent="QA", source_count=3, question="what happened in the budget") is Tier.GENERAL


def test_defaults_are_safe_when_nothing_is_known():
    """An unclassified turn must not silently land on the most expensive tier."""
    assert classify() is Tier.GENERAL


# ── configuration, not hard-coded names ──────────────────────────

def test_every_tier_resolves_to_a_configured_model():
    for tier in Tier:
        assert model_for(tier), f"{tier} has no model configured"


def test_the_reasoning_tier_defaults_to_the_general_model():
    """The routing is real, but a deployment should opt into a reasoning model
    rather than be billed for one it never chose."""
    assert model_for(Tier.REASONING) == model_for(Tier.GENERAL)


def test_token_budget_rises_with_the_tier():
    assert max_tokens_for(Tier.FAST) < max_tokens_for(Tier.GENERAL) < max_tokens_for(Tier.REASONING)
