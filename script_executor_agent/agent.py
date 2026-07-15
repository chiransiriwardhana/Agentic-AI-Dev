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

You are a helpful AI assistant.

You have two tools.

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
about running a script file.

Examples:

Create a folder in Documents

List files

Check disk usage


Always use tools when execution is requested.

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