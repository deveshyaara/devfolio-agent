import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
import json

load_dotenv()

@tool
def get_all_project_contexts():
    """Returns ALL project README files at once for synthesis and general questions."""
    return "Here are the projects: project1, project2."

model = ChatGoogleGenerativeAI(temperature=0, model="gemini-3.5-flash")
model_with_tools = model.bind_tools([get_all_project_contexts])

print("Invoking model...")
msg = HumanMessage(content="list the projects")
try:
    ai_msg = model_with_tools.invoke([msg])
    print("Tool calls:", ai_msg.tool_calls)
    if ai_msg.tool_calls:
        print("Sending tool result back...")
        tool_call = ai_msg.tool_calls[0]
        tool_msg = ToolMessage(content="Result", tool_call_id=tool_call["id"])
        final_response = model_with_tools.invoke([msg, ai_msg, tool_msg])
        print("Success!")
except Exception as e:
    print("ERROR:", e)
