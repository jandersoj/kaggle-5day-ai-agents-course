
# 1. setup
import os
from dotenv import load_dotenv, dotenv_values
import asyncio
load_dotenv() 
print("environment keys loaded")
# os.getenv("GOOGLE_API_KEY")

from google.adk.agents import Agent, SequentialAgent, ParallelAgent, LoopAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import AgentTool, FunctionTool, google_search
from google.genai import types
print("ADK components imported")

# in case of errors, we want to automatically retry the request
retry_config=types.HttpRetryOptions(
    attempts = 5, # max number of attempts 
    exp_base = 7, # delay multiplier
    initial_delay = 1, # in seconds, delay before first retry
    http_status_codes = [429, 500, 503, 504] # retry upon recieving these
)

# 2. Research & Summarization System

# research agent, uses google_search tool
research_agent = Agent(
    name = "ResearchAgent",
    model = Gemini(
        model = "gemini-2.5-flash-lite",
        retry_options = retry_config
    ),
    instruction = """You are a specialized research agent. Your only job is to use the google_search tool 
    to find 2-3 pieces of relevant information on the given topic and present the findings with citations.""",
    tools = [google_search],
    output_key = "research_findings",  # the result will be stored in the session state with this key
)
print("research_agent created.")

# summary agent, no tools
summary_agent = Agent(
    name = "SummaryAgent",
    model = Gemini(
        model = "gemini-2.5-flash-lite",
        retry_options = retry_config
    ),
    instruction = """Read the provided research findings: {research_findings}. 
    Create a concise summary as a bulleted list with 3-5 key points.""",
    output_key="final_summary",
)
print("summary_agent created")

#root agent to manage both
root_agent = Agent(
    name = "RootAgent", 
    model = Gemini(
        model = "gemini-2.5-flash-lite",
        retry_options = retry_config
    ), 
    instruction = """You are a research coordinator. Your goal is to answer the user's query by orchestrating a workflow.
    1. First, you MUST call the `ResearchAgent` tool to find relevant information on the topic provided by the user.
    2. Next, after receiving the research findings, you MUST call the `SummarizerAgent` tool to create a concise summary.
    3. Finally, present the final summary clearly to the user as your response.""",
    # We wrap the sub-agents in `AgentTool` to make them callable tools for the root agent.
    tools = [AgentTool(research_agent), AgentTool(summary_agent)],
)
print("root agent created")


#and here we make a runner to orchestrate
async def main():
    runner = InMemoryRunner(agent = root_agent)
    print("runner created")

    user_question = input("Ask the agent a question: ")
    response = await runner.run_debug(user_question)
    print(response)
    
asyncio.run(main())