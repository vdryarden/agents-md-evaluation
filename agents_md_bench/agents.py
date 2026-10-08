"""Harbor agents that run with a chosen instruction file in the task's working directory.

Usage:
    harbor run -p tasks/ \
        -a agents_md_bench.agents:ClaudeCodeWithInstructions -m anthropic/<model> \
        --ak instructions_file=variants/conventions.md --ak variant=conventions

Agent kwargs added by InstructionFileMixin:
    instructions_file   Host path of the file to install. Omit for the "no file" baseline.
    variant             Label recorded with the trial (default: file stem, or "none").
    instructions_targets
                        Comma-separated filenames to write in the workdir. Defaults per
                        agent: CLAUDE.md for Claude Code, AGENTS.md for everything else.
    strip_existing      "true" (default) deletes every AGENTS.md / CLAUDE.md already in
                        the repo first, so only the variant under test is visible.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path
from typing import Any, Mapping

from harbor.agents.installed.claude_code import ClaudeCode
from harbor.agents.installed.codex import Codex
from harbor.agents.base import BaseAgent
from harbor.agents.capabilities import AgentCapabilities
from harbor.agents.nop import NopAgent
from harbor.models.agent.context import AgentContext
from harbor.environments.base import BaseEnvironment

_MIXIN_KWARGS = ("instructions_file", "instructions_targets", "strip_existing", "variant")
_KNOWN_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", "AGENTS.override.md")


def _truthy(value: Any) -> bool:
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


class InstructionFileMixin:
    """Installs one instruction-file variant into the workdir during agent setup."""

    default_instruction_targets: tuple[str, ...] = ("AGENTS.md",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        file = kwargs.pop("instructions_file", None)
        self.instructions_file = Path(file).expanduser().resolve() if file else None
        if self.instructions_file and not self.instructions_file.is_file():
            raise FileNotFoundError(f"instructions_file not found: {self.instructions_file}")
        targets = kwargs.pop("instructions_targets", None)
        self.instruction_targets = (
            tuple(t.strip() for t in targets.split(",") if t.strip())
            if targets
            else self.default_instruction_targets
        )
        self.strip_existing = _truthy(kwargs.pop("strip_existing", "true"))
        self.variant = kwargs.pop("variant", None) or (
            self.instructions_file.stem if self.instructions_file else "none"
        )
        super().__init__(*args, **kwargs)

    @classmethod
    def parse_options(
        cls, kwargs: dict[str, Any] | None = None, env: Mapping[str, str] | None = None
    ):
        rest = {k: v for k, v in (kwargs or {}).items() if k not in _MIXIN_KWARGS}
        return super().parse_options(rest, env)  # type: ignore[misc]

    async def setup(self, environment: BaseEnvironment) -> None:
        await super().setup(environment)  # type: ignore[misc]
        await self._install_instruction_file(environment)

    async def _install_instruction_file(self, environment: BaseEnvironment) -> None:
        workdir = (await environment.exec(command="pwd")).stdout.strip() or "/app"

        removed: list[str] = []
        if self.strip_existing:
            names = " -o ".join(f"-name {shlex.quote(n)}" for n in _KNOWN_INSTRUCTION_FILES)
            result = await environment.exec(
                command=(
                    f"find {shlex.quote(workdir)} -not -path '*/.git/*' "
                    f"\\( {names} \\) -type f -print -delete 2>/dev/null"
                ),
                user="root",
            )
            removed = [line for line in (result.stdout or "").splitlines() if line]

        installed: list[str] = []
        sha256 = None
        if self.instructions_file:
            content = self.instructions_file.read_bytes()
            sha256 = hashlib.sha256(content).hexdigest()
            for name in self.instruction_targets:
                target = f"{workdir.rstrip('/')}/{name}"
                await environment.upload_file(self.instructions_file, target)
                await environment.exec(command=f"chmod a+r {shlex.quote(target)}", user="root")
                installed.append(target)
            # Keep the injected file out of `git status` / `git diff`, so the agent
            # doesn't treat it as its own change and diffs stay comparable.
            excludes = " ".join(shlex.quote(f"/{n}") for n in self.instruction_targets)
            await environment.exec(
                command=(
                    f"cd {shlex.quote(workdir)} && [ -d .git ] && "
                    f"printf '%s\\n' {excludes} >> .git/info/exclude || true"
                ),
                user="root",
            )

        record = {
            "variant": self.variant,
            "instructions_file": str(self.instructions_file) if self.instructions_file else None,
            "sha256": sha256,
            "bytes": self.instructions_file.stat().st_size if self.instructions_file else 0,
            "workdir": workdir,
            "installed": installed,
            "removed_existing": removed,
        }
        logs_dir: Path = self.logs_dir  # type: ignore[attr-defined]
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "instructions.json").write_text(json.dumps(record, indent=2))


class ClaudeCodeWithInstructions(InstructionFileMixin, ClaudeCode):
    default_instruction_targets = ("CLAUDE.md",)


class CodexWithInstructions(InstructionFileMixin, Codex):
    default_instruction_targets = ("AGENTS.md",)


class ScriptAgent(BaseAgent):
    """Runs a host shell script in the workdir (``--ak script=path``), like Harbor's oracle.

    Harbor only hands the task directory to its built-in oracle, so this lets the
    benchmark smoke-test a task's solution together with instruction-file injection.
    """

    capabilities = AgentCapabilities()

    def __init__(self, *args: Any, script: str | None = None, **kwargs: Any) -> None:
        if not script:
            raise ValueError("ScriptAgent needs --ak script=<path to solve.sh>")
        self.script = Path(script).expanduser().resolve()
        super().__init__(*args, **kwargs)

    @staticmethod
    def name() -> str:
        return "script"

    def version(self) -> str:
        return "1.0.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        pass

    async def run(
        self, instruction: str, environment: BaseEnvironment, context: AgentContext
    ) -> None:
        await environment.upload_file(self.script, "/tmp/agents_md_bench_solve.sh")
        result = await environment.exec(command="bash /tmp/agents_md_bench_solve.sh")
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "script.txt").write_text(
            f"exit={result.return_code}\n{result.stdout or ''}\n{result.stderr or ''}"
        )


class ScriptWithInstructions(InstructionFileMixin, ScriptAgent):
    """Runs a task's reference solution; used to smoke-test tasks and injection."""


class NopWithInstructions(InstructionFileMixin, NopAgent):
    """Does nothing; the verifier should score 0. Checks tasks aren't trivially passing."""
