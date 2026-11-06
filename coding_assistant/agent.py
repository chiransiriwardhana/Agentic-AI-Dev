import json
import os
import sys

from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage

from tool import (
    run_script,
    process_shell_tool,
    read_file,
    edit_file,
    write_file,
    install_python_dependencies,
)


load_dotenv(override=True)

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY is missing")


# model = ChatOpenAI(
#     model="gpt-5",
#     temperature=0
# )


# from langchain_ollama import ChatOllama

# model = ChatOllama(
#     model="llama3.2:latest",   # must match the name in `ollama list`
#     temperature=0,
#     base_url="http://localhost:11434",  # default, optional
# )


llm = ChatGroq(
    model="openai/gpt-oss-20b",
    api_key=os.environ["GROQ_API_KEY"],
    temperature=0,
    streaming=True,
    reasoning_format="parsed",   
    reasoning_effort="high",   
    model_kwargs={"parallel_tool_calls": False},
)



agent = create_agent(
    model=llm,
    tools=[
        run_script,
        process_shell_tool,
        read_file,
        edit_file,
        write_file,
        install_python_dependencies,
    ],

    system_prompt="""

You are an expert coding assistant. You help the user write, review,
debug, refactor, and run code across any programming language.

Your responsibilities:

- Write clean, correct, well-structured code when asked.
- Explain code, errors, and stack traces clearly and concisely.
- Debug issues by reasoning through the problem before proposing a fix.
- Suggest improvements: readability, performance, security, edge cases,
  and best practices, when relevant.
- Ask a clarifying question only if the request is genuinely ambiguous;
  otherwise make a reasonable assumption, state it briefly, and proceed.
- Prefer showing complete, runnable code over vague descriptions.

You have six tools available:

1. read_file
Reads a file's contents (with line numbers) so you can see the actual
current code before diagnosing a bug or proposing a fix. Always read a
file before editing it if you have not already seen its exact content
in this conversation.

2. run_script
Compiles (if needed) and executes a script or source file in any of:
Python (.py), JavaScript (.js), TypeScript (.ts), Ruby (.rb),
Bash (.sh), PowerShell (.ps1), Rust (.rs), Go (.go), C (.c), C++ (.cpp),
or Java (.java). Returns STDOUT/STDERR so you can see whether it
succeeded or what error occurred.

3. edit_file
Applies a targeted find-and-replace fix to an existing file (old_str
must exactly match current content, and must be unique in the file).
Prefer this over write_file for bug fixes -- it changes only what's
necessary. This tool shows the user a diff and asks for confirmation
in their terminal before writing; if the user declines, treat the fix
as not applied and say so.

4. write_file
Creates a new file, or fully overwrites an existing one. Use for new
files or large rewrites, not small fixes. Also asks for confirmation
before writing.

5. process_shell_tool
Runs general OS actions that are not about running or editing a
specific script file (e.g. creating folders, listing files, checking
disk usage, running git commands). Do NOT use this to install Python
packages -- use install_python_dependencies instead.

6. install_python_dependencies
Installs Python packages into the same interpreter that run_script
uses. Call this when a .py script fails with ModuleNotFoundError or
ImportError ("No module named ..."), or when the user asks to install
libraries before running. Pass the missing import name(s). Do not
guess that a package is installed -- observe run_script output first.


REASON / PLAN / EXECUTE / OBSERVE LOOP:

Whenever the user asks you to run, fix, or make a script produce
correct output, do not stop after one attempt. Cycle through:

1. REASON: state the goal and what the latest evidence (code, STDOUT,
   STDERR) actually shows. Do not invent errors or file contents.
2. PLAN: choose the next smallest action (read, run, install missing
   deps, or edit).
3. EXECUTE: call exactly that tool.
4. OBSERVE: read the tool result. If the script did not produce the
   expected successful output, loop again with the new evidence.

Python missing-dependency path (do this before editing code):

- If STDERR contains ModuleNotFoundError or ImportError for a missing
  module, call install_python_dependencies with that module name, then
  run_script again.
- If another missing module appears, install it and re-run. Repeat
  until imports succeed.
- Do not use process_shell_tool / pip / pip3 for Python packages.

Code-debug path (after dependencies are present):

- read_file if you do not already have the current source.
- Diagnose from the real error and real code.
- edit_file the smallest fix, then run_script again.
- Keep looping (reason -> plan -> execute -> observe) until run_script
  exits successfully AND the output matches what the user asked for.
- Cap: at most 8 execute steps after the first run. If still failing,
  stop, explain what you tried and the last error, and ask how to
  proceed.

Do not claim success unless you actually re-ran the script and saw
correct output. Do not fabricate file contents, error messages, or
command output -- always get them from the tools.

"""
)



