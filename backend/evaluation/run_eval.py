"""RAG evaluation harness.

Runs the 20-question suite against a running backend and reports:
  - citation presence where expected
  - honest refusal on unsupported questions (no hallucinated sources)
  - intent routing accuracy
  - follow-up context retention (same conversation id)
  - latency

Usage:
    python evaluation/run_eval.py --base-url http://localhost:8000
Requires the backend to be running with real GUARDIAN_API_KEY / OPENAI_API_KEY.
"""

import argparse
import asyncio
import json
import re
import time
from pathlib import Path

import httpx

INSUFFICIENT_MARKERS = [
    "insufficient", "could not find", "couldn't find", "no guardian reporting",
    "not able to locate", "no relevant guardian", "unable to find", "does not appear",
    "no evidence", "wasn't able to find",
]


async def ask(client: httpx.AsyncClient, question: str, conversation_id: str | None = None) -> dict:
    response = await client.post(
        "/api/chat",
        json={"message": question, "stream": False, "conversation_id": conversation_id},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def looks_insufficient(answer: str) -> bool:
    lowered = answer.lower()
    return any(marker in lowered for marker in INSUFFICIENT_MARKERS)


def has_inline_citations(answer: str) -> bool:
    return bool(re.search(r"\[\d+\]", answer))


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

                if item.get("expect_citations"):
                    if not sources:
                        issues.append("no sources returned")
                    if not has_inline_citations(answer) and not looks_insufficient(answer):
                        issues.append("no inline [n] citations")
                    for source in sources:
                        if not source.get("url", "").startswith("https://www.theguardian.com"):
                            issues.append(f"non-Guardian URL: {source.get('url')}")

                if item.get("expect_insufficient"):
                    if sources and not looks_insufficient(answer):
                        issues.append("hallucination risk: cited sources for unsupported question")
                    if not looks_insufficient(answer):
                        issues.append("did not acknowledge missing evidence")

                if item.get("expected_intent") and intent not in item["expected_intent"]:
                    issues.append(f"intent {intent} not in {item['expected_intent']}")

                if item.get("follow_up"):
                    follow = await ask(client, item["follow_up"], result.get("conversation_id"))
                    if not follow.get("answer"):
                        issues.append("follow-up returned empty answer")

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
