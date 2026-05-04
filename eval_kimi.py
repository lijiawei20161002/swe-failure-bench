#!/usr/bin/env python3
"""
Kimi eval script for swe-failure-bench.

Runs Kimi (kimi-for-coding) as the coding agent on each task,
records full trajectories, and prints a pass/fail summary.

Usage:
    export KIMI_API_KEY=sk-...
    python3 eval_kimi.py                      # all tasks
    python3 eval_kimi.py --task task_02_connection_pool
    python3 eval_kimi.py --max-turns 25
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ── config ────────────────────────────────────────────────────────────────────

KIMI_KEY = os.environ.get("KIMI_API_KEY", "")
if not KIMI_KEY:
    print("Error: set KIMI_API_KEY environment variable before running.", file=sys.stderr)
    sys.exit(1)

KIMI_BASE = "https://api.kimi.com/coding/v1"
KIMI_MODEL = "kimi-for-coding"
KIMI_HEADERS = {
    "Authorization": f"Bearer {KIMI_KEY}",
    "User-Agent": "claude-code/1.0",
    "Content-Type": "application/json",
}

BENCH_DIR = Path(__file__).parent
SEEDS_DIR = BENCH_DIR / "seeds"
TRAJ_DIR  = BENCH_DIR / "trajectories"

DEFAULT_MAX_TURNS = 30

# ── tools ─────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to the workspace root"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Execute a shell command in the workspace directory. Use this to run tests, list files, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to run"
                    }
                },
                "required": ["command"]
            }
        }
    }
]

# ── API call ──────────────────────────────────────────────────────────────────

def call_kimi(messages: list[dict], retries: int = 3) -> dict:
    payload = {
        "model": KIMI_MODEL,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }
    for attempt in range(retries):
        try:
            resp = requests.post(
                f"{KIMI_BASE}/chat/completions",
                headers=KIMI_HEADERS,
                json=payload,
                timeout=360,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            status = e.response.status_code if e.response else 0
            body = e.response.text if e.response else str(e)
            print(f"    HTTP error (attempt {attempt+1}): {status} {body[:200]}")
            if attempt == retries - 1:
                raise
            if status == 429:
                # Honour Retry-After header, minimum 60s
                retry_after = int(e.response.headers.get("Retry-After", 60))
                wait = max(retry_after, 60)
                print(f"    Rate limited — waiting {wait}s (Retry-After={retry_after}s)...")
                time.sleep(wait)
            else:
                time.sleep(5 * (attempt + 1))
        except requests.Timeout:
            print(f"    Timeout (attempt {attempt+1})")
            if attempt == retries - 1:
                raise
            time.sleep(15 * (attempt + 1))

# ── tool executor ─────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict, workspace: Path) -> str:
    if name == "read_file":
        path = workspace / args["path"]
        try:
            return path.read_text()
        except FileNotFoundError:
            return f"Error: file not found: {args['path']}"
        except Exception as e:
            return f"Error reading {args['path']}: {e}"

    elif name == "write_file":
        path = workspace / args["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"])
        return f"OK: wrote {len(args['content'])} bytes to {args['path']}"

    elif name == "run_bash":
        try:
            result = subprocess.run(
                args["command"],
                shell=True,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=90,
            )
            out = (result.stdout + result.stderr).strip()
            return out[-4000:] if len(out) > 4000 else out  # keep last 4k chars
        except subprocess.TimeoutExpired:
            return "Error: command timed out after 90s"
        except Exception as e:
            return f"Error: {e}"

    return f"Error: unknown tool '{name}'"

# ── workspace setup ───────────────────────────────────────────────────────────

def setup_workspace(seed_dir: Path, workspace: Path) -> None:
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(seed_dir, workspace)

def list_workspace_files(workspace: Path) -> list[str]:
    skip = {"__pycache__", ".pytest_cache", ".DS_Store", "__init__.py"}
    files = []
    for f in sorted(workspace.rglob("*")):
        if f.is_file() and not any(p in str(f) for p in skip):
            files.append(str(f.relative_to(workspace)))
    return files

def run_tests(workspace: Path, task_name: str) -> tuple[bool, str]:
    """Return (passed, output)."""
    extra_install = "pytest pytest-asyncio" if "async" in task_name else "pytest"
    install_cmd = f"pip install {extra_install} --quiet 2>/dev/null"
    subprocess.run(install_cmd, shell=True, cwd=workspace, capture_output=True)

    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/", "-v", "--tb=short", "-q"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output

# ── task evaluation ────────────────────────────────────────────────────────────

def build_initial_prompt(seed_dir: Path) -> str:
    """Build the opening user message showing seed code + tests."""
    impl_files = sorted([
        f for f in seed_dir.rglob("*.py")
        if f.is_file()
        and "tests/" not in str(f.relative_to(seed_dir))
        and "__" not in f.name
        and ".pytest_cache" not in str(f)
    ])
    test_files = sorted([
        f for f in seed_dir.rglob("test_*.py")
        if ".pytest_cache" not in str(f)
    ])

    parts = ["Here is the buggy implementation that needs fixing:\n"]
    for f in impl_files:
        rel = f.relative_to(seed_dir)
        parts.append(f"**{rel}**\n```python\n{f.read_text()}\n```\n")

    parts.append("\nHere are the tests that must all pass:\n")
    for f in test_files:
        rel = f.relative_to(seed_dir)
        parts.append(f"**{rel}**\n```python\n{f.read_text()}\n```\n")

    parts.append(
        "\nPlease fix all bugs in the implementation file(s) so that "
        "`python3 -m pytest tests/ -v` exits with return code 0.\n"
        "Start by running the tests to see the current failures."
    )
    return "\n".join(parts)


def eval_task(task_name: str, seed_dir: Path, max_turns: int) -> dict:
    print(f"\n{'='*62}")
    print(f"  TASK: {task_name}")
    print(f"{'='*62}")

    # Workspace
    workspace = TRAJ_DIR / "workspaces" / task_name
    setup_workspace(seed_dir, workspace)

    system_prompt = (
        "You are an expert Python engineer fixing bugs in a codebase. "
        "You have tools to read files, write files, and run shell commands. "
        "Fix ALL bugs so that the full pytest suite passes. "
        "Run the tests after each round of edits to verify. "
        "Only edit the implementation files — never edit the test files."
    )

    initial_user = build_initial_prompt(seed_dir)

    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": initial_user},
    ]

    trajectory = {
        "task":       task_name,
        "start_time": datetime.now().isoformat(),
        "model":      KIMI_MODEL,
        "turns":      [],
        "passed":     False,
        "pass_turn":  None,
        "total_turns": 0,
    }

    passed = False
    total_api_calls = 0

    for turn_idx in range(max_turns):
        print(f"  turn {turn_idx+1:2d}", end=" ", flush=True)

        # Call Kimi
        try:
            response = call_kimi(messages)
            total_api_calls += 1
        except Exception as e:
            print(f"→ API ERROR: {e}")
            break

        choice = response["choices"][0]
        msg = choice["message"]
        finish = choice.get("finish_reason", "?")

        reasoning = msg.get("reasoning_content", "")
        content   = msg.get("content") or ""
        tool_calls = msg.get("tool_calls") or []

        turn_record = {
            "turn": turn_idx + 1,
            "finish_reason": finish,
            "reasoning_length": len(reasoning),
            "content": content,
            "tool_calls": [],
            "tool_results": [],
        }

        # Kimi requires reasoning_content to be echoed back in history
        assistant_msg: dict = {
            "role": "assistant",
            "content": content,
            "reasoning_content": reasoning,
        }
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        if tool_calls:
            tool_names = [tc["function"]["name"] for tc in tool_calls]
            print(f"→ {', '.join(tool_names)}", end=" ", flush=True)

            tool_msgs = []
            wrote_files = False
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    fn_args = {}

                result = execute_tool(fn_name, fn_args, workspace)
                if fn_name == "write_file":
                    wrote_files = True

                turn_record["tool_calls"].append({
                    "name": fn_name,
                    "args": {k: v[:200] if isinstance(v, str) else v for k, v in fn_args.items()},
                })
                turn_record["tool_results"].append({
                    "name": fn_name,
                    "result_preview": result[:400],
                })

                tool_msgs.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

            messages.extend(tool_msgs)

            # Auto-check after writes
            if wrote_files:
                passed, test_out = run_tests(workspace, task_name)
                turn_record["test_run"] = {
                    "passed": passed,
                    "output_tail": test_out[-800:],
                }
                if passed:
                    print(f"→ ✓ PASSED")
                    trajectory["passed"] = True
                    trajectory["pass_turn"] = turn_idx + 1
                    trajectory["turns"].append(turn_record)
                    break
                else:
                    # Count failing tests
                    import re
                    m = re.search(r"(\d+) failed", test_out)
                    fail_n = m.group(1) if m else "?"
                    print(f"→ {fail_n} tests still failing")
            else:
                print()

        else:
            # No tool calls — model finished without passing tests
            print(f"→ no tool calls (finish={finish})")
            # Final check
            passed, test_out = run_tests(workspace, task_name)
            turn_record["test_run"] = {"passed": passed, "output_tail": test_out[-800:]}
            if passed:
                trajectory["passed"] = True
                trajectory["pass_turn"] = turn_idx + 1
                print(f"  ✓ PASSED (tests were already passing)")
            else:
                print(f"  ✗ Model stopped without passing tests")
            trajectory["turns"].append(turn_record)
            break

        trajectory["turns"].append(turn_record)

    trajectory["total_turns"] = len(trajectory["turns"])
    trajectory["total_api_calls"] = total_api_calls
    trajectory["end_time"] = datetime.now().isoformat()

    # Final verdict
    if not trajectory["passed"]:
        passed, final_out = run_tests(workspace, task_name)
        trajectory["final_test_output"] = final_out[-800:]
        if passed:
            trajectory["passed"] = True
            trajectory["pass_turn"] = trajectory["total_turns"]

    status = "✓ PASSED" if trajectory["passed"] else "✗ FAILED"
    print(f"  {status}  ({trajectory['total_turns']} turns, {total_api_calls} API calls)")

    # Save trajectory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    traj_path = TRAJ_DIR / f"{task_name}_{ts}.json"
    traj_path.write_text(json.dumps(trajectory, indent=2, ensure_ascii=False))
    print(f"  → saved: {traj_path.name}")

    return trajectory

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Evaluate Kimi on swe-failure-bench")
    parser.add_argument("--task", help="Run only this task (seed dir name)")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    args = parser.parse_args()

    TRAJ_DIR.mkdir(parents=True, exist_ok=True)

    # Collect tasks
    if args.task:
        task_dirs = [SEEDS_DIR / args.task]
        if not task_dirs[0].exists():
            print(f"Task not found: {args.task}")
            sys.exit(1)
    else:
        task_dirs = sorted([
            d for d in SEEDS_DIR.iterdir()
            if d.is_dir() and (d / "tests").exists()
        ])

    print(f"Running {len(task_dirs)} task(s) | max_turns={args.max_turns} | model={KIMI_MODEL}")

    results: dict[str, bool] = {}
    for i, td in enumerate(task_dirs):
        if i > 0:
            time.sleep(5)   # brief pause between tasks to avoid rate limits
        traj = eval_task(td.name, td, args.max_turns)
        results[td.name] = traj["passed"]

    # Summary
    passed_count = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n{'='*62}")
    print("FINAL RESULTS")
    print(f"{'='*62}")
    for task, ok in results.items():
        mark = "✓" if ok else "✗"
        print(f"  {mark}  {task}")
    pct = 100 * passed_count / total if total else 0
    print(f"\n  Pass rate: {passed_count}/{total} = {pct:.0f}%")
    print(f"{'='*62}\n")

    summary = {
        "timestamp":   datetime.now().isoformat(),
        "model":       KIMI_MODEL,
        "max_turns":   args.max_turns,
        "results":     results,
        "passed":      passed_count,
        "total":       total,
        "pass_rate":   passed_count / total if total else 0,
    }
    (TRAJ_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Summary saved to trajectories/summary.json")


if __name__ == "__main__":
    main()
