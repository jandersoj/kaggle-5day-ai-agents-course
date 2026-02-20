import os
import warnings
import logging
import asyncio

# Suppress warnings
warnings.filterwarnings("ignore")
logging.getLogger("google").setLevel(logging.ERROR)

from dotenv import load_dotenv
load_dotenv()

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.tools import load_memory
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

# Services
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

# Agent
user_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    name="MemoryDemoAgent",
    instruction="""You are a helpful assistant.
At the START of every response, you MUST call the load_memory tool with a relevant search query to retrieve past conversation context.
Do this before answering anything. If memory returns results, use them in your answer.""",
    tools=[load_memory],
)

# Runner
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
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text and part.text.strip():
                        print(f"Model > {part.text}")


async def main():
    await run_session(
        runner,
        "My favorite color is blue-green. Can you write a Haiku about it?",
        "conversation-01",
    )

    print("Getting session...")
    session = await session_service.get_session(
        app_name=APP_NAME, user_id=USER_ID, session_id="conversation-01"
    )
    print(f"Got session, events: {len(session.events)}")

    print("Adding to memory...")
    await memory_service.add_session_to_memory(session)
    print("Memory saved!")

    print("Memory store:", memory_service._session_events)

    await run_session(
        runner,
        "What is my favorite color?",
        "conversation-02",
    )

asyncio.run(main())
