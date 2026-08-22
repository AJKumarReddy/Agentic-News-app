"""Scope guardrail: what this assistant will and will not answer.

This is a news research assistant. Before the guardrail existed, "write a
python code for reversing linked list" was routed to WEB mode — which the
understanding step legitimately offers for how-to and documentation lookups —
searched, answered in full, and given a citation. A general-purpose coding
answer dressed up as sourced journalism is worse than no answer: it spends the
model, the search budget, and the user's trust in the citation on something the
product does not do.

The check is deliberately deterministic rather than a prompt instruction. A
guardrail that depends on the same model it is guarding fails exactly when the
model misreads the request, which is the case it exists for. The LLM is also
told about the mode (defence in depth), but this module is the guarantee.

Two rules decide it:
  1. Does the message read as a *task request* — do this for me — of a kind we
     don't do (code, maths, translation, creative writing, roleplay)?
  2. For the rules that key on subject matter rather than on an imperative
     ("merge sort", "time complexity"), does news framing rescue it? It must:
     "news about a bug in the merge sort" is a news question.

Topic mentions are never enough on their own. This blocks requests to perform
work, not subject matter: news about programming, AI, or mathematics is
ordinary news and must keep working. The reverse also holds — news words do not
launder a task request, so "write a python script to scrape headlines" is still
declined.
"""

import re

# Requests to write or debug software.
_CODE = re.compile(
    r"\b(write|generate|create|produce|draft|give me|show me|provide)\b[^.?!]{0,40}"
    r"\b(code|program|script|function|method|class|algorithm|regex|snippet|pseudocode|query)\b"
    r"|\b(implement|debug|refactor|optimi[sz]e|unit.?test)\b[^.?!]{0,30}"
    r"\b(code|program|function|method|class|algorithm|bug|app)\b"
    r"|\b(how (?:do|can|would) (?:i|you|we)|show me how to)\b[^.?!]{0,60}"
    r"\b(?:in|using|with)\s+(python|java|javascript|typescript|c\+\+|c#|ruby|php|rust|golang|sql|react|node)\b"
    r"|\bfix (?:my|this|the) (code|script|program|function|bug|error)\b",
    re.IGNORECASE,
)

# Textbook data-structure and algorithm exercises. Only unambiguous terms —
# "stack", "queue" and "graph" are ordinary English and stay out of this list.
_EXERCISE = re.compile(
    r"\b(linked list|binary (?:search )?tree|binary search|bubble sort|quick ?sort|merge sort|"
    r"hash ?(?:map|table)|dynamic programming|time complexity|big.?o notation|"
    r"fizz ?buzz|leet ?code|fibonacci|factorial|palindrome)\b",
    re.IGNORECASE,
)

# Homework maths — computation asked of us, not reported figures.
_MATH = re.compile(
    r"\b(solve|calculate|compute|evaluate|simplify|differentiate|integrate|factorise|factorize)\b"
    r"[^.?!]{0,40}\b(equation|integral|derivative|expression|matrix|polynomial|for x|this problem|sum of)\b",
    re.IGNORECASE,
)

# Ghostwriting and translation.
_AUTHORING = re.compile(
    r"\bwrite (?:me )?(?:a|an|the|my) (essay|poem|song|story|joke|email|letter|cover letter|"
    r"resume|cv|blog post|tweet|caption|speech|screenplay|assignment|homework)\b"
    r"|\btranslate\b[^.?!]{0,40}\b(?:in)?to \w+",
    re.IGNORECASE,
)

# Attempts to repurpose the assistant or extract its instructions.
_ROLEPLAY = re.compile(
    r"\bignore (?:all )?(?:your |the )?(?:previous|prior|above|earlier) (?:instructions|prompts?|rules)\b"
    r"|\b(?:act|behave) as (?:a|an|my) \w+"
    r"|\bpretend (?:to be|you(?:'re| are))\b"
    r"|\b(?:your|the) system prompt\b"
    r"|\bjailbreak\b",
    re.IGNORECASE,
)

_RULES = (
    ("code", _CODE),
    ("exercise", _EXERCISE),
    ("math", _MATH),
    ("authoring", _AUTHORING),
    ("roleplay", _ROLEPLAY),
)

