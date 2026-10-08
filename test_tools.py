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

def test_model(model_name):
    print(f"\n--- Testing {model_name} ---")
    try:
        model = ChatGoogleGenerativeAI(temperature=0, model=model_name)
        model_with_tools = model.bind_tools([get_weather])
        
        print("1. Invoking model to get tool call...")
        msg1 = HumanMessage(content="What is the weather in Paris?")
        ai_msg = model_with_tools.invoke([msg1])
        print("AI Message tool_calls:", ai_msg.tool_calls)
        
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

for m in ["gemini-flash-latest", "gemini-pro-latest"]:
    test_model(m)
