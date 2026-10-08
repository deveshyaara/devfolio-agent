import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool

load_dotenv()

@tool
def get_weather(location: str):
    """Get the weather for a location."""
    return f"The weather in {location} is sunny."

models_to_test = [
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash",
    "gemma-4-26b-a4b-it",
    "gemini-1.5-flash",  # Just in case it exists but wasn't listed
]

def test_model(model_name):
    print(f"\n--- Testing {model_name} ---")
    try:
        model = ChatGoogleGenerativeAI(temperature=0, model=model_name, max_retries=0)
        model_with_tools = model.bind_tools([get_weather])
        
        print("1. Invoking model to get tool call...")
        msg1 = HumanMessage(content="What is the weather in Paris?")
        ai_msg = model_with_tools.invoke([msg1])
        
        if not ai_msg.tool_calls:
            print("No tool call returned.")
            return
            
        print("2. Sending tool result back...")
        tool_call = ai_msg.tool_calls[0]
        tool_msg = ToolMessage(content="Sunny", tool_call_id=tool_call["id"])
        
        final_response = model_with_tools.invoke([msg1, ai_msg, tool_msg])
        print("Final response:", final_response.content)
        print("SUCCESS")
    except Exception as e:
        print("ERROR:", e)

for m in models_to_test:
    test_model(m)
