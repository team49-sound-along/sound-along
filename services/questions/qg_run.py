"""Command line: generate DRAFT questions for passages and print an honest report (every question, every drop, tokens, time, cost).

    python qg_run.py --timing data/<id>.timing.json --model ollama:gpt-oss:20b --limit 3
    python qg_run.py --timing data/<id>.timing.json --model bedrock:<modelId> --region us-west-2 --limit 1
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from qg_adapters import AdapterError, ModelAdapter, adapter_from_spec
from qg_cost import price_for
from qg_pipeline import GenerationError, generate_draft

DEFAULT_LIMIT = 3  # a hard cap on passages per run, so one command can never spend more than a few passages' worth


def format_report(draft: Mapping[str, Any]) -> str:
    lines = [f"== {draft.get('title')} ({draft.get('passageId')}) ==", f"model: {draft.get('generatedWith', {}).get('model')}"]
    for question in draft.get("questions", []):
        checks = question.get("checks", {})
        lines.append(f"\n{question['id']} [{question['skill']}] {question['question']}")
        for i, choice in enumerate(question["choices"]):
            lines.append(f"   {'ABCD'[i]}{'*' if i == question['answerIndex'] else ' '} {choice}")
        lines.append(f"   evidence: sentence {question['evidenceSentence']}")
        lines.append(
            f"   checks: answers correctly from the passage = {'yes' if checks.get('answeredFromPassage') else 'NO'}; "
            f"guessable without the passage = {'YES (flagged)' if checks.get('guessableWithoutPassage') else 'no'}"
        )
    dropped = draft.get("dropped", [])
    lines.append(f"\ndropped: {len(dropped)}")
    for item in dropped:
        lines.append(f"   - {item['question']}  [{'; '.join(item['reasons'])}]")
    m = draft.get("metrics", {})
    cost = m.get("estimatedCostUsd")
    lines.append(
        f"\nmodel calls: {m.get('calls')}, tokens in/out: {m.get('inputTokens')}/{m.get('outputTokens')}, time: {m.get('seconds')} s, "
        f"estimated cost: {'unknown' if cost is None else f'${cost:.6f}'}"
    )
    lines.append(f"price basis: {m.get('priceBasis')}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None, adapter_factory: Callable[[str, str], ModelAdapter] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate draft practice questions. Drafts are never served; a person approves them.")
    parser.add_argument("--timing", nargs="+", required=True, type=Path, help="timing JSON files (data/<id>.timing.json)")
    parser.add_argument("--model", default="ollama:gpt-oss:20b")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--out", default=Path("samples/questions"), type=Path, help="where drafts go (must not be a served folder)")
    parser.add_argument("--n", default=4, type=int)
    parser.add_argument("--seed", default=7, type=int)
    parser.add_argument("--limit", default=DEFAULT_LIMIT, type=int, help="most passages to process in one run")
    args = parser.parse_args(argv)

    adapter = (adapter_factory or (lambda spec, region: adapter_from_spec(spec, region)))(args.model, args.region)
    price = price_for(args.model)
    failures = 0
    for path in args.timing[: args.limit]:
        try:
            doc = json.loads(path.read_text())
            draft = generate_draft(doc, adapter, n=args.n, seed=args.seed, model=args.model, price=price, today=date.today().isoformat())
        except (GenerationError, AdapterError, ValueError, OSError) as error:
            failures += 1
            sys.stderr.write(f"FAILED {path.name}: {error}\n")
            continue
        args.out.mkdir(parents=True, exist_ok=True)
        target = args.out / f"{draft['passageId']}.draft.json"
        target.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n")
        sys.stdout.write(format_report(draft) + f"draft written to {target} (not served; a person must approve it)\n")
    skipped = max(len(args.timing) - args.limit, 0)
    if skipped:
        sys.stdout.write(f"\n{skipped} passage(s) skipped because of --limit {args.limit}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
