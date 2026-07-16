import os
import re
import platform
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain.messages import HumanMessage

load_dotenv(override=True)

# ==========================
# LLM for shell conversion
# ==========================

llm = ChatOpenAI(
    model="gpt-5",
    temperature=0
)

# ==========================
# Generalized Script Runner
# ==========================

import sys
import shutil
import tempfile

# Fallback directory used only when a bare filename (no path) is given
# and it isn't found in the current working directory.
SCRIPTS_DIR = Path("scripts")

# Use the same interpreter that's currently running, instead of assuming
# "python" resolves correctly (on some systems only "python3" exists).
PYTHON_EXECUTABLE = sys.executable or "python"


def _resolve_script_path(script_name: str) -> Path:
    """
    Resolves a script path from any of:
      - an absolute path (Windows or POSIX): C:\\Users\\me\\train.py, /home/me/train.py
      - a relative path from the current working directory: subdir/train.py, ../train.py
      - a path using "~" for home: ~/scripts/train.py
      - a bare filename: train.py (checked in CWD first, then SCRIPTS_DIR as a fallback,
        then Documents/Desktop/Downloads as a last resort)
    """

    expanded = os.path.expanduser(script_name.strip().strip('"').strip("'"))
    candidate = Path(expanded)

    if candidate.is_absolute():
        return candidate

    if candidate.exists():
        return candidate.resolve()

    fallback = SCRIPTS_DIR / candidate
    if fallback.exists():
        return fallback.resolve()

    for location in (HOME / "Desktop", HOME / "Documents", HOME / "Downloads"):
        maybe = location / candidate
        if maybe.exists():
            return maybe.resolve()

    # Nothing matched; return the most likely candidate so the caller can
    # report a clear "not found" message with the path it actually tried.
    return candidate


def _is_available(executable: str) -> bool:
    return shutil.which(executable) is not None


# Maps a file extension to how it should be run.
# "interpreter": run directly with an interpreter, no build step.
# "compiled": needs a compile step first, then run the produced binary.
_INTERPRETERS = {
    ".py": [PYTHON_EXECUTABLE],
    ".js": ["node"],
    ".ts": ["npx", "ts-node"],
    ".rb": ["ruby"],
    ".sh": ["bash"],
    ".ps1": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"],
}

_COMPILED = {
    ".rs": {"compiler": "rustc"},
    ".go": {"run_directly": ["go", "run"]},  # go run skips a manual build step
    ".c": {"compiler": "gcc"},
    ".cpp": {"compiler": "g++"},
    ".java": {"compiler": "javac", "run_after": "java"},
}


