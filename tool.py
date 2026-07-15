import subprocess
from pathlib import Path

from langchain.tools import tool

SCRIPTS_DIR = Path("scripts")


@tool
def run_python_script(script_name: str) -> str:
    """
    Execute a Python script from the scripts directory.

    Example:
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

        return output

    except Exception as e:
        return str(e)