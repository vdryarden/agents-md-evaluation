"""Pick a reproducible slice of SWE-bench Pro and write it as a benchmark manifest.

    python -m agents_md_bench.swebench_pro --features 12 --bugs 4 --seed 0 \
        --out benchmarks/swebench-pro-f12-b4.json

Task types come from the `issue_specificity` labels of the Hugging Face release
(ScaleAI/SWE-bench_Pro, config v1, 731 tasks): "feature" means every label ends
in _feat, "bug" means every label ends in _bug. Mixed and enhancement tasks are
left out.

Each type's task ids are sorted, shuffled with --seed, and taken in that order,
skipping tasks whose prebuilt Docker image is larger than --max-image-gb
(compressed, as Docker Hub reports it) and anything in --exclude (tasks that
failed validation). The manifest records the seed, the skips and the sizes, so
rerunning the command with the same arguments gives the same tasks.

The manifest's "datasets" list is a Harbor dataset config (the registry's
`swebenchpro@1.0` filtered to the chosen task names), so
`python -m agents_md_bench.matrix --tasks <manifest>` runs it directly.
"""

from __future__ import annotations

import argparse
import json
import random
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HF_ROWS = "https://datasets-server.huggingface.co/rows"
HF_DATASET, HF_CONFIG, HF_SPLIT = "ScaleAI/SWE-bench_Pro", "v1", "test"
HUB_TAG = "https://hub.docker.com/v2/repositories/jefzda/sweap-images/tags/{tag}"
HARBOR_DATASET, HARBOR_VERSION = "swebenchpro", "1.0"


def _get_json(url: str, tries: int = 4) -> dict:
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == tries - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def load_rows() -> list[dict]:
    rows, offset = [], 0
    while True:
        query = urllib.parse.urlencode(
            {"dataset": HF_DATASET, "config": HF_CONFIG, "split": HF_SPLIT, "offset": offset, "length": 50}
        )
        page = _get_json(f"{HF_ROWS}?{query}")
        rows += [r["row"] for r in page["rows"]]
        offset += len(page["rows"])
        if not page["rows"] or offset >= page["num_rows_total"]:
            return rows


def task_type(row: dict) -> str | None:
    labels = json.loads(row["issue_specificity"] or "[]")
    if labels and all(label.endswith("_feat") for label in labels):
        return "feature"
    if labels and all(label.endswith("_bug") for label in labels):
        return "bug"
    return None


def image_gb(tag: str) -> float | None:
    try:
        return _get_json(HUB_TAG.format(tag=tag))["full_size"] / 1e9
    except Exception:
        return None


def pick(rows: list[dict], kind: str, n: int, args: argparse.Namespace, skipped: list[dict]) -> list[dict]:
    pool = sorted((r for r in rows if task_type(r) == kind), key=lambda r: r["instance_id"])
    random.Random(f"{args.seed}:{kind}").shuffle(pool)
    chosen = []
    for row in pool:
        if len(chosen) == n:
            break
        name = row["instance_id"].lower()  # Harbor's registry uses lowercased ids
        if name in args.exclude:
            skipped.append({"task": name, "type": kind, "reason": args.exclude[name]})
            continue
        size = image_gb(row["dockerhub_tag"])
        if size is None or size > args.max_image_gb:
            reason = "image size unknown" if size is None else f"image {size:.2f} GB > {args.max_image_gb} GB"
            skipped.append({"task": name, "type": kind, "reason": reason})
            continue
        chosen.append(
            {
                "task": name,
                "type": kind,
                "repo": row["repo"],
                "language": row["repo_language"],
                "issue_specificity": json.loads(row["issue_specificity"]),
                "image_gb": round(size, 2),
            }
        )
    if len(chosen) < n:
        sys.exit(f"only {len(chosen)} {kind} tasks qualify, wanted {n}")
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--features", type=int, default=12)
    parser.add_argument("--bugs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-image-gb", type=float, default=1.5, help="compressed Docker image size cap")
    parser.add_argument(
        "--exclude", action="append", default=[], metavar="TASK=REASON",
        help="skip a task (e.g. it failed validation); repeatable",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.exclude = dict(e.partition("=")[::2] for e in args.exclude)

    rows = load_rows()
    skipped: list[dict] = []
    tasks = pick(rows, "feature", args.features, args, skipped) + pick(rows, "bug", args.bugs, args, skipped)
    manifest = {
        "description": f"SWE-bench Pro: {args.features} feature-only + {args.bugs} bug-only tasks",
        "selection": {
            "source": f"{HF_DATASET} ({HF_CONFIG}, {len(rows)} tasks), issue_specificity labels",
            "command": shlex.join(["python", "-m", "agents_md_bench.swebench_pro", *sys.argv[1:]]),
            "seed": args.seed,
            "max_image_gb": args.max_image_gb,
            "skipped": skipped,
        },
        "datasets": [
            {"name": HARBOR_DATASET, "version": HARBOR_VERSION, "task_names": [t["task"] for t in tasks]}
        ],
        "tasks": tasks,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{args.out}: {len(tasks)} tasks, {len(skipped)} skipped")


if __name__ == "__main__":
    main()
