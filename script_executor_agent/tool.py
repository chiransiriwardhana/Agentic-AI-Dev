import os
import re
import sys
import shutil
import platform
import tempfile
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
# OS Detection
# ==========================

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
# Generalized Script Runner
# ==========================

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
      - a bare filename: train.py (checked in CWD first, then SCRIPTS_DIR,
        then Desktop/Documents/Downloads as a last resort)
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
    return subprocess.run(
        [*executable_parts, str(script_path)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=script_path.parent,
    )


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

        binary_name = script_path.stem + (".exe" if IS_WINDOWS else "")
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
    Execute general operating system commands (not script execution).
    Works on macOS, Windows, and Linux — the underlying shell and command
    syntax are chosen automatically based on the OS this tool is running on.

    Examples:

    Create folder named Test in Documents

    List files in Downloads

    Show disk usage
    """

    command = convert_to_shell_command(natural_language)
    output = run_shell_command(command)

    return f"""Command: {command} Output: {output}"""