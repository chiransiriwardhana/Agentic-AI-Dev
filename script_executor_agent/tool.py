import os
import re
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
            ["python", str(script_path)],
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
    Provides absolute paths to LLM.
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
macOS Unix shell
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



def resolve_command_paths(command: str, user_message: str):

    command = os.path.expanduser(normalize_command(command))
    mkdir_match = re.match(r"^mkdir(?:\s+-p)?\s+(.+)$",command)

    if not mkdir_match:
        return command

    raw_path = (mkdir_match.group(1).strip().strip('"').strip("'"))
    path = Path(os.path.expanduser(raw_path))

    if path.is_absolute():
        resolved = path
    else:
        base = (infer_base_directory(user_message) or CWD)
        resolved = (base / path).resolve()

    return f"mkdir -p {resolved}"


def run_shell_command(command: str):

    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True, cwd=CWD)

        if result.stdout.strip():
            return result.stdout.strip()

        if result.stderr.strip():
            return result.stderr.strip()

        return "Command executed successfully."


    except subprocess.CalledProcessError as e:
        return f"Command failed:\n{e.stderr or e.stdout}"



# ==========================
# Natural Language -> Shell
# ==========================

def convert_to_shell_command(natural_language: str):
    prompt = f"""

{get_shell_context_text()}


Convert the user request into ONE shell command.


Rules:

- Return ONLY the command.
- No markdown.
- No explanation.

- Always use absolute paths.

- For folders use mkdir -p.

Examples:

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

    command = resolve_command_paths(response.content,natural_language)

    return command



# ==========================
# Shell Tool
# ==========================

@tool
def process_shell_tool(natural_language: str) -> str:
    """
    Execute operating system commands.

    Examples:

    Create folder named Test in Documents

    List files in Downloads

    Show disk usage
    """

    command = convert_to_shell_command(natural_language)
    output = run_shell_command(command)

    return f"""Command: {command} Output: {output}"""