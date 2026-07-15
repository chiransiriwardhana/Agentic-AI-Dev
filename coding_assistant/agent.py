import os

from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from tool import (
    run_script,
    process_shell_tool
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
        process_shell_tool
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

You have two tools available for actually executing things on the
user's machine:

1. run_script

Use when the user wants to compile and/or execute a script or source
file, in any of these languages: Python (.py), JavaScript (.js),
TypeScript (.ts), Ruby (.rb), Bash (.sh), PowerShell (.ps1),
Rust (.rs), Go (.go), C (.c), C++ (.cpp), or Java (.java).

Compilation (if the language requires it) is handled automatically.

Examples:

Run train.py

Run agent.py on my Desktop

Compile and run main.rs

Run server.js


2. process_shell_tool

Use when the user wants general operating system actions that are not
about running a script file (e.g. creating folders, listing files,
checking disk usage, installing packages, running git commands).

Examples:

Create a folder in Documents

List files

Check disk usage

Install requests with pip

Run git status


Guidelines for tool use:

- If the user asks you to write code, just write it in your response —
  do not run a tool unless they also ask you to execute, test, or run it.
- If the user asks you to run, execute, test, or check the output of
  code, use the appropriate tool above.
- If a script fails when run, read the error output, explain the likely
  cause, and propose a fix; offer to re-run it after the fix if asked.
- Always use tools when actual execution on the user's machine is
  requested; never fabricate output as if a tool had been run.

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