#!/usr/bin/env python3
"""
Ultimate Local Code Improvement Agent (Ollama)
------------------------------------------------
Features:
- Animated 2D Pixel AI Employee in Gradio 6 UI
- Multi-file safe apply (with confirmation)
- Automatic git branch + commit
- Create GitHub Pull Request (gh)
- Run tests before/after
- Export .patch file
- Dry-run mode
- Chunked reading for large files
"""

import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
from openai import OpenAI

# ====================== CONFIG ======================
MODEL = "qwen2.5-coder:14b"                  # ← change to your model
OLLAMA_BASE_URL = "http://localhost:11434/v1"
DRY_RUN = False                              # True = never write files

client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama", timeout=60.0)

MAX_CHARS_FULL_READ = 8_000
MAX_CHUNK_LINES = 120
IGNORE_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv", "dist",
               "build", ".next", "target", ".idea", ".vscode", "coverage", ".tox"}
SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs",
                        ".java", ".cpp", ".c", ".h", ".rb", ".php", ".svelte", ".vue",
                        ".tf", ".tfvars", ".yaml", ".yml"}

PLACEHOLDER_PATTERNS = (
    "<proposed-changes>",
    "<your-code-here>",
    "<insert-code>",
    "TODO: replace with actual",
)

TOOL_ALIASES = {
    "list_repo_files": "list_files",
    "lint": "run_linter",
    "run_lint": "run_linter",
    "git_status": "get_git_status",
    "project_structure": "get_project_structure",
}

# ====================== LOW-LEVEL HELPERS ======================

def run_cmd(cmd: str, cwd: str = ".") -> str:
    blocked = ("git push", "gh pr create")
    if any(b in cmd for b in blocked):
        return f"Blocked '{cmd}': remote push/PR commands are disabled in automatic shell execution."

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (result.stdout + result.stderr).strip()
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after 30s: {cmd}"
    except Exception as e:
        return f"Error: {e}"

def is_git_repo() -> bool:
    return run_cmd("git rev-parse --is-inside-work-tree 2>/dev/null").strip() == "true"

def _suggest_matching_paths(target: str) -> List[str]:
    clean = target.lstrip("./")
    stem = Path(clean).name.lower()
    matches = []
    for path in Path(".").rglob("*"):
        if not path.is_file():
            continue
        if any(p in IGNORE_DIRS for p in path.parts):
            continue
        rel = str(path).lstrip("./")
        if stem and (stem in rel.lower() or path.suffix.lower() in {".tf", ".yaml", ".yml"}):
            matches.append(rel)
    return sorted(matches)[:15]

def _missing_path_message(path: str) -> str:
    suggestions = _suggest_matching_paths(path)
    hint = ""
    if suggestions:
        hint = " Matching/infra files in repo:\n- " + "\n- ".join(suggestions)
    return f"Error: '{path}' does not exist. Call list_files or get_project_structure to get exact paths.{hint}"

# ====================== TOOLS ======================

def list_repo_files() -> List[str]:
    files = []
    for path in Path(".").rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            if any(p in IGNORE_DIRS for p in path.parts):
                continue
            files.append(str(path).lstrip("./"))
    return sorted(files)[:300]

def read_file(path: str) -> str:
    try:
        p = Path(path)
        if p.is_dir():
            return f"Error: '{path}' is a directory, not a file. Use list_files or get_project_structure."
        if not p.exists():
            return _missing_path_message(path)
        content = p.read_text(encoding="utf-8", errors="ignore")
        if len(content) > MAX_CHARS_FULL_READ:
            return (content[:MAX_CHARS_FULL_READ] +
                    f"\n\n... [TRUNCATED - file is {len(content)} chars. "
                    f"Use read_file_chunk for specific parts]")
        return content
    except Exception as e:
        return f"Error reading {path}: {e}"

