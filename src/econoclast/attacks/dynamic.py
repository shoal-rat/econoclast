"""Dynamic verification: the agent writes and runs a check we don't hardcode.

When the data is available and the paper uses a method Econoclast has no built-in
estimator for, this asks the model to write one concrete diagnostic as a Python
script, runs it, and turns the result into a finding. It is the most literal form
of "if you don't have the method, build it and verify".

This executes model-written code, so it is OFF by default and only runs with
allow_code=True (the `--allow-code` flag). It is not a sandbox: run it in a
container or a throwaway VM. A crude denylist blocks obvious file/network/shell
calls, but do not rely on it.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

from econoclast.attacks.base import Attack, AttackContext, Finding
from econoclast.attacks.designs import method_coverage
from econoclast.attacks.llm import _EPISTEMICS, _UNTRUSTED
from econoclast.llm.base import Message, extract_json
from econoclast.logging import get_logger

log = get_logger("attacks.dynamic")

_BANNED = re.compile(
    r"\b(os\.system|subprocess|popen|socket|requests|urllib|httpx|shutil\.rmtree|"
    r"os\.remove|os\.unlink|eval\s*\(|exec\s*\(|__import__|open\s*\([^)]*['\"][wa])",
    re.IGNORECASE)


class DynamicCheckAttack(Attack):
    name = "dynamic-check"
    category = "identification"
    kind = "llm"
    requires_llm = True
    description = "Write and run a diagnostic for a method Econoclast does not cover (needs data; opt-in)."

    def gate(self, ctx: AttackContext) -> bool:
        return bool(ctx.allow_code and ctx.data_path
                    and method_coverage(ctx.methods)["needs_research"])

    def run(self, ctx: AttackContext) -> list[Finding]:
        method = method_coverage(ctx.methods)["needs_research"][0]
        cols = _columns(ctx.data_path)
        system = (
            "You write ONE short, self-contained Python diagnostic. Use only pandas, numpy, statsmodels, "
            "and scipy. No file writes, no network, no shell, no imports beyond those. Read the dataset "
            "from the given path, run a single concrete check relevant to the named method, and print a "
            "JSON object to stdout and nothing else.\n\n" + _EPISTEMICS + "\n\n" + _UNTRUSTED)
        user = (
            f"Method to check: {method}. Dataset path: {ctx.data_path!r}. Columns: {cols}.\n"
            "Write a Python script that loads the data and runs ONE diagnostic that a referee would use "
            "to stress-test this method's identification (for example a placebo/permutation test, a "
            "balance or continuity check, a falsification test, or a weak-identification statistic). "
            'It must print exactly one JSON object: {"check": str, "statistic": number|null, '
            '"p_value": number|null, "concern": bool, "explanation": str}. Output ONLY the Python code.')
        try:
            resp = ctx.backend.complete("attacker",
                                        [Message(role="system", content=system), Message(role="user", content=user)])
            code = _extract_code(resp.text)
        except Exception as exc:  # noqa: BLE001
            log.warning("dynamic-check codegen failed: %s", exc)
            return []
        if not code or _BANNED.search(code):
            log.warning("dynamic-check: generated code missing or blocked by denylist; skipping.")
            return []

        result = _run_script(code)
        if not result:
            return []
        concern = bool(result.get("concern"))
        sev = "medium" if concern else "info"
        conf = 0.45 if concern else 0.2  # agent-written check: modest confidence
        title = f"Agent-run {method} check: {result.get('check', 'diagnostic')}"
        if not concern:
            title = f"Agent-run {method} check passed: {result.get('check', 'diagnostic')}"
        return [Finding(
            attack=self.name, title=title[:160], category="identification",
            severity=sev, confidence=conf,
            detail="Econoclast wrote and ran a diagnostic for a method it does not cover built-in. "
                   + str(result.get("explanation", "")),
            evidence=[f"statistic={result.get('statistic')}, p={result.get('p_value')}"],
            recommendation="Treat as a lead: re-run the authors' own pipeline before drawing conclusions.",
            data={"method": method, "result": result, "agent_generated": True})]


def _columns(path: str) -> list[str]:
    try:
        import pandas as pd

        if path.endswith(".dta"):
            return list(pd.read_stata(path, convert_categoricals=False).columns)[:40]
        return list(pd.read_csv(path, nrows=5).columns)[:40]
    except Exception:  # noqa: BLE001
        return []


def _extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else text).strip()


def _run_script(code: str, timeout: float = 120.0) -> dict | None:
    with tempfile.TemporaryDirectory() as d:
        script = Path(d) / "check.py"
        script.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, str(script)], cwd=d, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", timeout=timeout)
        except subprocess.TimeoutExpired:
            log.warning("dynamic-check script timed out")
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("dynamic-check run failed: %s", exc)
            return None
        if proc.returncode != 0:
            log.info("dynamic-check script exited %s: %s", proc.returncode, (proc.stderr or "")[-300:])
        data = extract_json(proc.stdout or "")
        return data if isinstance(data, dict) else None
