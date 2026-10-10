# agents-md-evaluation

Runs coding agents on a set of [Harbor](https://github.com/laude-institute/harbor) tasks once per instruction file (AGENTS.md / CLAUDE.md variant), then compares success, rule-following and cost against a no-file baseline.

## How it works

- **Tasks** (`tasks/`) are ordinary Harbor tasks: `instruction.md`, `environment/Dockerfile` with the repo, `tests/test.sh` as the hidden grader, `solution/solve.sh`. The grader writes `/logs/verifier/reward.json` with `reward` (0/1, the hidden functional tests), `correct` (same) and `adherence` (0 to 1, share of convention checks passed).
- **Variants** (`variants/*.md`) are your instruction files. Each file's name, minus `.md`, becomes its variant name. A `none` variant (no file at all) is added as the baseline. Keep `placebo.md`, a file of similar length with no useful content, so you can tell content effects from length effects.
- **Agents** (`agents_md_bench/agents.py`) wrap Harbor's built-in agents. Before the agent starts they delete any AGENTS.md / CLAUDE.md already in the repo, write the variant into the working directory (`CLAUDE.md` for Claude Code, `AGENTS.md` for Codex, configurable with `--ak instructions_targets=...`), hide it from `git status`, and record the variant and its hash in `agent/instructions.json` for the trial.
- **Matrix** (`python -m agents_md_bench.matrix`) writes one Harbor job config covering every agent x variant pair and runs it, so all runs share one queue. `--tasks` takes a folder of local tasks or a manifest from `benchmarks/` that points at registry tasks.
- **Report** (`python -m agents_md_bench.report`) aggregates trial results into a table with success, adherence, cost, tokens and time per variant, plus the paired difference from the baseline across the same tasks with a 95% bootstrap interval.

## Quick start

```bash
uv tool install harbor==0.24.0          # or: pip install -e .
export ANTHROPIC_API_KEY=...            # and/or OPENAI_API_KEY for codex

# Check a task: its reference solution should pass, the do-nothing agent should fail.
PYTHONPATH=. harbor run -p tasks/textkit-add-slugify \
  -a agents_md_bench.agents:ScriptWithInstructions \
  --ak script=tasks/textkit-add-slugify/solution/solve.sh \
  --ak instructions_file=variants/textkit-conventions.md
python -m agents_md_bench.matrix --agent nop -k 1 --name sanity

# Real run: every variant in variants/ plus "none", 3 attempts per task.
python -m agents_md_bench.matrix \
  --agent claude-code=anthropic/claude-sonnet-5-5 \
  --agent codex=openai/<model> \
  -k 3 -n 8 --name pilot

python -m agents_md_bench.report jobs/pilot --csv jobs/pilot.csv
harbor view jobs        # browse trajectories in Harbor's viewer
```

Useful options: `--only conventions placebo` runs a subset of variants, `--env daytona` (or `modal`, `e2b`, ...) runs in cloud sandboxes for more parallelism, `--ak max_turns=50` and `--ak strip_existing=false` pass agent options, and anything after `--` goes straight to `harbor run`.

## Adding tasks

`harbor task init <org>/<name> --no-package -p tasks` scaffolds one. For tasks that should react to instruction files:

1. Put a snapshot of one of your repos in `environment/` (copy it, or `git clone` at a pinned commit in the Dockerfile) and `git init` / commit it, as the example does.
2. Write `instruction.md` as a user would phrase the request, without restating the conventions. Those belong in the variants.
3. In `tests/`, split checks into `test_correct_*` (does it work) and `test_adherence_*` (did it follow the rules the variants describe). The example's `score.py` turns that into `reward.json`.
4. Write `solution/solve.sh` and confirm it scores 1 / 1.0 with `ScriptWithInstructions`, and that `nop` scores 0.

A good mix is convention tasks (like the example), plain bug fixes mined from merged PRs with tests (revert the fix, keep its tests as the grader), and a slice of an existing dataset as a "does this file hurt" check (see the SWE-bench Pro slice below).

## SWE-bench Pro slice

`benchmarks/swebench-pro-f12-b4.json` is a fixed set of 16 real tasks from SWE-bench Pro: 12 feature-only and 4 bug-only. Task types come from the `issue_specificity` labels of the Hugging Face release (`ScaleAI/SWE-bench_Pro`, `v1`): feature-only means every label ends in `_feat`, bug-only means every label ends in `_bug`. The tasks run from Harbor's registry (`swebenchpro@1.0`), using SWE-bench Pro's prebuilt Docker images, and score 0/1 on the task's hidden tests (no adherence score, since these repos have no house rules for a file to teach). Use it as the "does this file help or hurt on ordinary work" check next to your convention tasks.

```bash
python -m agents_md_bench.matrix --tasks benchmarks/swebench-pro-f12-b4.json \
  --agent claude-code=anthropic/claude-sonnet-5-5 -k 3 -n 2 --name pro16
```

The manifest was made with `python -m agents_md_bench.swebench_pro --features 12 --bugs 4 --seed 0 --out benchmarks/swebench-pro-f12-b4.json`, which shuffles each type's task ids with the seed and takes them in order, skipping images over 1.5 GB compressed so they fit a small machine. The manifest lists every task with its repo, language, labels and image size, and the ones skipped and why. Rerun it with a different `--seed` or counts to draw a new slice, and `--exclude TASK=REASON` to drop a task that fails validation.

Each image is 0.5 to 1.4 GB compressed and a few GB unpacked, so with Docker's default storage expect to need about 40 GB free for all 16 at once, or prune images between tasks. Trials are long (real repos, full test files), so budget accordingly before a paid run.

## Reading the results

- Run at least 3 attempts per task. Agents are noisy, and a single run can mislead.
- A difference whose interval includes 0% isn't evidence of a difference yet. Add tasks before trusting it.
- Compare against `placebo` as well as `none`: if a variant beats `none` but not `placebo`, its content isn't what helped.
- Read failing trajectories (`harbor view jobs`) to see whether the agent read the file and ignored it or never saw it.

## Notes

- Claude Code is pointed at `CLAUDE.md` by default and Codex at `AGENTS.md`. If your Claude Code version also reads `AGENTS.md`, set `--ak instructions_targets=CLAUDE.md` to make sure it gets one copy, not two.
- Pin the agent CLI version (`--ak version=...`) and the model for runs you'll compare. Results drift otherwise.
- `jobs/` is git-ignored; keep result CSVs you care about elsewhere.