def read_file_chunk(path: str, start_line: int = 1, num_lines: int = MAX_CHUNK_LINES) -> str:
    try:
        p = Path(path)
        if p.is_dir():
            return f"Error: '{path}' is a directory, not a file."
        if not p.exists():
            return _missing_path_message(path)
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        total = len(lines)
        safe_num = max(1, min(num_lines or MAX_CHUNK_LINES, MAX_CHUNK_LINES))
        start = max(0, (start_line or 1) - 1)
        end = min(total, start + safe_num)
        header = f"📄 {path}  |  lines {start+1}–{end} of {total}\n{'─'*60}\n"
        return header + "\n".join(lines[start:end])
    except Exception as e:
        return f"Error: {e}"

def write_file(path: str, content: str) -> str:
    if not path or not path.strip():
        return "❌ Failed to write: empty file path."

    p = Path(path)
    if path.endswith(("/", "\\")) or p.is_dir():
        return f"❌ Refused to write to directory path '{path}'. Specify a concrete file path."

    if not content.strip():
        return f"❌ Refused to write empty content to '{path}'."

    if any(pat in content for pat in PLACEHOLDER_PATTERNS):
        return f"❌ Refused to write placeholder content to '{path}'. Provide actual file content first."

    if DRY_RUN:
        return f"[DRY-RUN] Would write {len(content)} chars → {path}"

    try:
        if p.exists():
            backup = p.with_suffix(p.suffix + ".bak")
            backup.write_text(p.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"✅ Wrote {path} (backup created)"
    except Exception as e:
        return f"❌ Failed to write {path}: {e}"

def write_files(files: List[Dict[str, str]]) -> str:
    """Write multiple files at once. Only after explicit confirmation."""
    if not files:
        return "No files provided."
    results = []
    for item in files:
        if not isinstance(item, dict):
            results.append(f"Invalid item: {item}")
            continue
        path = item.get("path")
        content = item.get("content")
        if not path or content is None:
            results.append(f"Invalid item: {item}")
            continue
        results.append(write_file(path, content))
    return "\n".join(results)

def get_git_status() -> str:
    if not is_git_repo():
        return "Not a git repository."
    branch = run_cmd("git branch --show-current")
    status = run_cmd("git status --short")
    diffstat = run_cmd("git diff --stat HEAD")
    log = run_cmd("git log --oneline -6")
    return f"Branch: {branch}\n\nStatus:\n{status}\n\nDiffstat:\n{diffstat}\n\nLog:\n{log}"

def create_branch(branch_name: str = None) -> str:
    if not is_git_repo():
        return "Not a git repository."
    if not branch_name:
        branch_name = f"ai-improve/{datetime.now().strftime('%Y%m%d-%H%M')}"
    if run_cmd(f"git branch --list {branch_name}").strip():
        run_cmd(f"git checkout {branch_name}")
        return f"Switched to existing branch: {branch_name}"
    result = run_cmd(f"git checkout -b {branch_name}")
    return f"Created & switched to branch: {branch_name}\n{result}"

def commit_changes(message: str) -> str:
    if not is_git_repo():
        return "Not a git repository."
    if DRY_RUN:
        return f"[DRY-RUN] Would commit: {message}"
    run_cmd("git add -A && git reset -- '*.bak' 2>/dev/null || true")
    safe_msg = message.replace('"', '\\"')
    return run_cmd(f'git commit -m "{safe_msg}"')

def show_diff(path: str = None) -> str:
    if path:
        return run_cmd(f"git diff -- {path}")
    return run_cmd("git diff") + "\n\n--- STAGED ---\n" + run_cmd("git diff --cached")

def export_patch(filename: str = "ai-improvements.patch") -> str:
    """Export current changes as a unified patch file."""
    diff = run_cmd("git diff") + "\n" + run_cmd("git diff --cached")
    if not diff.strip():
        return "No changes to export."
    Path(filename).write_text(diff, encoding="utf-8")
    return f"Patch saved to: {filename} ({len(diff)} bytes)"

def run_tests() -> str:
    """Try to detect and run the project's test suite."""
    results = []

    if any(Path(".").rglob("test_*.py")) or any(Path(".").rglob("*_test.py")) or Path("tests").exists():
        r = run_cmd("pytest -q --tb=no 2>/dev/null || python -m pytest -q --tb=no 2>/dev/null || true")
        results.append(f"pytest:\n{r[:2500]}")

    if Path("package.json").exists():
        r = run_cmd("npm test -- --watchAll=false 2>/dev/null || yarn test --watchAll=false 2>/dev/null || true")
        results.append(f"npm/yarn test:\n{r[:2000]}")

    if any(Path(".").rglob("*_test.go")):
        r = run_cmd("go test ./... 2>/dev/null || true")
        results.append(f"go test:\n{r[:2000]}")

    if Path("Cargo.toml").exists():
        r = run_cmd("cargo test 2>/dev/null || true")
        results.append(f"cargo test:\n{r[:2000]}")

    if not results:
        return "Could not detect a standard test runner."
    return "\n\n".join(results)

def create_pull_request(title: str, body: str = "") -> str:
    """Create a GitHub Pull Request using the GitHub CLI (gh)."""
    if not is_git_repo():
        return "Not a git repository."
    if DRY_RUN:
        return f"[DRY-RUN] Would create PR: {title}"

    branch = run_cmd("git branch --show-current").strip()
    if branch in {"main", "master"}:
        return "You are on main/master. Create a feature branch first."

    push = run_cmd(f"git push -u origin {branch}")

    body = body or "AI-assisted code improvements."
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body)
        body_file = f.name

    cmd = f'gh pr create --title "{title}" --body-file "{body_file}"'
    result = run_cmd(cmd)
    os.unlink(body_file)
    return f"Push result:\n{push}\n\nPR result:\n{result}"

