import os

from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from tool import (
    run_python_script,
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
        run_python_script,
        process_shell_tool
    ],

    system_prompt="""

You are a helpful AI assistant.

You have two tools.

1. run_python_script

Use when the user wants to execute Python scripts.

Example:

Run train.py


2. process_shell_tool

Use when the user wants operating system actions.

Examples:

Create a folder in Documents

List files

Check disk usage


Always use tools when execution is requested.

"""
)



print("Agent Ready!")
print("----------------")


while True:
    query = input("\nYou: ")

    if query.lower() == "exit":
        break
    try:
        response = agent.invoke(
            {
                "messages":
                [
                    {
                        "role": "user",
                        "content": query
                    }
                ]
            }

        )

        print("\nAssistant:")
        print(response["messages"][-1].content)

    except Exception as e:
        print("Error:", e)