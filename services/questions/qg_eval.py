"""Judge versus human labels: does the rubric agree with a person? Run on saved questions, so no writer model is involved.

    python qg_eval.py --draft ../../samples/questions/<id>.draft.json ... --labels eval/labels_run1.json --judge-model ollama:qwen3:30b
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from qg_adapters import AdapterError, ModelAdapter, adapter_from_spec
from qg_cost import estimate_usd, price_for
from qg_passage import sentences_from_timing
from qg_rubric import judge_question

Key = tuple[str, str]


def compare(labels: Sequence[Mapping[str, Any]], judged: Mapping[Key, Mapping[str, Any]]) -> dict[str, Any]:
    confusion: dict[str, dict[str, int]] = {v: {"passed": 0, "dropped": 0} for v in ("good", "fixable", "reject")}
    bad_kept: list[dict[str, Any]] = []
    good_dropped: list[dict[str, Any]] = []
    right_reason: dict[str, bool] = {}
    missing: list[str] = []
    for label in labels:
        key = (label["passageId"], label["question"])
        outcome = judged.get(key)
        if outcome is None:
            missing.append(label["question"])
            continue
        passed = bool(outcome["passed"])
        confusion[label["verdict"]]["passed" if passed else "dropped"] += 1
        if label["verdict"] == "reject" and passed:
            bad_kept.append({"question": label["question"], "labelFailed": label["failed"], "note": label.get("note", "")})
        if label["verdict"] == "good" and not passed:
            good_dropped.append({"question": label["question"], "judgeFailed": outcome["failed"], "reasons": outcome.get("reasons", {})})
        if label["verdict"] != "good" and not passed and label["failed"]:
            right_reason[label["question"]] = bool(set(label["failed"]) & set(outcome["failed"]))
    labelled = {(label["passageId"], label["question"]) for label in labels}
    unlabelled = [question for (passage, question) in judged if (passage, question) not in labelled]
    return {"confusion": confusion, "badKept": bad_kept, "goodDropped": good_dropped, "rightReason": right_reason, "missingJudgement": missing, "unlabelled": unlabelled}


def format_comparison(report: Mapping[str, Any]) -> str:
    c = report["confusion"]
    lines = ["label      judge kept  judge dropped"]
    lines += [f"{v:9s}  {c[v]['passed']:10d}  {c[v]['dropped']:13d}" for v in ("good", "fixable", "reject")]
    lines.append(f"\nbad questions the judge kept: {len(report['badKept'])}")
    lines += [f"   - {m['question']}  (label: {', '.join(m['labelFailed'])}; {m['note']})" for m in report["badKept"]]
    lines.append(f"good questions the judge dropped: {len(report['goodDropped'])}")
    lines += [f"   - {m['question']}  (judge: {', '.join(m['judgeFailed'])}; {m['reasons']})" for m in report["goodDropped"]]
    if report["rightReason"]:
        lines.append("catches for the right reason: " + ", ".join(f"{q}={'yes' if ok else 'NO'}" for q, ok in report["rightReason"].items()))
    for name in ("missingJudgement", "unlabelled"):
        if report[name]:
            lines.append(f"{name}: {report[name]}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None, adapter_factory: Callable[[str, str], ModelAdapter] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the rubric judge on saved drafts and compare it with human labels.")
    parser.add_argument("--draft", nargs="+", required=True, type=Path)
    parser.add_argument("--timing-dir", default=Path("../../data"), type=Path, help="folder with <id>.timing.json, to rebuild the passage sentences")
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--judge-model", default="ollama:qwen3:30b")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--report", type=Path, help="optional path for the machine-readable result")
    args = parser.parse_args(argv)

    adapter = (adapter_factory or (lambda spec, region: adapter_from_spec(spec, region)))(args.judge_model, args.region)
    labels = json.loads(args.labels.read_text())["labels"]
    judged: dict[Key, dict[str, Any]] = {}
    tokens = defaultdict(int)
    started = time.monotonic()
    for path in args.draft:
        draft = json.loads(path.read_text())
        sentences = sentences_from_timing(json.loads((args.timing_dir / f"{draft['passageId']}.timing.json").read_text()))
        for question in draft["questions"]:
            try:
                result = judge_question(adapter, sentences, question)
            except AdapterError as error:
                sys.stderr.write(f"judge failed on {question['question']!r}: {error}\n")
                continue
            tokens["in"] += result.input_tokens
            tokens["out"] += result.output_tokens
            judged[(draft["passageId"], question["question"])] = {
                "passed": not result.must_pass_failed, "failed": result.must_pass_failed, "flags": result.flags, "unknown": result.unknown, "reasons": result.reasons,
            }
    report = compare(labels, judged)
    price = price_for(args.judge_model)
    cost = estimate_usd(tokens["in"], tokens["out"], price)
    sys.stdout.write(format_comparison(report))
    for (passage, question), outcome in judged.items():
        label = next((x["verdict"] for x in labels if (x["passageId"], x["question"]) == (passage, question)), "?")
        sys.stdout.write(f"\n[{label:7s}] {question}\n   judge: {'KEPT' if outcome['passed'] else 'DROPPED ' + ', '.join(outcome['failed'])}"
                         f"{'; soft flags: ' + ', '.join(outcome['flags']) if outcome['flags'] else ''}"
                         f"{'; unknown: ' + ', '.join(outcome['unknown']) if outcome['unknown'] else ''}\n")
        for name, reason in outcome["reasons"].items():
            sys.stdout.write(f"     {name}: {reason}\n")
    sys.stdout.write(f"\njudge tokens in/out: {tokens['in']}/{tokens['out']}, time: {round(time.monotonic() - started, 1)} s, "
                     f"estimated cost: {'unknown (no price for this model)' if cost is None else f'${cost:.6f}'}\n")
    if args.report:
        args.report.write_text(json.dumps({"report": report, "judged": {f"{p}::{q}": v for (p, q), v in judged.items()}}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