def run_linter() -> str:
    results = []
    if any(Path(".").rglob("*.py")):
        r = run_cmd("ruff check . --output-format=text 2>/dev/null || true")
        if r.strip():
            results.append(f"Ruff:\n{r[:3500]}")
    if Path("package.json").exists():
        r = run_cmd("npx eslint . --ext .js,.jsx,.ts,.tsx 2>/dev/null | head -60 || true")
        if r.strip():
            results.append(f"ESLint:\n{r}")
    return "\n\n".join(results) if results else "No linter issues found."

def get_project_structure() -> str:
    return run_cmd(
        "find . -maxdepth 4 -type f \\( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.tsx' "
        "-o -name '*.go' -o -name '*.rs' -o -name '*.java' -o -name '*.tf' -o -name '*.tfvars' "
        "-o -name '*.yaml' -o -name '*.yml' \\) "
        "| grep -vE 'node_modules|__pycache__|venv|.venv|.git|dist|build|.terraform' | sort | head -150"
    )

# ====================== TOOL REGISTRY ======================

TOOLS = {
    "list_files": {"function": list_repo_files, "description": "List source and config files", "parameters": {"type": "object", "properties": {}, "required": []}},
    "read_file": {"function": read_file, "description": "Read full file (auto-truncates large ones)", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    "read_file_chunk": {"function": read_file_chunk, "description": "Read specific lines from a large file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"}, "num_lines": {"type": "integer"}}, "required": ["path"]}},
    "write_file": {"function": write_file, "description": "Write one file. ONLY after explicit user confirmation.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    "write_files": {"function": write_files, "description": "Write multiple files at once after confirmation. Argument: list of {path, content}", "parameters": {"type": "object", "properties": {"files": {"type": "array", "items": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}}, "required": ["files"]}},
    "get_git_status": {"function": get_git_status, "description": "Detailed git status", "parameters": {"type": "object", "properties": {}, "required": []}},
    "create_branch": {"function": create_branch, "description": "Create and switch to a new branch", "parameters": {"type": "object", "properties": {"branch_name": {"type": "string"}}, "required": []}},
    "commit_changes": {"function": commit_changes, "description": "git add + commit", "parameters": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}},
    "show_diff": {"function": show_diff, "description": "Show current diff", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []}},
    "export_patch": {"function": export_patch, "description": "Save current changes as a .patch file", "parameters": {"type": "object", "properties": {"filename": {"type": "string"}}, "required": []}},
    "run_tests": {"function": run_tests, "description": "Detect and run the project test suite", "parameters": {"type": "object", "properties": {}, "required": []}},
    "create_pull_request": {"function": create_pull_request, "description": "Create a GitHub Pull Request using gh CLI", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}}, "required": ["title"]}},
    "run_linter": {"function": run_linter, "description": "Run linters", "parameters": {"type": "object", "properties": {}, "required": []}},
    "get_project_structure": {"function": get_project_structure, "description": "Project structure overview", "parameters": {"type": "object", "properties": {}, "required": []}},
    "run_command": {"function": run_cmd, "description": "Run non-interactive shell command", "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}},
}

