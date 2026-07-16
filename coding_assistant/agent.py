import os

from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from tool import (
    run_script,
    process_shell_tool,
    read_file,
    edit_file,
    write_file,
)

# ======================
# Environment
# ======================

load_dotenv(override=True)

if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY is missing")

# ======================
# Model
# ======================

model = ChatOpenAI(
    model="gpt-5",
    temperature=0
)



# ======================
# Agent
# ======================

agent = create_agent(
    model=model,
    tools=[
        run_script,
        process_shell_tool,
        read_file,
        edit_file,
        write_file,
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

You have five tools available:

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
disk usage, installing packages, running git commands).


AUTONOMOUS DEBUG LOOP:

When the user asks you to fix a bug in an existing file, or to make a
script/program work, follow this loop instead of just guessing:

1. read_file the target file (skip this step only if you already have
   its exact current contents from earlier in this conversation).
2. run_script the file to see the actual current error or behavior, if
   you have not already just seen a fresh run's output.
3. Reason step by step about the root cause using the real error text
   and the real code -- do not guess at line numbers or content you
   have not actually seen.
4. Use edit_file to apply the smallest fix that addresses the root
   cause.
5. run_script again to verify the fix actually resolves the issue.
6. If it still fails, repeat steps 3-5 with the new error, up to 3
   total attempts. If still unresolved after 3 attempts, stop, explain
   what you tried and why it didn't work, and ask the user how they'd
   like to proceed.

Do not claim a fix worked unless you actually re-ran the script and saw
it succeed. Do not fabricate file contents, error messages, or command
output -- always get them from the tools.

"""
)



print("Agent Ready!")
print("----------------")


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
        response = agent.invoke(
            {
                "messages": conversation_history
            }
        )

        # response["messages"] contains the full trace for this invocation
        # (including tool calls). Replace our running history with it so
        # tool call/result messages are preserved for future context too.
        conversation_history = trim_history(response["messages"])

        print("\nAssistant:")
        print(response["messages"][-1].content)

    except Exception as e:
        print("Error:", e)
        # Roll back the user message we just added so a failed turn
        # doesn't corrupt the history with an unanswered question.
        conversation_history.pop()