# Only the subject-matter rules can be rescued by news framing. The others fire
# on an imperative addressed to us, which no amount of news vocabulary changes.
_RESCUABLE = {"exercise", "math"}

_NEWS_FRAMING = re.compile(
    r"\b(news|reported|reporting|reports|coverage|covered|headlines?|articles?|stor(?:y|ies)|"
    r"journalis\w*|guardian|nyt|new york times|press|announced|according to)\b",
    re.IGNORECASE,
)

# "code" is an ordinary news word in these compounds; strip them before the
# software rules run so "show me the code of conduct" is not read as a request
# to write software.
_CODE_IDIOM = re.compile(
    r"\b(?:code of (?:conduct|practice|ethics|silence)|(?:penal|dress|building|highway|tax|"
    r"criminal|civil|electoral|planning|postal|zip|area|country|discount|promo|qr|bar)\s?code"
    r"|codes? of law)\b",
    re.IGNORECASE,
)

DECLINE_MESSAGE = (
    "I'm a news research assistant — I answer questions about news and current events "
    "from Guardian and New York Times journalism, with web sources for extra context. "
    "Writing code, solving maths problems, and general writing tasks are outside what I do.\n\n"
    "Ask me what's been reported on a topic, person, event or organisation and I'll go "
    "through the coverage."
)


def out_of_scope_reason(*messages: str) -> str:
    """Name the rule that puts these messages out of scope, or "" if in scope.

    Accepts several strings — normally the raw message and the resolved
    standalone question — because a follow-up ("now do that in python") only
    becomes recognisable once it has been resolved against the conversation.
    """
    for text in messages:
        if not text:
            continue
        cleaned = _CODE_IDIOM.sub(" ", text)
        news_framed = bool(_NEWS_FRAMING.search(cleaned))
        for name, pattern in _RULES:
            if not pattern.search(cleaned):
                continue
            if news_framed and name in _RESCUABLE:
                continue
            return name
    return ""


def is_out_of_scope(*messages: str) -> bool:
    return bool(out_of_scope_reason(*messages))


# Greetings and pleasantries. "hi" is not a news question, and treating it as
# one produced the worst possible first impression: the reader typed one word
# and got a Guardian piece about water storage, "understood as" a question they
# never asked. Deterministic for the same reason the rules above are — the
# resolver's job is to turn a fragment into a searchable question, so given
# "hi" it will invent one rather than admit there is nothing there.
#
# Anchored and length-capped so it only ever catches a message that is *only* a
# greeting: "hi, what happened in Gaza today" is a news question with a polite
# opening and must search normally.
_GREETING = re.compile(
    r"^\s*(?:hi|hey+|hello+|yo|howdy|greetings|hiya|sup"
    r"|good\s+(?:morning|afternoon|evening|day)"
    r"|how(?:'?s|\s+is|\s+are)\s+(?:it\s+going|you|things)"
    r"|what'?s\s+up|thanks|thank\s+you|thx|ta|cheers"
    r"|ok(?:ay)?|cool|nice|great|bye|goodbye|see\s+ya)"
    r"[\s,.!?]*(?:sage|there|mate|friend)?[\s,.!?]*$",
    re.IGNORECASE,
)

#: Past this, a message is a real question however politely it opens.
_GREETING_MAX_CHARS = 40

GREETING_MESSAGE = (
    "Hello — I'm Sage, your research guide here.\n\n"
    "Ask me about a topic, person, event or organisation and I'll search the newsrooms, "
    "compare what they reported, and give you an answer with citations you can check. "
    "You can also ask what has happened today, or how outlets differ on a story."
)


def is_greeting(message: str) -> bool:
    """Whether the message is *only* a greeting or pleasantry."""
    if not message or len(message.strip()) > _GREETING_MAX_CHARS:
        return False
    return bool(_GREETING.match(message))


NO_EVIDENCE_MESSAGE = (
    "I could not find reporting on that in the journalism I have indexed.\n\n"
    "That may mean the newsrooms I read have not covered it, that it is too "
    "recent to be indexed yet, or that it did not happen. I would rather say so "
    "than assemble an answer out of loosely related articles."
)
