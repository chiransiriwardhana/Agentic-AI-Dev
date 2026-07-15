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
# Python Script Tool
# ==========================

SCRIPTS_DIR = Path("scripts")

# Use the same interpreter that's currently running, instead of assuming
# "python" resolves correctly (on some systems only "python3" exists).
import sys
PYTHON_EXECUTABLE = sys.executable or "python"

@tool
def run_python_script(script_name: str) -> str:
    """
    Execute a Python script from the scripts directory.

    Examples:
        hello.py
        train.py
        test.py
    """

    script_path = SCRIPTS_DIR / script_name

    if not script_path.exists():
        return f"Script '{script_name}' not found."

    try:

        result = subprocess.run(
            [PYTHON_EXECUTABLE, str(script_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )

        output = ""

        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"

        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"

        return output or "Script executed successfully."

    except Exception as e:
        return f"Error: {str(e)}"

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