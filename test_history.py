import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.tools import Tool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing import TypedDict, Annotated

load_dotenv()

def get_weather(location: str):
    """Get the weather for a location."""
    return f"The weather in {location} is sunny."

weather_tool = Tool(name="get_weather", func=get_weather, description="Get weather")
tools = [weather_tool]
tool_node = ToolNode(tools)

model = ChatGoogleGenerativeAI(temperature=0, model="gemini-3.5-flash")
model_with_tools = model.bind_tools(tools)

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

def call_model_node(state: AgentState):
    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        system_msg = SystemMessage(content="You are a helpful assistant.")
        messages = [system_msg] + messages
    
    response = model_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    if state["messages"][-1].tool_calls:
        return "call_tool"
    return END

workflow = StateGraph(AgentState)
workflow.add_node("call_model", call_model_node)
workflow.add_node("call_tool", tool_node) 
workflow.set_entry_point("call_model")
workflow.add_conditional_edges("call_model", should_continue, {"call_tool": "call_tool", END: END})
workflow.add_edge("call_tool", "call_model")
app = workflow.compile()

history = [
    AIMessage(content="Hi! I'm Devesh's AI assistant."),
    HumanMessage(content="hi"),
    AIMessage(content="Hello! How can I help you today?"),
    HumanMessage(content="What is the weather in Paris?")
]

try:
    print("Testing LangGraph with history...")
    output = app.invoke({"messages": history})
    print(output["messages"][-1].content)
except Exception as e:
    print("ERROR:", e)