def resolve_tool_name(name: str) -> str:
    if name in TOOLS:
        return name
    return TOOL_ALIASES.get(name, name)

def get_openai_tools():
    return [{"type": "function", "function": {"name": n, "description": t["description"], "parameters": t["parameters"]}} for n, t in TOOLS.items()]

def extract_text_tool_calls(content: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Fallback parser if a local model outputs JSON tool calls as plain text."""
    if not content or "{" not in content:
        return []
    found: List[Tuple[str, Dict[str, Any]]] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(content):
        brace_idx = content.find("{", idx)
        if brace_idx == -1:
            break
        try:
            obj, end_idx = decoder.raw_decode(content[brace_idx:])
            idx = brace_idx + end_idx
            raw_name = obj.get("name") if isinstance(obj, dict) else None
            resolved = resolve_tool_name(raw_name) if isinstance(raw_name, str) else None
            if resolved and resolved in TOOLS:
                args = obj.get("arguments")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if not isinstance(args, dict):
                    args = {}
                found.append((resolved, args))
        except Exception:
            idx = brace_idx + 1
    return found

# ====================== AGENT ======================

class CodeImprovementAgent:
    def __init__(self):
        self.messages = []
        self.status = {"state": "idle", "task": "Ready at workstation"}
        dry = "\n\n⚠️  CURRENT MODE: DRY-RUN (no files will be modified)" if DRY_RUN else ""
        self.system_prompt = f"""You are a senior software engineer helping improve a local codebase.{dry}

Strict rules:
1. NEVER call write_file, write_files, create_branch, commit_changes, or create_pull_request unless the user explicitly asks for or confirms that action.
2. When asked to analyze or propose improvements without writing files, only inspect/read/lint/check status and return a concrete written proposal.
3. Call list_files or get_project_structure first if you are unsure of exact file paths. Never guess paths.
4. For large files always use read_file_chunk.
5. Always pass actual file paths and complete, real code—never directory paths or placeholders like "<proposed-changes>".
6. Do not repeat identical tool calls if they already returned no output or the same result.

Recommended workflow:
Explore → Lint → Read key files → Propose improvements → Wait for confirmation → 
Create branch → Write files → Run tests → Commit → (PR or patch)
"""

    def _set_status(self, state: str, task: str) -> None:
        self.status = {"state": state, "task": task}

    def _execute_tool_call(self, name: str, args: Dict[str, Any], call_id: str) -> None:
        resolved_name = resolve_tool_name(name)
        target = args.get("path") or args.get("branch_name") or args.get("cmd") or ""
        label = f"{resolved_name} {target}".strip()[:48]
        self._set_status("working", f"Running {label}")

        display = {k: (f"[{len(v)} files]" if k == "files" else
                       (v[:70] + "..." if isinstance(v, str) and len(v) > 70 else v))
                   for k, v in args.items()}
        print(f"→ {resolved_name}({display})")

        result = TOOLS[resolved_name]["function"](**args) if resolved_name in TOOLS else f"Unknown tool {name}"
        result_str = str(result)
        if len(result_str) > 6000:
            result_str = result_str[:6000] + "\n... [truncated]"
        print(f"← {len(result_str)} chars")

        self.messages.append({
            "role": "tool",
            "tool_call_id": call_id,
            "name": resolved_name,
            "content": result_str
        })

    def _dispatch_calls(self, calls: List[Tuple[str, Dict[str, Any], str]], seen_calls: set) -> int:
        executed = 0
        for name, args, call_id in calls:
            resolved_name = resolve_tool_name(name)
            call_sig = (resolved_name, json.dumps(args, sort_keys=True, default=str))
            if call_sig in seen_calls:
                print(f"↺ Skipped duplicate {resolved_name}")
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": resolved_name,
                    "content": "You ALREADY have the full output of this tool call earlier in this conversation. Do NOT call any more tools—write your final answer right now using the output you already received."
                })
                continue
            seen_calls.add(call_sig)
            self._execute_tool_call(resolved_name, args, call_id)
            executed += 1
        return executed

    def chat(self, user_message: str, max_steps: int = 8) -> str:
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})
        self.messages.append({"role": "user", "content": user_message})
        seen_calls = set()

        for step in range(max_steps):
            self._set_status("thinking", f"Planning step {step+1}/{max_steps}...")
            print(f"\n{'═'*64}\n Step {step+1}\n{'═'*64}")

            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=self.messages,
                    tools=get_openai_tools(),
                    tool_choice="auto",
                    temperature=0.1,
                )
            except Exception as e:
                print(f"Ollama error: {e}")
                self._set_status("idle", "Connection error")
                return f"Error talking to Ollama: {e}"

            message = response.choices[0].message

            if message.tool_calls:
                self.messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [{
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    } for tc in message.tool_calls]
                })

                parsed_calls = []
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except Exception:
                        args = {}
                    parsed_calls.append((tc.function.name, args, tc.id))

                self._dispatch_calls(parsed_calls, seen_calls)
            else:
                raw_content = message.content or ""
                fallback_calls = extract_text_tool_calls(raw_content)
                if fallback_calls:
                    self.messages.append({"role": "assistant", "content": raw_content})
                    indexed_calls = [
                        (name, args, f"fallback_{step}_{idx}")
                        for idx, (name, args) in enumerate(fallback_calls)
                    ]
                    self._dispatch_calls(indexed_calls, seen_calls)
                    continue

                print("\n" + raw_content)
                self.messages.append({"role": "assistant", "content": raw_content})
                self._set_status("done", "Task complete")
                return raw_content

        # Step budget exhausted: ask for a direct wrap-up summary without calling more tools
        self._set_status("thinking", "Wrapping up summary...")
        self.messages.append({
            "role": "user",
            "content": "Step limit reached. Provide a concise summary of what actions were taken and what remains."
        })
        try:
            wrap_response = client.chat.completions.create(
                model=MODEL,
                messages=self.messages,
                temperature=0.1,
            )
            summary = (wrap_response.choices[0].message.content or "").strip() or "Max steps reached."
        except Exception:
            summary = "Max steps reached."

        print("\n" + summary)
        self.messages.append({"role": "assistant", "content": summary})
        self._set_status("done", "Summary ready")
        return summary

# ====================== PIXEL AI EMPLOYEE WIDGET ======================

PIXEL_EMPLOYEE_HTML = """
<div class="pixel-office-card">
  <canvas class="pixel-canvas" width="220" height="124"></canvas>
  <div class="pixel-hud">
    <div class="pixel-name-row">
      <span class="pixel-dot" data-state="${value.state || 'idle'}"></span>
      <strong class="pixel-title">DEV-BOT // AI SRE</strong>
      <span class="pixel-badge">${(value.state || 'idle').toUpperCase()}</span>
    </div>
    <div class="pixel-task">${value.task || 'Ready at workstation'}</div>
    <div class="pixel-controls">
      <button type="button" class="pixel-btn" data-action="coffee">☕ Coffee</button>
      <button type="button" class="pixel-btn" data-action="wave">👋 Wave</button>
    </div>
  </div>
</div>
"""

PIXEL_EMPLOYEE_CSS = """
.pixel-office-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: linear-gradient(135deg, #131826 0%, #1c2438 100%);
  border: 2px solid #2e3b59;
  border-radius: 12px;
  padding: 10px 14px;
  color: #e6edf7;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
}
.pixel-canvas {
  width: 220px;
  height: 124px;
  border-radius: 8px;
  border: 2px solid #36466b;
  background: #1a2234;
  image-rendering: pixelated;
  image-rendering: crisp-edges;
  flex-shrink: 0;
}
.pixel-hud {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1;
}
.pixel-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.pixel-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #4ade80;
  box-shadow: 0 0 8px #4ade80;
}
.pixel-dot[data-state="thinking"] {
  background: #facc15;
  box-shadow: 0 0 8px #facc15;
}
.pixel-dot[data-state="working"] {
  background: #38bdf8;
  box-shadow: 0 0 8px #38bdf8;
}
.pixel-dot[data-state="done"] {
  background: #a78bfa;
  box-shadow: 0 0 8px #a78bfa;
}
.pixel-title {
  font-size: 13px;
  letter-spacing: 0.04em;
  color: #f8fafc;
}
.pixel-badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.16);
  border: 1px solid rgba(56, 189, 248, 0.4);
  color: #7dd3fc;
}
.pixel-task {
  font-size: 12px;
  color: #cbd5e1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pixel-controls {
  display: flex;
  gap: 8px;
  margin-top: 2px;
}
.pixel-btn {
  background: #25304a;
  color: #e2e8f0;
  border: 1px solid #3c4d75;
  border-radius: 6px;
  padding: 3px 9px;
  font-size: 11px;
  cursor: pointer;
}
.pixel-btn:hover {
  background: #324163;
}
"""

PIXEL_EMPLOYEE_JS = """
const canvas = element.querySelector('.pixel-canvas');
const ctx = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;

