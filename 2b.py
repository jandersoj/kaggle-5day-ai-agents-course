# 1. setup
import os
from dotenv import load_dotenv, dotenv_values
import asyncio

from IPython.display import display, Image as IPImage
import base64

load_dotenv() 
print("environment keys loaded")
# os.getenv("GOOGLE_API_KEY")

import uuid
from google.genai import types

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import Runner, InMemoryRunner
from google.adk.sessions import InMemorySessionService

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.tool_context import ToolContext
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from google.adk.apps.app import App, ResumabilityConfig
from google.adk.tools.function_tool import FunctionTool
print("ADK components imported successfully.")

# in case of errors, we want to automatically retry the request
retry_config=types.HttpRetryOptions(
    attempts = 5, # max number of attempts 
    exp_base = 7, # delay multiplier
    initial_delay = 1, # in seconds, delay before first retry
    http_status_codes = [429, 500, 503, 504] # retry upon recieving these
)

# 2. MCP, Model Context Protocol
# using the Everything MPC Server for demo

# MCP integration w ES
mcp_image_server = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=[
                "-y",
                "@modelcontextprotocol/server-everything",
            ],
            tool_filter=["getTinyImage"]
        ),
        timeout=30,
    )
)
print("mcp tool created")

image_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    name="image_agent",
    instruction="Use the MCP toll to generate images for user queries",
    tools=[mcp_image_server],
)

# async def main():
#     runner = InMemoryRunner(agent = image_agent)
#     print("runner created")

#     # user_question = input("Ask the agent a question: ")
#     response = await runner.run_debug("provide a sample tiny image", verbose=True)
#     # print(response)
#     for event in response:
#         if event.content and event.content.parts:
#             for part in event.content.parts:
#                 if hasattr(part, "function_response") and part.function_response:
#                     for item in part.function_response.response.get("content", []):
#                         if item.get("type") == "image":
#                             display(IPImage(data=base64.b64decode(item["data"])))
# asyncio.run(main())

# 3. Human-in-the-loop

LARGE_ORDER_THRESHOLD = 5


def place_shipping_order(
    num_containers: int, destination: str, tool_context: ToolContext
) -> dict:
    """Places a shipping order. Requires approval if ordering more than 5 containers (LARGE_ORDER_THRESHOLD).

    Args:
        num_containers: Number of containers to ship
        destination: Shipping destination

    Returns:
        Dictionary with order status
    """

    # SCENARIO 1: Small orders auto-approve
    if num_containers <= LARGE_ORDER_THRESHOLD:
        return {
            "status": "approved",
            "order_id": f"ORD-{num_containers}-AUTO",
            "num_containers": num_containers,
            "destination": destination,
            "message": f"Order auto-approved: {num_containers} containers to {destination}",
        }
    # SCENARIO 2: Large order requiriing human approval
    if not tool_context.tool_confirmation:
        tool_context.request_confirmation(
            hint=f"Large order: {num_containers} containers to {destination}. Do you want to approve?",
            payload={"num_containers": num_containers, "destination": destination},
        )
        return {
            "status": "pending",
            "message": f"Order for {num_containers} containers requires approval",
        }
    #SCENARIO 3: called again and now resuming
    if tool_context.tool_confirmation.confirmed:
        return {
            "status": "approved",
            "order_id": f"ORD-{num_containers}-HUMAN",
            "num_containers": num_containers,
            "destination": destination,
            "message": f"Order approved: {num_containers} containers to {destination}",
        }
    else:
        return {
            "status": "rejected",
            "message": f"Order rejected: {num_containers} containers to {destination}",
        }
print("long-running functions created")

# Create shipping agent with pausable tool
shipping_agent = LlmAgent(
    name="shipping_agent",
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    instruction="""You are a shipping coordinator assistant.
  
  When users request to ship containers:
   1. Use the place_shipping_order tool with the number of containers and destination
   2. If the order status is 'pending', inform the user that approval is required
   3. After receiving the final result, provide a clear summary including:
      - Order status (approved/rejected)
      - Order ID (if available)
      - Number of containers and destination
   4. Keep responses concise but informative
  """,
    tools=[FunctionTool(func=place_shipping_order)],
)
print("shipping agent created")

shipping_app = App(
    name="shipping_coordinator",
    root_agent=shipping_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
print("resumable app created")

session_service = InMemorySessionService()

shipping_runner = Runner(
    app=shipping_app,
    session_service=session_service,
)
print("shipping runner created")

#SECTION 4: building the workflow

def check_for_approval(events):
    """
    Check if events contain an approval request.
    
    Returns:
        dict with approval details or None
    """
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if (
                    part.function_call
                    and part.function_call.name == "adk_request_confirmation"
                ):
                    return {
                        "approval_id": part.function_call.id,
                        "invocation_id": event.invocation_id
                    }
    return None

def print_agent_response(events):
    """Print agent's text responses from events"""
    for event in events:
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    print(f"Agent > {part.text}")

def create_approval_response(approval_info, approved):
    """Create approval response message"""
    confirmation_response = types.FunctionResponse(
        id=approval_info["approval_id"],
        name="adk_request_confirmation",
        response={"confirmed": approved},
    )
    return types.Content(
        role="user", parts=[types.Part(function_response=confirmation_response)]
    )
print("helper functions defined")

async def run_shipping_workflow(query: str, auto_approve: bool = True):
    """Runs a shipping workdlow with approval handling
    
    Args:
        query: User's shipping request
        auto_approve: Whether to auto-approve large orders (simulates human decision)
    """

    print(f"\n{'='*60}")
    print(f"User > {query}\n")

    session_id = f"order_{uuid.uuid4().hex[:8]}"

    await session_service.create_session(
        app_name="shipping_coordinator", user_id="test_user", session_id=session_id
    )

    query_content = types.Content(role="user", parts=[types.Part(text=query)])
    events = []

    # step 1: send initial request to agent
    async for event in shipping_runner.run_async(
        user_id="test_user", session_id=session_id, new_message=query_content
    ):
        events.append(event)
    # step 2: loop through events and check for "ask_request_confirmation" 
    approval_info = check_for_approval(events)

    # step 3: if it is present, handle approval workflow
    if approval_info:
        print(f"pausing for approval...")
        print(f"human decision: {'APPROVE' if auto_approve else 'REJECT'}\n")
        async for event in shipping_runner.run_async(
            user_id="test_user",
            session_id=session_id,
            new_message=create_approval_response(
                approval_info, auto_approve
            ),  # send human decision here
            invocation_id=approval_info[
                "invocation_id"
            ],  # tells ADK to RESUME
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Agent > {part.text}")
    else:
        print_agent_response(events)

    print(f"{'='*60}\n")
print("workflow function ready")

async def main():
    # Demo 1: It's a small order. Agent receives auto-approved status from tool
    await run_shipping_workflow("Ship 3 containers to Singapore")

    # Demo 2: Workflow simulates human decision: APPROVE
    await run_shipping_workflow("Ship 10 containers to Rotterdam", auto_approve=True)

    # Demo 3: Workflow simulates human decision: REJECT
    await run_shipping_workflow("Ship 8 containers to Los Angeles", auto_approve=False)


asyncio.run(main())