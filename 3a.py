#memory management, sessions

# 1. setup
import os
from dotenv import load_dotenv, dotenv_values
import asyncio

from typing import Any, Dict

from google.adk.agents import Agent, LlmAgent
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.models.google_llm import Gemini
from google.adk.sessions import DatabaseSessionService
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.tools.tool_context import ToolContext
from google.genai import types
print("adk imported")

load_dotenv() 

APP_NAME = "default"
USER_ID = "default"
MODEL_NAME = "gemini-2.5-flash-lite"

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

# init the agent
# root_agent = Agent(
#     model=Gemini(model=MODEL_NAME, retry_options=retry_config),
#     name="text_chat_bot",
#     description="A text chatbot",
# )

# session_service = InMemorySessionService()
# runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

# print("stateful agent initialized!")

# the actual logic
async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str = None,
    session_name: str = "default",
):
    print(f"\n### Session: {session_name}")
    app_name = runner_instance.app_name

    try:
        session = await session_service.create_session(
            app_name=app_name,
            user_id=USER_ID,
            session_id=session_name,
        )
        print("Created session")
    except Exception:
        session = await session_service.get_session(
            app_name=app_name,
            user_id=USER_ID,
            session_id=session_name,
        )
        print("Got existing session")

    if not user_queries:
        print("No queries!")
        return

    if isinstance(user_queries, str):
        user_queries = [user_queries]

    for query in user_queries:
        print(f"\nUser > {query}")
        message = types.Content(role="user", parts=[types.Part(text=query)])

        async for event in runner_instance.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=message,
        ):
            # Only print final agent text responses
            if not event.is_final_response():
                continue
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:  # safely check text exists and is non-empty
                        print(f"{MODEL_NAME} > {part.text}")


# async def main():
#     await run_session(
#         runner,
#         [
#             "Hi, I am Sam! What is the capital of United States?",
#             "Hello! What is my name?",
#         ],
#         "stateful-agentic-session",
#     )


# asyncio.run(main())

# 3. Persistent sessions

chatbot_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    name="text_chat_bot",
    description="A text chatbot with persistent memory",
)

# Step 2: Switch to DatabaseSessionService
# SQLite database will be created automatically
db_url = "sqlite:///my_agent_data.db"  # Local SQLite file
session_service = DatabaseSessionService(db_url=db_url)

# Step 3: Create a new runner with persistent storage
runner = Runner(agent=chatbot_agent, app_name=APP_NAME, session_service=session_service)

print("upgraded to persistent sessions!")
print(f"   - Database: my_agent_data.db")
print(f"   - Sessions will survive restarts!")



import sqlite3

def check_data_in_db():
    with sqlite3.connect("my_agent_data.db") as connection:
        cursor = connection.cursor()
        result = cursor.execute(
            "select app_name, session_id, author, content from events"
        )
        print([_[0] for _ in result.description])
        for each in result.fetchall():
            print(each)


check_data_in_db()


async def main():
    await run_session(
        runner,
        ["Hi, I am Sam! What is the capital of the United States?", "Hello! What is my name?"],
        "test-db-session-01",
    )


asyncio.run(main())

# 4. context compaction


research_app_compacting = App(
    name="research_app_compacting",
    root_agent=chatbot_agent,
    # the new part:
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,  # Trigger compaction every 3 invocations
        overlap_size=1,  # Keep 1 previous turn for context
    ),
)

db_url = "sqlite:///my_agent_data.db"  # Local SQLite file
session_service = DatabaseSessionService(db_url=db_url)

# Create a new runner 
research_runner_compacting = Runner(
    app=research_app_compacting, session_service=session_service
)

print("research app upgraded with events compaction")