let tick = 0;
let manualAction = null;
let manualTimer = 0;
let particles = [];

element.addEventListener('click', (e) => {
  const btn = e.target.closest('.pixel-btn');
  if (!btn) return;
  manualAction = btn.dataset.action;
  manualTimer = 90;
});

function px(x, y, w, h, color) {
  ctx.fillStyle = color;
  ctx.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h));
}

function drawRoom(state) {
  // Wall & floor
  px(0, 0, 220, 92, '#1e273b');
  px(0, 92, 220, 32, '#141a29');
  px(0, 90, 220, 2, '#2f3d5c');

  // Window with night sky + stars
  px(14, 14, 46, 34, '#0f172a');
  px(14, 14, 46, 2, '#475569');
  px(14, 46, 46, 2, '#475569');
  px(14, 14, 2, 34, '#475569');
  px(58, 14, 2, 34, '#475569');
  px(36, 14, 2, 34, '#475569');
  px(14, 30, 46, 2, '#475569');
  px(22, 20, 2, 2, '#fef08a');
  px(48, 22, 2, 2, '#e2e8f0');
  if ((tick >> 4) % 2 === 0) px(28, 38, 2, 2, '#7dd3fc');

  // Whiteboard on right
  px(146, 14, 58, 36, '#e2e8f0');
  px(144, 12, 62, 2, '#64748b');
  px(144, 50, 62, 2, '#64748b');
  px(152, 20, 20, 2, '#38bdf8');
  px(152, 26, 32, 2, '#f43f5e');
  px(152, 32, 26, 2, '#22c55e');
  px(152, 38, 16, 2, '#6366f1');

  // Desk
  px(36, 76, 86, 6, '#854d0e');
  px(40, 82, 6, 24, '#713f12');
  px(112, 82, 6, 24, '#713f12');

  // Dual Monitor
  px(52, 48, 38, 24, '#334155');
  px(54, 50, 34, 20, state === 'working' ? '#082f49' : '#0f172a');
  px(68, 72, 6, 4, '#64748b');
  px(62, 75, 18, 2, '#94a3b8');

  // Animated code lines on screen
  const lineShift = state === 'working' ? (tick >> 2) % 4 : 0;
  px(57, 53 + lineShift, 14, 2, '#38bdf8');
  px(57, 58 + lineShift, 22, 2, '#4ade80');
  px(57, 63 + lineShift, 10, 2, '#facc15');

  // Coffee mug on desk
  px(102, 69, 7, 7, '#f8fafc');
  px(109, 71, 2, 3, '#cbd5e1');
  if ((tick >> 3) % 2 === 0) {
    px(104, 65 - ((tick >> 3) % 3), 1, 2, 'rgba(226,232,240,0.6)');
  }
}

