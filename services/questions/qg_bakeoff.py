"""Compare several models on the same passages, with the same checks, and print one table.

The table holds only what code can measure (questions kept, why others were dropped, tokens, time, cost). Whether the kept questions are GOOD is
still decided by a person reading them, so every model's drafts are written to their own folder for that.

    python qg_bakeoff.py --timing ../../data/<id>.timing.json ... --region us-west-2
    python qg_bakeoff.py --timing ... --models bedrock:us.amazon.nova-lite-v1:0 --no-schema      # Nova without schema mode, to see what it adds
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from qg_adapters import AdapterError, BedrockAdapter, ModelAdapter, adapter_from_spec
from qg_cost import estimate_usd, price_for
from qg_pipeline import GenerationError, generate_draft

# Plain in-region ids for us-west-2 (they need no cross-region permissions). If a model is only offered through an inference profile, pass
# the "us." form with --models. Check each id in the Bedrock console (Model access) before the run.
DEFAULT_MODELS = (
    "bedrock:amazon.nova-lite-v1:0",
    "bedrock:amazon.nova-pro-v1:0",
    "bedrock:meta.llama4-maverick-17b-instruct-v1:0",
)
DEFAULT_LIMIT = 3


def summarize(model: str, drafts: Sequence[Mapping[str, Any]], failures: Sequence[str], passages: int) -> dict[str, Any]:
    """One row of the table. Cost is None when the price is unknown."""
    questions = [q for d in drafts for q in d["questions"]]
    dropped = [item for d in drafts for item in d["dropped"]]
    metrics = [d["metrics"] for d in drafts]
    tokens_in, tokens_out = sum(m["inputTokens"] for m in metrics), sum(m["outputTokens"] for m in metrics)
    cost = estimate_usd(tokens_in, tokens_out, price_for(model))
    done = len(drafts)
    return {
        "model": model,
        "passages": passages,
        "passagesFailed": len(failures),
        "failures": list(failures),
        "kept": len(questions),
        "dropped": len(dropped),
        "droppedQuoteNotFound": sum(any("quote" in r for r in item["reasons"]) for item in dropped),
        "droppedCouldNotAnswer": sum(any("could not answer" in r for r in item["reasons"]) for item in dropped),
        "droppedOther": sum(not any("quote" in r or "could not answer" in r for r in item["reasons"]) for item in dropped),
        "guessableFlagged": sum(bool(q["checks"]["guessableWithoutPassage"]) for q in questions),
        "evidenceCorrected": sum(bool(q.get("evidenceCorrected")) for q in questions),
        "inputTokens": tokens_in,
        "outputTokens": tokens_out,
        "seconds": round(sum(m["seconds"] for m in metrics), 1),
        "costUsd": None if cost is None else round(cost, 6),
        "costPerPassageUsd": None if cost is None or not done else round(cost / done, 6),
    }


def format_table(rows: Sequence[Mapping[str, Any]]) -> str:
    head = ["model", "ok/total", "kept", "dropped (quote / no answer / other)", "guessable", "tokens in/out", "seconds", "$ per passage"]
    body = [
        [
            r["model"],
            f"{r['passages'] - r['passagesFailed']}/{r['passages']}",
            str(r["kept"]),
            f"{r['dropped']} ({r['droppedQuoteNotFound']} / {r['droppedCouldNotAnswer']} / {r['droppedOther']})",
            str(r["guessableFlagged"]),
            f"{r['inputTokens']}/{r['outputTokens']}",
            str(r["seconds"]),
            "unknown" if r["costPerPassageUsd"] is None else f"{r['costPerPassageUsd']:.5f}",
        ]
        for r in rows
    ]
    widths = [max(len(row[i]) for row in [head, *body]) for i in range(len(head))]
    line = lambda row: "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))  # noqa: E731
    out = [line(head), line(["-" * w for w in widths]), *map(line, body)]
    for r in rows:
        out.extend(f"FAILED ({r['model']}): {f}" for f in r["failures"])
    out.append("\nKept does not mean good. Read each model's drafts and mark good / fixable / reject before choosing.")
    return "\n".join(out) + "\n"


def _folder(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def run_model(model: str, adapter: ModelAdapter, timings: Sequence[Path], out: Path, n: int, seed: int) -> dict[str, Any]:
    drafts: list[dict[str, Any]] = []
    failures: list[str] = []
    for path in timings:
        try:
            doc = json.loads(path.read_text())
            draft = generate_draft(doc, adapter, n=n, seed=seed, model=model, price=price_for(model), today=date.today().isoformat())
        except (GenerationError, AdapterError, ValueError, OSError) as error:
            failures.append(f"{path.name}: {error}")
            continue
        target = out / _folder(model) / f"{draft['passageId']}.draft.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n")
        drafts.append(draft)
    return summarize(model, drafts, failures, len(timings))


def main(argv: Sequence[str] | None = None, adapter_factory: Callable[[str, str], ModelAdapter] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the question pipeline with several models on the same passages and compare them.")
    parser.add_argument("--timing", nargs="+", required=True, type=Path)
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--out", default=Path("samples/bakeoff"), type=Path, help="drafts go here, one folder per model (never a served folder)")
    parser.add_argument("--n", default=4, type=int)
    parser.add_argument("--seed", default=7, type=int)
    parser.add_argument("--limit", default=DEFAULT_LIMIT, type=int, help="most passages per model (a hard cap on spend)")
    parser.add_argument("--no-schema", action="store_true", help="ask Nova in words only, without the tool-schema mode")
    args = parser.parse_args(argv)

    make = adapter_factory or (lambda spec, region: adapter_from_spec(spec, region))
    timings = args.timing[: args.limit]
    rows = []
    for model in args.models:
        adapter = make(model, args.region)
        if args.no_schema and isinstance(adapter, BedrockAdapter):
            adapter.use_schema = False
        rows.append(run_model(model, adapter, timings, args.out, args.n, args.seed))
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "bakeoff.summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    sys.stdout.write(format_table(rows))
    return 1 if any(r["passagesFailed"] for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
