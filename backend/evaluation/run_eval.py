"""RAG evaluation harness.

Runs the question suite against a running backend and reports:
  - citation presence where expected
  - honest refusal on unsupported questions (no hallucinated sources)
  - scope: out-of-scope task requests are declined, and never searched
  - routing accuracy (which evidence path the question took)
  - date windows: cited sources actually fall inside the period asked about
  - intent routing accuracy
  - follow-up context retention (same conversation id)
  - latency

Unit tests prove the plumbing holds; this catches the model drifting while it
does. Every check here corresponds to a defect that reached a user.

Usage:
    python evaluation/run_eval.py --base-url http://localhost:8000
Requires the backend to be running with real GUARDIAN_API_KEY / OPENAI_API_KEY.
"""

import argparse
import asyncio
import sys
import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

INSUFFICIENT_MARKERS = [
    "insufficient", "could not find", "couldn't find", "no guardian reporting",
    "not able to locate", "no relevant guardian", "unable to find", "does not appear",
    "no evidence", "wasn't able to find", "no newsroom coverage", "no reporting",
]

#: Wording that shows the assistant declined rather than attempted the task.
DECLINE_MARKERS = ["news research assistant", "outside what i do", "outside what it does"]

#: Answering a coding request at all leaves traces no news answer would have.
ATTEMPTED_TASK_MARKERS = ["def ", "class ", "return ", "```", "import ", "console.log"]


# Windows consoles default to cp1252, which cannot encode the arrows and
# box-drawing this report uses — a full evaluation run once completed and then
# died printing its own results. Reconfigure rather than strip the characters:
# losing the report is losing the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def ask(client: httpx.AsyncClient, question: str, conversation_id: str | None = None) -> dict:
    """One question, retrying past the chat rate limit.

    The suite runs faster than `CHAT_RATE_LIMIT_PER_MINUTE` allows, so a third
    of the first run failed with 429 and was scored as defects. Those were not
    defects, and an evaluation that cannot distinguish "the assistant was
    wrong" from "the harness went too fast" is worse than no evaluation.
    """
    for attempt in range(4):
        response = await client.post(
            "/api/chat",
            json={"message": question, "stream": False, "conversation_id": conversation_id},
            timeout=180,
        )
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()
        # the window is per minute, so back off in that order of magnitude
        await asyncio.sleep(8 * (attempt + 1))
    response.raise_for_status()
    return response.json()


def looks_insufficient(answer: str) -> bool:
    lowered = answer.lower()
    return any(marker in lowered for marker in INSUFFICIENT_MARKERS)


def has_inline_citations(answer: str) -> bool:
    return bool(re.search(r"\[\d+\]", answer))


def check_decline(answer: str, sources: list, mode: str) -> list[str]:
    """An out-of-scope request must be refused without spending a search."""
    issues = []
    lowered = answer.lower()
    if mode and mode != "DECLINE":
        issues.append(f"routed {mode}, expected DECLINE")
    if sources:
        issues.append(f"cited {len(sources)} sources for an out-of-scope request")
    if not any(marker in lowered for marker in DECLINE_MARKERS):
        issues.append("did not decline in the expected terms")
    for marker in ATTEMPTED_TASK_MARKERS:
        if marker in lowered:
            issues.append(f"attempted the task (contains {marker!r})")
            break
    return issues


def check_window(sources: list, days: int) -> list[str]:
    """Cited sources have to fall inside the period the question asked for.

    Sources from outside it are the failure users actually saw: an answer that
    looks period-scoped but is not. A widened window is allowed only when the
    answer says so, which `looks_insufficient` covers separately.
    """
    cutoff = date.today() - timedelta(days=days + 1)  # a day's slack for timezones
    stale = []
    for source in sources:
        raw = (source.get("published_at") or "")[:10]
        if not raw:
            continue
        try:
            published = datetime.fromisoformat(raw).date()
        except ValueError:
            continue
        if published < cutoff:
            stale.append(f"{raw} ({source.get('source', '?')})")
    return [f"sources outside the {days}-day window: {', '.join(stale[:3])}"] if stale else []


async def run(base_url: str) -> int:
    questions = json.loads((Path(__file__).parent / "questions.json").read_text(encoding="utf-8"))
    passed = failed = 0
    rows: list[str] = []

    async with httpx.AsyncClient(base_url=base_url) as client:
        for item in questions:
            start = time.perf_counter()
            issues: list[str] = []
            try:
                result = await ask(client, item["question"])
                answer, sources = result.get("answer", ""), result.get("sources", [])
                intent = result.get("intent", "")
                mode = result.get("mode", "")

                if item.get("expect_decline"):
                    issues.extend(check_decline(answer, sources, mode))

                if item.get("expected_route") and mode not in item["expected_route"]:
                    issues.append(f"routed {mode}, expected one of {item['expected_route']}")

                if item.get("expect_window_days") and not looks_insufficient(answer):
                    issues.extend(check_window(sources, item["expect_window_days"]))

                if item.get("expect_citations"):
                    if not sources:
                        issues.append("no sources returned")
                    if not has_inline_citations(answer) and not looks_insufficient(answer):
                        issues.append("no inline [n] citations")
                    # This used to require every URL to be on theguardian.com,
                    # written when the Guardian was the only source. With NYT
                    # and an aggregator relaying hundreds of outlets, that
                    # assertion fails on correct answers — it was reporting the
                    # product's own growth as a defect.
                    #
                    # What the check was actually for is still worth keeping:
                    # that citations point at real, absolute article URLs
                    # rather than invented ones. A publisher allowlist cannot
                    # be maintained against an aggregator; a well-formed URL
                    # can be checked without one.
                    for source in sources:
                        url = source.get("url", "")
                        if not url.startswith("https://") or len(url) < 20:
                            issues.append(f"suspect citation URL: {url!r}")

                if item.get("expect_insufficient"):
                    if sources and not looks_insufficient(answer):
                        issues.append("hallucination risk: cited sources for unsupported question")
                    if not looks_insufficient(answer):
                        issues.append("did not acknowledge missing evidence")

                if item.get("expected_intent") and intent not in item["expected_intent"]:
                    issues.append(f"intent {intent} not in {item['expected_intent']}")

                if item.get("follow_up"):
                    follow = await ask(client, item["follow_up"], result.get("conversation_id"))
                    follow_answer = follow.get("answer", "")
                    if not follow_answer:
                        issues.append("follow-up returned empty answer")
                    # the thread is replayed into synthesis, so a question
                    # about the previous turn must not come back empty-handed
                    elif looks_insufficient(follow_answer):
                        issues.append("follow-up lost the conversation context")

            except Exception as exc:  # noqa: BLE001
                issues.append(f"request failed: {exc}")

            elapsed = time.perf_counter() - start
            status = "PASS" if not issues else "FAIL"
            if issues:
                failed += 1
            else:
                passed += 1
            rows.append(
                f"[{status}] #{item['id']:>2} {item['category']:<15} {elapsed:5.1f}s  "
                f"{item['question'][:60]}" + (f"  → {'; '.join(issues)}" if issues else "")
            )

    print("\n".join(rows))
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.base_url)))