function drawCharacter(x, y, state, frame) {
  const bob = (frame % 2 === 0) ? 0 : -1;
  const cy = y + bob;

  // Chair back when at desk
  if (state === 'working' || state === 'idle') {
    px(x - 4, cy + 12, 4, 18, '#334155');
    px(x - 2, cy + 26, 16, 4, '#475569');
  }

  // Hair & Head
  px(x + 2, cy, 12, 3, '#1e1b4b');
  px(x + 1, cy + 2, 14, 2, '#312e81');
  px(x + 2, cy + 4, 12, 10, '#fed7aa');

  // Glasses & Eyes (blink occasionally)
  const blinking = (tick % 75) > 70;
  px(x + 3, cy + 7, 4, 3, '#0f172a');
  px(x + 9, cy + 7, 4, 3, '#0f172a');
  px(x + 7, cy + 8, 2, 1, '#64748b');
  if (!blinking) {
    px(x + 5, cy + 8, 1, 1, '#38bdf8');
    px(x + 11, cy + 8, 1, 1, '#38bdf8');
  }

  // Hoodie torso
  px(x + 1, cy + 14, 14, 12, '#2563eb');
  px(x + 6, cy + 14, 4, 12, '#1d4ed8');

  // Arms
  if (state === 'working') {
    const reach = (frame % 2 === 0) ? 0 : -2;
    px(x + 13, cy + 16 + reach, 8, 3, '#3b82f6');
    px(x + 20, cy + 16 + reach, 2, 2, '#fed7aa');
  } else if (state === 'wave' || state === 'done') {
    const waveY = (frame % 2 === 0) ? -4 : -1;
    px(x + 14, cy + 10 + waveY, 3, 8, '#3b82f6');
    px(x + 14, cy + 8 + waveY, 3, 3, '#fed7aa');
  } else if (state === 'coffee') {
    px(x + 12, cy + 14, 6, 3, '#3b82f6');
    px(x + 17, cy + 12, 5, 5, '#f8fafc');
  } else {
    px(x + 12, cy + 16, 4, 7, '#3b82f6');
  }

  // Legs
  if (state === 'thinking') {
    const step = (frame % 2 === 0) ? -2 : 2;
    px(x + 3 + step, cy + 26, 4, 9, '#1e293b');
    px(x + 9 - step, cy + 26, 4, 9, '#1e293b');
  } else {
    px(x + 3, cy + 26, 4, 9, '#1e293b');
    px(x + 9, cy + 26, 4, 9, '#1e293b');
  }
}

