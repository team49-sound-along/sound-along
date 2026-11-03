"""The human gate. Turns a reviewed draft into the document the website may read, and is the ONLY code that writes it.

A person sets `review.status` to "approved" on each question in the draft file, then runs this. Drafts live where CloudFront cannot serve
them (`raw/` on AWS, `samples/questions/` locally); the approved file goes to `data/`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from qg_validate import validate_shape

_SAFE_ID = re.compile(r"^[0-9A-Za-z_-]+$")
_SERVED_FIELDS = ("id", "skill", "question", "choices", "answerIndex", "evidenceSentence")


def approve_draft(draft: Mapping[str, Any], today: str) -> dict[str, Any]:
    """The served document: approved questions only, with every internal field removed. Questions are checked again first."""
    approved = [q for q in draft.get("questions", []) if (q.get("review") or {}).get("status") == "approved"]
    if not approved:
        raise ValueError("no question in the draft is approved; set review.status to 'approved' on the ones you checked")
    sentence_count = int(draft["sentenceCount"])
    served: list[dict[str, Any]] = []
    for question in approved:
        _, reasons = validate_shape(question, sentence_count)
        if reasons:
            raise ValueError(f"question {question.get('id')} fails its checks: {'; '.join(reasons)}")
        served.append({field: question[field] for field in _SERVED_FIELDS})
    return {
        "version": draft.get("version", 1),
        "passageId": draft["passageId"],
        "title": draft.get("title", ""),
        "generatedWith": draft.get("generatedWith", {}),
        "reviewed": True,  # the same flag the cards documents use; generators never replace a reviewed file
        "reviewedAt": today,
        "questions": served,
    }


def approve_file(draft_path: Path, data_dir: Path, today: str) -> Path:
    draft = json.loads(Path(draft_path).read_text())
    passage_id = str(draft.get("passageId", ""))
    if not _SAFE_ID.match(passage_id):
        raise ValueError(f"unsafe passage id {passage_id!r}")
    document = approve_draft(draft, today)
    out = Path(data_dir) / f"{passage_id}.questions.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish the approved questions of a reviewed draft to the data folder.")
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--data-dir", default=Path("data"), type=Path)
    args = parser.parse_args(argv)
    try:
        out = approve_file(args.draft, args.data_dir, date.today().isoformat())
    except (ValueError, OSError, KeyError) as error:
        sys.stderr.write(f"not approved: {error}\n")
        return 1
    sys.stdout.write(f"wrote {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
