"""Which model answers this turn.

One model for everything is either too slow and expensive for "summarise this
article" or too shallow for "why did this happen, and how does it connect to
the last six months". So the tier is chosen per turn.

**No extra model call is spent deciding.** The understanding step already
produces an intent and a mode before any evidence is fetched, and the evidence
itself is countable — that is enough signal, and asking a model which model to
use would put a round trip in front of every answer to save one behind it.
This also follows the pattern the rest of the app uses for anything that
decides what happens next: `scope.py` and the greeting check are deterministic
for the same reason, because a router that asks the model to classify itself
fails exactly when the model misreads the request.

Tiers map to settings, not to hard-coded names, so a deployment points them at
whatever it has access to. `CHAT_MODEL_REASONING` defaults to the general model
— the routing is real, but nobody is billed for a reasoning model they did not
ask for.
"""

import re
from enum import Enum

from app.core.config import get_settings


class Tier(str, Enum):
    """Least capable model that can do the job well, in ascending order."""

    FAST = "fast"
    GENERAL = "general"
    REASONING = "reasoning"


#: Extraction and restatement. The evidence already contains the answer; the
#: model is arranging it, not working anything out.
SIMPLE_INTENTS = frozenset({"FACT", "ENTITY", "SOURCE_LOOKUP"})

#: Intents that are inherently multi-document: they cannot be answered by
#: restating one passage, because the answer *is* the relationship between
#: several.
COMPLEX_INTENTS = frozenset({"COMPARISON", "TIMELINE", "TREND"})

#: Questions asking for cause, consequence or meaning rather than fact. These
#: are the "why / how / what does this mean" escalation: the evidence reports
#: what happened, and the answer has to reason past it.
_CAUSAL = re.compile(
    r"\b(why|how did|how does|how has|what caused|what led to|what does .{0,40}mean"
    r"|implications?|consequences?|contradict\w*|discrepanc\w*|inconsistent"
    r"|connect(?:ed|ion)?|relationship between|compare[ds]?|versus|pattern"
    r"|explain (?:why|how)|significance|impact of)\b",
    re.IGNORECASE,
)

#: Above this many distinct publishers in the evidence, synthesis stops being
#: summarising and starts being reconciliation — outlets disagree, and deciding
#: what to do about that is the reasoning tier's job.
MANY_SOURCES = 5


def classify(
    *,
    intent: str = "QA",
    mode: str = "NEWS",
    question: str = "",
    source_count: int = 0,
) -> Tier:
    """The tier this turn needs.

    Ordered so the cheapest confident answer wins: a clear de-escalation is
    checked before any escalation, because "summarise the article I am reading"
    should not reach a reasoning model merely for containing the word "why".
    """
    # One known article, restating what it says. Nothing to reconcile — this is
    # the clearest de-escalation available and it is also the most common turn.
    if mode == "ARTICLE" and intent in SIMPLE_INTENTS | {"SUMMARY"}:
        return Tier.FAST

    if intent in SIMPLE_INTENTS and source_count <= 2:
        return Tier.FAST

    if intent in COMPLEX_INTENTS:
        return Tier.REASONING
    if source_count >= MANY_SOURCES:
        return Tier.REASONING
    if _CAUSAL.search(question or ""):
        return Tier.REASONING

    return Tier.GENERAL


def model_for(tier: Tier) -> str:
    """The configured model name for a tier."""
    settings = get_settings()
    return {
        Tier.FAST: settings.chat_model_fast,
        Tier.GENERAL: settings.chat_model,
        Tier.REASONING: settings.chat_model_reasoning,
    }[tier]


#: Longer answers are worth more tokens; a fast extraction is not. Keeps the
#: budget with the tier rather than scattered at call sites.
MAX_TOKENS = {Tier.FAST: 900, Tier.GENERAL: 1800, Tier.REASONING: 2600}


def max_tokens_for(tier: Tier) -> int:
    return MAX_TOKENS[tier]
