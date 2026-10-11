"""Summarize Harbor trial results by (agent, model, variant).

    python -m agents_md_bench.report jobs/pilot [more job dirs] --baseline none --csv results.csv

For each variant: success rate, mean adherence, mean cost and tokens, and the
paired difference from the baseline variant on the same tasks, with a 95%
bootstrap interval over tasks. Writes per-trial rows to --csv and the summary
table (Markdown) to stdout or --out.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def _seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    parse = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (parse(end) - parse(start)).total_seconds()


def load_rows(job_dirs: list[Path]) -> list[dict]:
    rows = []
    for job_dir in job_dirs:
        for result_path in sorted(job_dir.glob("*/result.json")):
            r = json.loads(result_path.read_text())
            agent_cfg = r.get("config", {}).get("agent", {})
            kwargs = agent_cfg.get("kwargs") or {}
            rewards = (r.get("verifier_result") or {}).get("rewards") or {}
            agent_result = r.get("agent_result") or {}
            exc = r.get("exception_info")
            rows.append(
                {
                    "job": job_dir.name,
                    "trial": r.get("trial_name"),
                    "task": r.get("task_name"),
                    "agent": (r.get("agent_info") or {}).get("name") or agent_cfg.get("name"),
                    "model": agent_cfg.get("model_name") or "",
                    "variant": kwargs.get("variant")
                    or (Path(kwargs["instructions_file"]).stem if kwargs.get("instructions_file") else "none"),
                    "reward": rewards.get("reward", rewards.get("correct")),
                    "correct": rewards.get("correct", rewards.get("reward")),
                    "adherence": rewards.get("adherence"),
                    "cost_usd": agent_result.get("cost_usd"),
                    "input_tokens": agent_result.get("n_input_tokens"),
                    "output_tokens": agent_result.get("n_output_tokens"),
                    "agent_seconds": _seconds(
                        (r.get("agent_execution") or {}).get("started_at"),
                        (r.get("agent_execution") or {}).get("finished_at"),
                    ),
                    "exception": (exc or {}).get("exception_type") if isinstance(exc, dict) else (exc or ""),
                }
            )
    return rows


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def _per_task(rows: list[dict], key: str) -> dict[str, float]:
    by_task: dict[str, list] = defaultdict(list)
    for row in rows:
        # Trials that crashed count as failures for success, but not for cost/adherence.
        value = row[key]
        if value is None and key in ("reward", "correct"):
            value = 0
        by_task[row["task"]].append(value)
    return {t: m for t, vs in by_task.items() if (m := _mean(vs)) is not None}


def paired_delta(a: dict[str, float], b: dict[str, float], n_boot: int = 2000, seed: int = 0):
    tasks = sorted(set(a) & set(b))
    if not tasks:
        return None, None, None, 0
    diffs = [a[t] - b[t] for t in tasks]
    rng = random.Random(seed)
    boots = sorted(
        statistics.fmean(rng.choice(diffs) for _ in diffs) for _ in range(n_boot)
    )
    return statistics.fmean(diffs), boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot)], len(tasks)


def _fmt(value, pct: bool = False, digits: int = 2) -> str:
    if value is None:
        return "–"
    return f"{100 * value:.0f}%" if pct else f"{value:.{digits}f}"


def summarize(rows: list[dict], baseline: str) -> str:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["agent"], row["model"], row["variant"])].append(row)

    lines = [
        "| agent | model | variant | trials | errors | success | Δ success vs "
        f"{baseline} (95% CI) | adherence | Δ adherence | cost $ | out tokens | agent s |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for (agent, model, variant), grp in sorted(groups.items()):
        base = groups.get((agent, model, baseline), [])
        success = _per_task(grp, "reward")
        adherence = _per_task(grp, "adherence")
        if variant != baseline and base:
            d, lo, hi, n = paired_delta(success, _per_task(base, "reward"))
            d_success = f"{_fmt(d, True)} [{_fmt(lo, True)}, {_fmt(hi, True)}] n={n}" if d is not None else "–"
            da, *_ = paired_delta(adherence, _per_task(base, "adherence"))
            d_adh = _fmt(da, True)
        else:
            d_success = d_adh = "baseline" if variant == baseline else "–"
        lines.append(
            "| "
            + " | ".join(
                [
                    agent,
                    model or "–",
                    variant,
                    str(len(grp)),
                    str(sum(1 for r in grp if r["exception"])),
                    _fmt(_mean(success.values()), True),
                    d_success,
                    _fmt(_mean(adherence.values()), True),
                    d_adh,
                    _fmt(_mean(r["cost_usd"] for r in grp), digits=3),
                    _fmt(_mean(r["output_tokens"] for r in grp), digits=0),
                    _fmt(_mean(r["agent_seconds"] for r in grp), digits=0),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job_dirs", nargs="+", type=Path)
    parser.add_argument("--baseline", default="none", help="variant to compare against")
    parser.add_argument("--csv", type=Path, help="write per-trial rows here")
    parser.add_argument("--out", type=Path, help="write the Markdown summary here")
    args = parser.parse_args()

    rows = load_rows(args.job_dirs)
    if not rows:
        raise SystemExit("no trial results found")
    if args.csv:
        with args.csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    table = summarize(rows, args.baseline)
    if args.out:
        args.out.write_text(table + "\n")
    print(table)


if __name__ == "__main__":
    main()