function drawBubble(x, y, text) {
  px(x, y, 28, 13, '#f8fafc');
  px(x + 4, y + 13, 4, 3, '#f8fafc');
  ctx.fillStyle = '#0f172a';
  ctx.font = 'bold 9px monospace';
  ctx.fillText(text, x + 5, y + 9);
}

function render() {
  tick++;
  if (manualTimer > 0) {
    manualTimer--;
    if (manualTimer === 0) manualAction = null;
  }

  const rawState = (props.value && props.value.state) ? props.value.state : 'idle';
  const activeState = manualAction || rawState;
  const frame = Math.floor(tick / 10);

  ctx.clearRect(0, 0, canvas.width, canvas.height);
  drawRoom(activeState);

  let charX = 76;
  let charY = 58;
  let bubble = '';

  if (activeState === 'thinking') {
    charX = 148 + Math.sin(tick * 0.06) * 14;
    charY = 62;
    bubble = '.'.repeat((frame % 3) + 1);
  } else if (activeState === 'working') {
    charX = 74;
    charY = 58;
    bubble = '</>';
    if (tick % 8 === 0) {
      particles.push({ x: 70 + Math.random() * 16, y: 48, vy: -0.5, life: 26 });
    }
  } else if (activeState === 'done') {
    charX = 122;
    charY = 62;
    bubble = 'OK!';
  } else if (activeState === 'wave') {
    charX = 122;
    charY = 62;
    bubble = 'HI!';
  } else if (activeState === 'coffee') {
    charX = 116;
    charY = 62;
    bubble = '☕';
  }

  drawCharacter(charX, charY, activeState, frame);
  if (bubble) drawBubble(charX + 12, charY - 16, bubble);

  // Floating code particles when working
  particles = particles.filter(p => p.life > 0);
  for (const p of particles) {
    p.y += p.vy;
    p.life--;
    px(p.x, p.y, 2, 2, '#38bdf8');
  }

  requestAnimationFrame(render);
}

