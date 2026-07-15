from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from tool import run_python_script

load_dotenv()

model = ChatOpenAI(
    model="gpt-5",
    temperature=0
)

agent = create_agent(
    model=model,
    tools=[run_python_script],
    system_prompt="""
You are a helpful AI assistant.

If the user asks to execute a python script,
ALWAYS use the run_python_script tool.

Only pass the filename.

Examples:

hello.py
train.py
test.py
"""
)

print("Agent Ready!")
print("----------------")

while True:

    query = input("\nYou: ")

    if query.lower() == "exit":
        break

    response = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": query
                }
            ]
        }
    )

    print("\nAssistant:")

    print(response["messages"][-1].content)