print("Agent Ready! (streaming + thinking enabled)")
print("----------------")


# ======================
# Terminal streaming UI
# ======================

DIM = "\033[2m"
ITALIC = "\033[3m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"

TOOL_RESULT_PREVIEW_CHARS = 800


def _supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _style(text: str, *codes: str) -> str:
    if not _supports_color():
        return text
    return f"{''.join(codes)}{text}{RESET}"


def _delta(previous: str, incoming: str) -> str:
    """Groq may send either a token delta or the full text so far."""
    if not incoming:
        return ""
    if incoming.startswith(previous):
        return incoming[len(previous):]
    return incoming


def _message_text(message) -> str:
    content = getattr(message, "content", "") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
        return "".join(parts)
    return str(content)


def _reasoning_text(message) -> str:
    extra = getattr(message, "additional_kwargs", None) or {}
    reasoning = extra.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning:
        return reasoning

    blocks = getattr(message, "content_blocks", None) or []
    parts = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "reasoning":
            parts.append(block.get("reasoning") or block.get("text") or "")
    return "".join(parts)


def _truncate(text: str, limit: int = TOOL_RESULT_PREVIEW_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n... [truncated]"


def _format_tool_args(args) -> str:
    if args is None:
        return ""
    if isinstance(args, str):
        return args
    try:
        return json.dumps(args, ensure_ascii=False, indent=2)
    except TypeError:
        return str(args)


def _unpack_stream_item(item):
    """Normalize LangGraph stream items across single/multi stream_mode."""
    if isinstance(item, dict) and "type" in item and "data" in item:
        return item["type"], item["data"]
    if isinstance(item, tuple) and len(item) == 2:
        first, second = item
        if first in {"messages", "updates", "values"}:
            return first, second
        return "messages", item
    return "messages", item


class TerminalStreamPrinter:
    """Prints thinking, tool use, and the answer as they stream in."""

    def __init__(self):
        self._section = None
        self._reasoning_seen = ""
        self._answer_seen = ""
        self._generation_id = None
        self._printed_tool_call_ids = set()
        self._printed_tool_result_ids = set()
        self._printed_answer = False

    def _end_section(self):
        if self._section is not None:
            print(flush=True)
        self._section = None

    def _open(self, section: str, title: str, *styles: str):
        if self._section == section:
            return
        self._end_section()
        print(_style(title, *styles), flush=True)
        self._section = section

    def _on_new_generation(self, message_id):
        if message_id and message_id != self._generation_id:
            self._generation_id = message_id
            self._reasoning_seen = ""
            self._answer_seen = ""
            self._printed_answer = False

    def on_message_chunk(self, token):
        if not isinstance(token, AIMessageChunk):
            return

        self._on_new_generation(getattr(token, "id", None))

        reasoning_delta = _delta(self._reasoning_seen, _reasoning_text(token))
        if reasoning_delta:
            self._open("thinking", "Thinking", DIM, ITALIC, BOLD)
            print(
                _style(reasoning_delta, DIM, ITALIC),
                end="",
                flush=True,
            )
            self._reasoning_seen += reasoning_delta

        answer_delta = _delta(self._answer_seen, _message_text(token))
        if answer_delta:
            self._open("answer", "Assistant", BOLD)
            print(answer_delta, end="", flush=True)
            self._answer_seen += answer_delta
            self._printed_answer = True

    def on_completed_message(self, message):
        if isinstance(message, AIMessage):
            reasoning = _reasoning_text(message)
            leftover = _delta(self._reasoning_seen, reasoning)
            if leftover:
                self._open("thinking", "Thinking", DIM, ITALIC, BOLD)
                print(_style(leftover, DIM, ITALIC), end="", flush=True)
                self._reasoning_seen += leftover

            for call in message.tool_calls or []:
                call_id = call.get("id") or f"{call.get('name')}:{json.dumps(call.get('args'), sort_keys=True)}"
                if call_id in self._printed_tool_call_ids:
                    continue
                self._printed_tool_call_ids.add(call_id)
                self._open("tool", f"Using {call.get('name')}", CYAN, BOLD)
                args_text = _format_tool_args(call.get("args"))
                if args_text:
                    print(_style(args_text, CYAN), flush=True)

            answer = _message_text(message)
            leftover_answer = _delta(self._answer_seen, answer)
            if leftover_answer and not message.tool_calls:
                self._open("answer", "Assistant", BOLD)
                print(leftover_answer, end="", flush=True)
                self._answer_seen += leftover_answer
                self._printed_answer = True

        elif isinstance(message, ToolMessage):
            result_id = getattr(message, "tool_call_id", None) or id(message)
            if result_id in self._printed_tool_result_ids:
                return
            self._printed_tool_result_ids.add(result_id)
            name = getattr(message, "name", None) or "tool"
            self._open("tool_result", f"Result from {name}", YELLOW, BOLD)
            print(_style(_truncate(_message_text(message)), DIM), flush=True)

    def finish(self):
        self._end_section()
        if not self._printed_answer and not self._printed_tool_call_ids:
            print(_style("(no assistant text)", DIM), flush=True)


def stream_agent_turn(messages):
    printer = TerminalStreamPrinter()
    last_messages = messages

    print()
    for item in agent.stream(
        {"messages": messages},
        stream_mode=["messages", "updates", "values"],
    ):
        mode, payload = _unpack_stream_item(item)

        if mode == "messages":
            token = payload[0] if isinstance(payload, tuple) else payload
            printer.on_message_chunk(token)

        elif mode == "updates":
            if not isinstance(payload, dict):
                continue
            for update in payload.values():
                if not isinstance(update, dict):
                    continue
                for message in update.get("messages") or []:
                    printer.on_completed_message(message)

        elif mode == "values":
            if isinstance(payload, dict) and payload.get("messages"):
                last_messages = payload["messages"]

    printer.finish()
    return last_messages


# ======================
# Conversation Memory
# ======================
# Keeps the full running history of the conversation (user turns,
# assistant turns, and any tool calls/results in between) so the agent
# has context from earlier in the session on every new invocation.
conversation_history = []

# Optional safety valve: cap how many messages we keep, so very long
# sessions don't blow up token usage / context length. Set to None to
# keep everything.
MAX_HISTORY_MESSAGES = 40


def trim_history(history):
    if MAX_HISTORY_MESSAGES is not None and len(history) > MAX_HISTORY_MESSAGES:
        return history[-MAX_HISTORY_MESSAGES:]
    return history


while True:
    query = input("\nYou: ")

    if query.lower() == "exit":
        break

    conversation_history.append(
        {
            "role": "user",
            "content": query
        }
    )
    conversation_history = trim_history(conversation_history)

    try:
        conversation_history = trim_history(
            stream_agent_turn(conversation_history)
        )

    except Exception as e:
        print("Error:", e)
        # Roll back the user message we just added so a failed turn
        # doesn't corrupt the history with an unanswered question.
        conversation_history.pop()