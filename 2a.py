
# 1. setup
import os
from dotenv import load_dotenv, dotenv_values
import asyncio
load_dotenv() 
print("environment keys loaded")
# os.getenv("GOOGLE_API_KEY")

from google.genai import types

from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import google_search, AgentTool, ToolContext
from google.adk.code_executors import BuiltInCodeExecutor

print("ADK components imported successfully.")


# in case of errors, we want to automatically retry the request
retry_config=types.HttpRetryOptions(
    attempts = 5, # max number of attempts 
    exp_base = 7, # delay multiplier
    initial_delay = 1, # in seconds, delay before first retry
    http_status_codes = [429, 500, 503, 504] # retry upon recieving these
)

#define helper function
def show_python_code_and_resule(response):
    for i in range(len(response)):
    #check to make sure its valid...
        if(
            (response[i].content.parts)
            and (response[i].content.parts[0])
            and (response[i].content.parts[0].function_response)
            and (response[i].content.parts[0].function_response.response)
        ):
            response_code = response[i].content.parts[0].function_response.response
            if "result" in response_code and response_code["result"] != "```":
                if "tool_code" in response_code["result"]:
                    print(
                        "generated Python code >> ", response_code["result"].replace("tool code", ""),
                    )
                else:
                    print("generated Python response >> ", response_code["result"])

print("helper function defined")

# 2. Custom Tools

#just making more helper functions i suppose
def get_fee_for_payment_method(method: str) -> dict:
    """Looks up the transaction fee percentage for a given payment method.

    This tool simulates looking up a company's internal fee structure based on
    the name of the payment method provided by the user.

    Args:
        method: The name of the payment method. It should be descriptive,
                e.g., "platinum credit card" or "bank transfer".

    Returns:
        Dictionary with status and fee information.
        Success: {"status": "success", "fee_percentage": 0.02}
        Error: {"status": "error", "error_message": "Payment method not found"}
    """
    # very important to tell it what you want ^

    fee_database = {
        "platinum card": 0.02,
        "gold card": 0.035,
        "bank transfer": 0.01
    }

    fee = fee_database.get(method.lower())
    if fee is not None:
        return {"status": "success", "fee_percentage": fee}
    else: 
        return {"status": "error",
                "error_message": f"payment method '{method}' not found",
                }

print("fee lookup function created")
print(f"test: {get_fee_for_payment_method('platinum card')}")


#another helper:
def get_exchange_rate(base_currency: str, target_currency: str) -> dict:
    """Looks up and returns the exchange rate between two currencies.

    Args:
        base_currency: The ISO 4217 currency code of the currency you
                       are converting from (e.g., "USD").
        target_currency: The ISO 4217 currency code of the currency you
                         are converting to (e.g., "EUR").

    Returns:
        Dictionary with status and rate information.
        Success: {"status": "success", "rate": 0.93}
        Error: {"status": "error", "error_message": "Unsupported currency pair"}
    """

    # static data simulating a live exchange rate API
    # this would call something like: requests.get("api.exchangerates.com")
    rate_database = {
        "usd": {
            "eur": 0.93,  # Euro
            "jpy": 157.50,  # Japanese Yen
            "inr": 83.58,  # Indian Rupee
        }
    }

    # input validation and processing
    base = base_currency.lower()
    target = target_currency.lower()

    # return structured result and status
    rate = rate_database.get(base, {}).get(target)
    if rate is not None:
        return {"status": "success", "rate": rate}
    else:
        return {
            "status": "error",
            "error_message": f"Unsupported currency pair: {base_currency}/{target_currency}",
        }


print("exchange rate function created")
print(f"test: {get_exchange_rate('USD', 'EUR')}")


# #a currency agent to make use of these helpers:
# currency_agent = LlmAgent(
#     name = "currency_agent",
#     model = Gemini(
#         model = "gemini-2.5-flash-lite", 
#         retry_options = retry_config),
#     instruction = """You are a smart currency conversion assistant.

