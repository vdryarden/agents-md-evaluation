"""Build and run one Harbor job covering every (agent, variant) pair.

    python -m agents_md_bench.matrix \
        --tasks tasks --variants variants \
        --agent claude-code=anthropic/claude-sonnet-5-5 \
        --agent codex=openai/gpt-5.5 \
        -k 3 -n 4 --name pilot

--tasks is a folder of local tasks or a manifest from benchmarks/ (registry tasks).
Each *.md file in --variants becomes a variant named after its stem; a "none"
variant (no instruction file at all) is added unless --no-baseline is passed.
The job config is written to <jobs-dir>/<name>.yaml, then `harbor run -c` runs it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

AGENTS = {
    "claude-code": "agents_md_bench.agents:ClaudeCodeWithInstructions",
    "codex": "agents_md_bench.agents:CodexWithInstructions",
    "nop": "agents_md_bench.agents:NopWithInstructions",
}


def build_config(args: argparse.Namespace) -> dict:
    variant_files = sorted(Path(args.variants).glob("*.md"))
    if args.only:
        variant_files = [v for v in variant_files if v.stem in args.only]
    variants: list[tuple[str, Path | None]] = [(v.stem, v.resolve()) for v in variant_files]
    if not args.no_baseline:
        variants.insert(0, ("none", None))
    if not variants:
        sys.exit(f"no variants found in {args.variants}")

    agents = []
    for spec in args.agent:
        short, _, model = spec.partition("=")
        import_path = AGENTS.get(short, short)
        for name, path in variants:
            kwargs = {"variant": name, **dict(kv.split("=", 1) for kv in args.ak)}
            if path:
                kwargs["instructions_file"] = str(path)
            agents.append(
                {
                    "name": import_path,
                    "model_name": model or None,
                    "kwargs": kwargs,
                }
            )

    return {
        "job_name": args.name,
        "jobs_dir": str(Path(args.jobs_dir).resolve()),
        "n_attempts": args.attempts,
        "n_concurrent_trials": args.concurrency,
        "environment": {"type": args.env},
        "agents": agents,
        "datasets": load_datasets(args.tasks),
    }


def load_datasets(tasks: str) -> list[dict]:
    """A folder of local tasks, or a manifest JSON whose "datasets" are Harbor dataset configs."""
    path = Path(tasks)
    if path.is_file():
        return json.loads(path.read_text())["datasets"]
    return [{"path": str(path.resolve())}]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--tasks", default="tasks",
        help="directory of Harbor tasks, or a benchmark manifest (e.g. benchmarks/swebench-pro-f12-b4.json)",
    )
    parser.add_argument("--variants", default="variants", help="directory of instruction files (*.md)")
    parser.add_argument("--only", nargs="*", help="variant stems to include (default: all)")
    parser.add_argument("--no-baseline", action="store_true", help="skip the no-file baseline")
    parser.add_argument(
        "--agent", action="append", required=True,
        help="AGENT=MODEL, AGENT is claude-code, codex, nop or an import path; repeatable",
    )
    parser.add_argument("--ak", action="append", default=[], help="extra agent kwarg key=value, repeatable")
    parser.add_argument("-k", "--attempts", type=int, default=3)
    parser.add_argument("-n", "--concurrency", type=int, default=4)
    parser.add_argument("--env", default="docker", help="harbor environment: docker, daytona, modal, ...")
    parser.add_argument("--jobs-dir", default="jobs")
    parser.add_argument("--name", default=dt.datetime.now().strftime("matrix-%Y%m%d-%H%M%S"))
    parser.add_argument("--dry-run", action="store_true", help="write the job config and stop")
    parser.add_argument("harbor_args", nargs=argparse.REMAINDER, help="passed through after --")
    args = parser.parse_args()

    config = build_config(args)
    jobs_dir = Path(args.jobs_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    config_path = jobs_dir / f"{args.name}.json"
    config_path.write_text(json.dumps(config, indent=2))
    n_variants = len({a["kwargs"]["variant"] for a in config["agents"]})
    print(
        f"{config_path}: {len(args.agent)} agent(s) x {n_variants} variant(s) "
        f"x {args.attempts} attempt(s) per task"
    )
    if args.dry_run:
        return

    env = dict(os.environ)
    root = str(Path(__file__).resolve().parent.parent)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (root, env.get("PYTHONPATH")) if p)
    extra = [a for a in args.harbor_args if a != "--"]
    sys.exit(subprocess.call(["harbor", "run", "-c", str(config_path), "-y", *extra], env=env))


if __name__ == "__main__":
    main()
