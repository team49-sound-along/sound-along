"""Merge Sound Along's `soundAlong` block into a ReadWorks product JSON (the integration path, no ReadWorks code touched).

  python scripts/merge_product_json.py product.json --data data -o product.merged.json

ReadWorks' product JSON lists capabilities in `features` (for example ["au", "hau", "qsmw"]) and references audio by id (`au`).
This adds the `soundAlong` block from `<data>/<uuid>.soundalong.json` and the feature flags it declares, leaving every other
field, including `au`, exactly as it was. See docs/FORMAT.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def merge(product: dict[str, Any], block_file: dict[str, Any]) -> dict[str, Any]:
    """Return a new product document; the input is never modified."""
    block = block_file["soundAlong"]
    if product.get("uuid") != block["passageId"]:
        raise ValueError(f"The soundAlong block is for passage {block['passageId']}, but the product JSON is {product.get('uuid')}.")
    existing = list(product.get("features") or [])
    added = [flag for flag in block_file.get("features", []) if flag not in existing]
    return {**product, "features": existing + added, "soundAlong": block}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("product", type=Path, help="a ReadWorks product JSON file")
    parser.add_argument("--data", type=Path, default=Path("data"), help="folder with <uuid>.soundalong.json files")
    parser.add_argument("-o", "--output", type=Path, help="output file (default: print to stdout)")
    args = parser.parse_args(argv)

    product = json.loads(args.product.read_text(encoding="utf-8"))
    block_path = args.data / f"{product.get('uuid')}.soundalong.json"
    if not block_path.exists():
        sys.stderr.write(f"No Sound Along block for {product.get('uuid')} in {args.data}. Generate the passage first.\n")
        return 1
    merged = merge(product, json.loads(block_path.read_text(encoding="utf-8")))
    text = json.dumps(merged, ensure_ascii=False, indent=1)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        sys.stdout.write(f"wrote {args.output}: features {merged['features']}, voices {[v['kind'] for v in merged['soundAlong']['voices']]}\n")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