render();
"""

# ====================== GRADIO UI (Gradio 6 compatible) ======================

def launch_ui():
    try:
        import gradio as gr
    except ImportError:
        print("Gradio not installed. Run: pip install gradio")
        sys.exit(1)

    agent = CodeImprovementAgent()

    def respond(message, history):
        if not message or not message.strip():
            yield history, agent.status
            return

        agent._set_status("thinking", "Reading request...")
        yield history, agent.status

        response = agent.chat(message)
        history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": response}
        ]
        yield history, agent.status

    def clear_chat():
        agent.messages = []
        agent._set_status("idle", "Ready at workstation")
        return [], agent.status

    with gr.Blocks(title="Code Improvement Agent") as demo:
        with gr.Row():
            with gr.Column(scale=3):
                gr.Markdown("# Local Code Improvement Agent (Ollama)")
                gr.Markdown(f"**Model:** `{MODEL}` &nbsp;&nbsp;|&nbsp;&nbsp; **Dry-run:** `{DRY_RUN}`")
            with gr.Column(scale=4):
                employee_avatar = gr.HTML(
                    value=agent.status,
                    html_template=PIXEL_EMPLOYEE_HTML,
                    css_template=PIXEL_EMPLOYEE_CSS,
                    js_on_load=PIXEL_EMPLOYEE_JS,
                    show_label=False,
                )

        chatbot = gr.Chatbot(height=520)
        msg = gr.Textbox(
            placeholder="Ask me to analyze the repo, propose improvements, apply changes...",
            label="Message",
            scale=7
        )

        with gr.Row():
            submit = gr.Button("Send", variant="primary")
            clear = gr.Button("Clear conversation")

        # Live status polling while agent works across multi-step tool calls
        status_timer = gr.Timer(0.6)
        status_timer.tick(lambda: agent.status, outputs=employee_avatar)

        submit.click(respond, inputs=[msg, chatbot], outputs=[chatbot, employee_avatar]).then(
            lambda: "", None, msg
        )
        msg.submit(respond, inputs=[msg, chatbot], outputs=[chatbot, employee_avatar]).then(
            lambda: "", None, msg
        )
        clear.click(clear_chat, outputs=[chatbot, employee_avatar])

    print("\nLaunching web UI → http://127.0.0.1:7860")
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        theme=gr.themes.Soft()
    )

# ====================== MAIN ======================

def main():
    global DRY_RUN

    print("=" * 64)
    print("  Ultimate Code Improvement Agent")
    print("=" * 64)

    if "--dry-run" in sys.argv:
        DRY_RUN = True
        sys.argv.remove("--dry-run")
        print("→ Dry-run mode enabled")

    if "--ui" in sys.argv:
        sys.argv.remove("--ui")
        launch_ui()
        return

    # CLI mode
    print(f"Model    : {MODEL}")
    print(f"Directory: {os.getcwd()}")
    print(f"Dry-run  : {DRY_RUN}")
    print("-" * 64)

    try:
        client.models.list()
    except Exception:
        print("\n❌ Cannot connect to Ollama. Run `ollama serve` and pull a model.")
        sys.exit(1)

    agent = CodeImprovementAgent()

    args = sys.argv[1:]
    goal = " ".join(args) if args else (
        "Analyze this repository. Start with structure, git status and linters. "
        "Then examine the most important files and propose the highest-value improvements. "
        "Do not write any files until I explicitly confirm."
    )

    print(f"\nGoal: {goal}\n")
    agent.chat(goal)

    print("\n" + "=" * 64)
    print("Continue the conversation. Useful phrases:")
    print("  • yes, create a branch and apply all changes")
    print("  • run the tests")
    print("  • commit and create a pull request")
    print("  • export a patch file")
    print("  • exit")
    print("=" * 64)

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break
        if not user_input:
            continue
        if user_input.lower() in {"exit", "quit", "q"}:
            print("Bye!")
            break
        agent.chat(user_input)

if __name__ == "__main__":
    main()