import os
from dotenv import load_dotenv, dotenv_values
import asyncio
load_dotenv() 
print("environment keys loaded")
# os.getenv("GOOGLE_API_KEY")

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import google_search
from google.genai import types
print("ADK components imported")

#in case of errors, we want to automatically retry the request
retry_config=types.HttpRetryOptions(
    attempts = 5, #max number of attempts 
    exp_base = 7, #delay multiplier
    initial_delay = 1, #in seconds, delay before first retry
    http_status_codes = [429, 500, 503, 504] #retry upon recieving these
)

#here we define our root agent
root_agent = Agent(
    name = "weird_little_guy",
    model = Gemini(
        model = "gemini-2.5-flash-lite",
        retry_options = retry_config
    ),
    description = "a weird little guy",
    instruction = "you are a helpful assistant who answers in riddles or Jeopardy questions. Use Google Search for current info or if unsure.",
    tools = [ google_search ]
)
print("root agent defined")

#and here we make a runner to orchestrate
async def main():
    runner = InMemoryRunner(agent = root_agent)
    print("runner created")

    user_question = input("Ask the agent a question: ")
    response = await runner.run_debug(user_question)
    print(response)

asyncio.run(main())