def _run_interpreted(executable_parts, script_path: Path):
    result = subprocess.run(
        [*executable_parts, str(script_path)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=script_path.parent,
    )
    return result


def _run_compiled(ext: str, script_path: Path):
    spec = _COMPILED[ext]

    # Languages where the toolchain itself runs the file without a separate
    # explicit compile step (e.g. "go run file.go").
    if "run_directly" in spec:
        return subprocess.run(
            [*spec["run_directly"], str(script_path)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=script_path.parent,
        )

    compiler = spec["compiler"]
    if not _is_available(compiler):
        raise RuntimeError(f"'{compiler}' is not installed or not on PATH.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)

        if ext == ".java":
            # Java: compile into tmp dir, then run the class by name.
            compile_result = subprocess.run(
                [compiler, "-d", str(tmp_dir_path), str(script_path)],
                capture_output=True, text=True, timeout=300,
            )
            if compile_result.returncode != 0:
                return compile_result

            class_name = script_path.stem
            return subprocess.run(
                ["java", "-cp", str(tmp_dir_path), class_name],
                capture_output=True, text=True, timeout=300,
            )

        binary_name = script_path.stem + (".exe" if IS_WINDOWS_NAME() else "")
        binary_path = tmp_dir_path / binary_name

        compile_result = subprocess.run(
            [compiler, str(script_path), "-o", str(binary_path)],
            capture_output=True, text=True, timeout=300,
        )
        if compile_result.returncode != 0:
            return compile_result

        return subprocess.run(
            [str(binary_path)],
            capture_output=True, text=True, timeout=300,
            cwd=script_path.parent,
        )


def IS_WINDOWS_NAME():
    # Defined ahead of the OS-detection block below; re-checks directly
    # so this helper works no matter where it's called from in the file.
    return platform.system() == "Windows"


@tool
def run_script(script_path_input: str) -> str:
    """
    Compile (if needed) and execute a script or source file in any
    supported language, from anywhere on the filesystem.

    Supported extensions:
      .py   -> run with Python
      .js   -> run with Node.js
      .ts   -> run with ts-node
      .rb   -> run with Ruby
      .sh   -> run with bash
      .ps1  -> run with PowerShell
      .rs   -> compile with rustc, then run
      .go   -> run with "go run"
      .c    -> compile with gcc, then run
      .cpp  -> compile with g++, then run
      .java -> compile with javac, then run

    Accepts:
      - An absolute path: /Users/me/project/main.rs or C:\\Users\\me\\project\\main.rs
      - A relative path: subdir/train.py or ../scripts/test.js
      - A "~"-based path: ~/Documents/scripts/train.py
      - A bare filename: agent.py (checked in CWD, then a local "scripts"
        folder, then Desktop/Documents/Downloads)

    Examples:
        hello.py
        ~/Desktop/agent.py
        main.rs
        server.js
        /Users/me/project/App.java
    """

    script_path = _resolve_script_path(script_path_input)

    if not script_path.exists():
        return f"Script '{script_path_input}' not found (looked for: {script_path})."

    ext = script_path.suffix.lower()

    try:
        if ext in _INTERPRETERS:
            result = _run_interpreted(_INTERPRETERS[ext], script_path)
        elif ext in _COMPILED:
            result = _run_compiled(ext, script_path)
        else:
            supported = ", ".join(sorted(set(_INTERPRETERS) | set(_COMPILED)))
            return f"Unsupported file type '{ext}'. Supported extensions: {supported}"

        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"

        return output or "Script executed successfully."

    except subprocess.TimeoutExpired:
        return "Error: script timed out after 300 seconds."
    except Exception as e:
        return f"Error: {str(e)}"

# ==========================
# File Read / Edit Tools
# ==========================

import difflib

def _resolve_file_path(path_input: str) -> Path:
    """
    Same resolution rules as _resolve_script_path, reused for reading
    and editing arbitrary files (not just runnable scripts).
    """
    return _resolve_script_path(path_input)


@tool
def read_file(path_input: str) -> str:
    """
    Read and return the contents of a file, with line numbers, so it can
    be inspected before making an edit.

    Accepts the same kinds of paths as run_script: absolute, relative,
    "~"-based, or a bare filename (checked in CWD, "scripts/", then
    Desktop/Documents/Downloads).

    Examples:
        buggy.py
        ~/Desktop/agent.py
        src/main.rs
    """

    file_path = _resolve_file_path(path_input)

    if not file_path.exists():
        return f"File '{path_input}' not found (looked for: {file_path})."

    if not file_path.is_file():
        return f"'{file_path}' is not a file."

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file: {str(e)}"

    numbered = "\n".join(
        f"{i + 1:>4}: {line}" for i, line in enumerate(text.splitlines())
    )
    return f"Contents of {file_path}:\n\n{numbered}"


def _confirm_write(file_path: Path, diff_text: str) -> bool:
    """
    Shows a diff preview and asks for explicit confirmation in the
    terminal before writing changes to disk. Returns True if approved.
    """
    print(f"\n--- Proposed change to {file_path} ---")
    print(diff_text if diff_text.strip() else "(no visible diff — check content)")
    print("--- end of proposed change ---")
    answer = input(f"Apply this change to {file_path}? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


@tool
def edit_file(path_input: str, old_str: str, new_str: str) -> str:
    """
    Apply a targeted find-and-replace edit to a file: replaces the first
    exact occurrence of old_str with new_str. Shows a diff and asks for
    user confirmation in the terminal before writing.

    Use this for bug fixes and small changes rather than rewriting the
    whole file. old_str must match the file's existing content exactly
    (whitespace included) and should be unique enough to target the
    right spot.

    Examples:
        path_input: "buggy.py"
        old_str:    "return a / b"
        new_str:    "return a / b if b != 0 else 0"
    """

    file_path = _resolve_file_path(path_input)

    if not file_path.exists():
        return f"File '{path_input}' not found (looked for: {file_path})."

    try:
        original = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading file: {str(e)}"

    if old_str not in original:
        return (
            f"Could not find the given old_str in {file_path}. "
            "Make sure it matches the file's exact current content "
            "(use read_file first to confirm)."
        )

    if original.count(old_str) > 1:
        return (
            f"old_str appears {original.count(old_str)} times in {file_path}, "
            "which is ambiguous. Include more surrounding context to make it unique."
        )

    updated = original.replace(old_str, new_str, 1)

    diff_text = "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=str(file_path),
            tofile=str(file_path),
            lineterm="",
        )
    )

    if not _confirm_write(file_path, diff_text):
        return "Edit cancelled by user."

    try:
        file_path.write_text(updated, encoding="utf-8")
    except Exception as e:
        return f"Error writing file: {str(e)}"

    return f"Edit applied to {file_path}."


@tool
def write_file(path_input: str, content: str) -> str:
    """
    Create a new file, or fully overwrite an existing one, with the
    given content. Shows a diff (or full content, for new files) and
    asks for user confirmation in the terminal before writing.

    Prefer edit_file for small fixes to existing files; use write_file
    for new files or full rewrites.

    Examples:
        path_input: "~/Desktop/new_script.py"
        content:    "print('hello')"
    """

    file_path = _resolve_file_path(path_input)
    # For new files, _resolve_file_path may just echo back a relative
    # candidate since nothing exists yet -- resolve it against CWD.
    if not file_path.is_absolute():
        file_path = (Path.cwd() / file_path).resolve()

    original = ""
    if file_path.exists():
        try:
            original = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading existing file: {str(e)}"

    if original:
        diff_text = "\n".join(
            difflib.unified_diff(
                original.splitlines(),
                content.splitlines(),
                fromfile=str(file_path),
                tofile=str(file_path),
                lineterm="",
            )
        )
    else:
        diff_text = f"(new file)\n{content}"

    if not _confirm_write(file_path, diff_text):
        return "Write cancelled by user."

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        return f"Error writing file: {str(e)}"

    return f"File written to {file_path}."



SYSTEM = platform.system()  # "Windows", "Darwin" (macOS), or "Linux"
IS_WINDOWS = SYSTEM == "Windows"
IS_MACOS = SYSTEM == "Darwin"
IS_LINUX = SYSTEM == "Linux"

OS_LABEL = {
    "Windows": "Windows (PowerShell)",
    "Darwin": "macOS Unix shell",
    "Linux": "Linux Unix shell",
}.get(SYSTEM, SYSTEM)

# ==========================
# Shell Environment
# ==========================

HOME = Path.home()
CWD = Path.cwd()

KNOWN_LOCATIONS = {
    "documents": HOME / "Documents",
    "desktop": HOME / "Desktop",
    "downloads": HOME / "Downloads",
    "home": HOME,
}

def get_shell_context_text() -> str:
    """
    Internal helper.
    Provides absolute paths and OS context to the LLM.
    """

    return f"""
Environment:

HOME:
{HOME}

Current working directory:
{CWD}

Documents:
{KNOWN_LOCATIONS['documents']}

Desktop:
{KNOWN_LOCATIONS['desktop']}

Downloads:
{KNOWN_LOCATIONS['downloads']}

Operating System:
{OS_LABEL}
"""

# ==========================
# Shell Utilities
# ==========================

def normalize_command(command: str) -> str:

    command = command.strip()

    if command.startswith("```"):
        lines = [line for line in command.splitlines() if not line.strip().startswith("```")]
        command = "\n".join(lines).strip()

    command = command.strip("`")

    if (len(command) >= 2 and command[0] == command[-1] and command[0] in {'"', "'"}):
        command = command[1:-1]

    return command.strip()

def infer_base_directory(user_message: str):

    message = user_message.lower()

    for keyword, path in KNOWN_LOCATIONS.items():
        if keyword in message:
            return path

    return None

def _windows_mkdir_pattern():
    # New-Item -ItemType Directory -Path "..." -Force
    return re.compile(r'^New-Item\s+-ItemType\s+Directory\s+-Path\s+"?(.+?)"?\s*(-Force)?\s*$', re.IGNORECASE)

def _posix_mkdir_pattern():
    return re.compile(r"^mkdir(?:\s+-p)?\s+(.+)$")

def resolve_command_paths(command: str, user_message: str):

    command = os.path.expanduser(normalize_command(command))

    if IS_WINDOWS:
        match = _windows_mkdir_pattern().match(command)
        if not match:
            return command

        raw_path = match.group(1).strip().strip('"').strip("'")
        path = Path(os.path.expanduser(raw_path))

        if path.is_absolute():
            resolved = path
        else:
            base = (infer_base_directory(user_message) or CWD)
            resolved = (base / path).resolve()

        return f'New-Item -ItemType Directory -Path "{resolved}" -Force'

    # macOS / Linux
    match = _posix_mkdir_pattern().match(command)
    if not match:
        return command

    raw_path = match.group(1).strip().strip('"').strip("'")
    path = Path(os.path.expanduser(raw_path))

    if path.is_absolute():
        resolved = path
    else:
        base = (infer_base_directory(user_message) or CWD)
        resolved = (base / path).resolve()

    return f"mkdir -p {resolved}"

def run_shell_command(command: str):
    """
    Runs a command using the appropriate shell for the current OS:
      - Windows -> powershell.exe
      - macOS/Linux -> the default POSIX shell (via shell=True)
    """

    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                text=True,
                capture_output=True,
                cwd=CWD,
            )
        else:
            result = subprocess.run(
                command,
                shell=True,
                text=True,
                capture_output=True,
                cwd=CWD,
                executable="/bin/bash",
            )

        if result.returncode != 0:
            return f"Command failed:\n{result.stderr or result.stdout}"

        if result.stdout.strip():
            return result.stdout.strip()

        if result.stderr.strip():
            return result.stderr.strip()

        return "Command executed successfully."

    except Exception as e:
        return f"Error running command: {str(e)}"

# ==========================
# Natural Language -> Shell
# ==========================

def _examples_for_os() -> str:
    if IS_WINDOWS:
        return f"""
User:
List files in Documents

Command:
Get-ChildItem "{KNOWN_LOCATIONS['documents']}"

User:
Create folder Test inside Documents

Command:
New-Item -ItemType Directory -Path "{KNOWN_LOCATIONS['documents']}\\Test" -Force

User:
Show disk usage

Command:
Get-PSDrive -PSProvider FileSystem
"""
    else:
        return f"""
User:
List files in Documents

Command:
ls {KNOWN_LOCATIONS['documents']}

User:
Create folder Test inside Documents

Command:
mkdir -p {KNOWN_LOCATIONS['documents']}/Test

User:
Show disk usage

Command:
df -h
"""

def convert_to_shell_command(natural_language: str):
    rules = """
Rules:

- Return ONLY the command.
- No markdown.
- No explanation.
- Always use absolute paths.
"""

    if IS_WINDOWS:
        rules += "- Generate a valid Windows PowerShell command (not cmd.exe, not bash/Unix syntax).\n"
        rules += "- For folders use: New-Item -ItemType Directory -Path <path> -Force\n"
    else:
        rules += "- Generate a valid POSIX shell command (bash-compatible).\n"
        rules += "- For folders use mkdir -p.\n"

    prompt = f"""

{get_shell_context_text()}

Convert the user request into ONE shell command.

{rules}

Examples:
{_examples_for_os()}

User request:

{natural_language}

"""

    response = llm.invoke(
        [
            HumanMessage(
                content=prompt
            )
        ]
    )

    command = resolve_command_paths(response.content, natural_language)

    return command

# ==========================
# Shell Tool
# ==========================

@tool
def process_shell_tool(natural_language: str) -> str:
    """
    Execute operating system commands. Works on macOS, Windows, and Linux —
    the underlying shell and command syntax are chosen automatically based
    on the OS this tool is running on.

    Examples:

    Create folder named Test in Documents

    List files in Downloads

    Show disk usage
    """

    command = convert_to_shell_command(natural_language)
    output = run_shell_command(command)

    return f"""Command: {command} Output: {output}"""