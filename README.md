## Script/Command Execution Agent

The Script Executor Agent is capable of executing shell commands provided through natural language prompts and running Python scripts. It provides functionalities similar to coding assistant agents.

Examples:

1. Folder creation using a natural language prompt:
    Prompt:
    “Can you create a folder named created-by-agent on the Desktop?”
    The agent interprets the request and executes the required shell command to create the folder on the user’s Desktop.
2. Python script execution:
    Prompt:
    “Can you run the pi_value_compute.py file?”
    The agent executes the Python script and displays the output directly in the terminal. The pi_value_compute.py script calculates the value of π up to 1000 decimal places.

The Script Executor Agent demonstrates agentic capabilities by interpreting user instructions, selecting appropriate tools, executing external actions, and returning the results.

## SQL Agent

This code implements a SQL Database Agent using LangGraph + LangChain. The agent allows a user to ask questions in natural language, converts those questions into SQL queries using an LLM, executes them on a database, checks the SQL for errors, and returns the answer.

User question → LLM reasoning → SQL generation → SQL validation → Database execution → Answer


                 User
                  |
                  |
        "Which genre has longest tracks?"
                  |
                  v
              LangGraph Agent
                  |
        +---------+----------+
        |                    |
        v                    v
  Database Tools        GPT-4o Reasoning
        |                    
        v 
   SQLite Chinook DB
        |                    
        v 
     SQL Result
        |
        v
      Answer