#     For currency conversion requests:
#     1. Use `get_fee_for_payment_method()` to find transaction fees
#     2. Use `get_exchange_rate()` to get currency conversion rates
#     3. Check the "status" field in each tool's response for errors
#     4. Calculate the final amount after fees based on the output from `get_fee_for_payment_method` and `get_exchange_rate` methods and provide a clear breakdown.
#     5. First, state the final converted amount.
#         Then, explain how you got that result by showing the intermediate amounts. Your explanation must include: the fee percentage and its
#         value in the original currency, the amount remaining after the fee, and the exchange rate used for the final conversion.

#     If any tool returns status "error", explain the issue to the user clearly.
#     """,
#     tools = [get_fee_for_payment_method, get_exchange_rate],
# 
# print("currency agent created with helper tools")
# print("avaliable tools:")
# print("  • get_fee_for_payment_method - Looks up company fee structure")
# print("  • get_exchange_rate - Gets current exchange rates")

# #and once again we make a runner to orchestrate
# async def main():
#     currency_runner = InMemoryRunner(agent = currency_agent)
#     print("runner created")

#     user_question = input("Ask the agent a question: ")
#     response = await currency_runner.run_debug(user_question)
#     print(response)
    
# asyncio.run(main())

# 3. Improving Agent Reliability with Code (they are bad at math)



# thus we create:
calculation_agent = LlmAgent(
    name = "CalculationAgent",
    model = Gemini(
        model = "gemini-2.5-flash-lite", 
        retry_options = retry_config),
    instruction = """You are a specialized calculator that ONLY responds with Python code. You are forbidden from providing any text, explanations, or conversational responses.
 
     Your task is to take a request for a calculation and translate it into a single block of Python code that calculates the answer.
     
     **RULES:**
    1.  Your output MUST be ONLY a Python code block.
    2.  Do NOT write any text before or after the code block.
    3.  The Python code MUST calculate the result.
    4.  The Python code MUST print the final result to stdout.
    5.  You are PROHIBITED from performing the calculation yourself. Your only job is to generate the code that will perform the calculation.
   
    Failure to follow these rules will result in an error.
       """,
    code_executor = BuiltInCodeExecutor(),  # the built-in Code Executor Tool gives the agent code execution capabilities
)

#and we replace our silly old agent with
enhanced_currency_agent = LlmAgent(
    name = "enhanced_currency_agent",
    model = Gemini(
        model = "gemini-2.5-flash-lite",
        retry_options = retry_config),
    # updated instructions
    instruction = """You are a smart currency conversion assistant. You must strictly follow these steps and use the available tools.

  For any currency conversion request:

   1. Get Transaction Fee: Use the get_fee_for_payment_method() tool to determine the transaction fee.
   2. Get Exchange Rate: Use the get_exchange_rate() tool to get the currency conversion rate.
   3. Error Check: After each tool call, you must check the "status" field in the response. If the status is "error", you must stop and clearly explain the issue to the user.
   4. Calculate Final Amount (CRITICAL): You are strictly prohibited from performing any arithmetic calculations yourself. You must use the calculation_agent tool to generate Python code that calculates the final converted amount. This 
      code will use the fee information from step 1 and the exchange rate from step 2.
   5. Provide Detailed Breakdown: In your summary, you must:
       * State the final converted amount.
       * Explain how the result was calculated, including:
           * The fee percentage and the fee amount in the original currency.
           * The amount remaining after deducting the fee.
           * The exchange rate applied.
    """,
    tools = [
        get_fee_for_payment_method,
        get_exchange_rate,
        AgentTool(agent = calculation_agent),  # Using another agent as a tool
    ],
)

print("enhanced currency agent created")
print("new capability: delegate calculations to specialist agent")
print("Tool types used:")
print("  • Function Tools (fees, rates)")
print("  • Agent Tool (calculation specialist)")

#finally, another runner


#and here we make a runner to orchestrate
async def main():
    enhanced_runner = InMemoryRunner(agent = enhanced_currency_agent)
    print("runner created")

    user_question = input("Ask the agent a question: ")
    response = await enhanced_runner.run_debug(user_question)
    print(response)
    
asyncio.run(main())