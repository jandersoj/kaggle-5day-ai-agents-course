import os
from dotenv import load_dotenv, dotenv_values
load_dotenv() 
import asyncio

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.tools import load_memory, preload_memory
from google.genai import types
print("ADK components imported")

# Config
APP_NAME = "MemoryDemoApp"
USER_ID = "demo_user"

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

# Services — note the () to instantiate them!
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()  # <-- was missing ()

# Agent — load_memory tool lets it query past memories
user_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    name="MemoryDemoAgent",
    instruction="Answer user questions in simple words. Use your memory tool to recall past conversations when relevant.",
    tools=[load_memory],  # <-- gives the agent access to memory
)

# Runner with both services
runner = Runner(
    agent=user_agent,
    app_name=APP_NAME,
    session_service=session_service,
    memory_service=memory_service,
)


async def run_session(
    runner_instance: Runner,
    user_queries: list[str] | str,
    session_id: str = "default",
):
    print(f"\n### Session: {session_id}")

    try:
        session = await session_service.create_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )
    except Exception:
        session = await session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=session_id
        )

    if isinstance(user_queries, str):
        user_queries = [user_queries]

    for query in user_queries:
        print(f"\nUser > {query}")
        query_content = types.Content(role="user", parts=[types.Part(text=query)])

        async for event in runner_instance.run_async(
            user_id=USER_ID, session_id=session.id, new_message=query_content
        ):
            if event.is_final_response() and event.content and event.content.parts:
                text = event.content.parts[0].text
                if text and text != "None":
                    print(f"Model > {text}")


async def main():
    # First conversation
    await run_session(
        runner,
        "My favorite color is blue-green. Can you write a Haiku about it?",
        "conversation-01",
    )

    # Add session to memory so future sessions can recall it
    await memory_service.add_session_to_memory(
        await session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id="conversation-01"
        )
    )

    # Second conversation — agent can now recall the first
    await run_session(
        runner,
        "What is my favorite color?",
        "conversation-02",
    )


asyncio.run(main())