"""Optional, billable Gemini smoke test; never part of offline tests or startup."""

import json
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI

from devfolio.config import Settings, required
from devfolio.embeddings import GoogleEmbeddings


def main():
    load_dotenv()
    settings = Settings.from_env()
    results = []
    embeddings = None
    try:
        embeddings = GoogleEmbeddings(settings, required("GOOGLE_API_KEY"))
        vector = embeddings.documents(["A portfolio application using Python and PostgreSQL."])[0]
        results.append(
            {"check": "embedding", "status": "passed", "dimensions": len(vector), "model": settings.model}
        )
    except Exception as exc:
        results.append({"check": "embedding", "status": "failed", "error_type": type(exc).__name__})
    finally:
        if embeddings:
            embeddings.close()
    tool = Tool(
        name="get_scheduling_link",
        func=lambda query="": "https://calendly.com/example",
        description="Get a scheduling link to arrange a meeting.",
    )
    for model_name in filter(
        None,
        [os.getenv("CHAT_MODEL", "gemini-3.5-flash"), os.getenv("FALLBACK_CHAT_MODEL", "gemma-4-26b-a4b-it")],
    ):
        try:
            model = ChatGoogleGenerativeAI(
                model=model_name, temperature=0, max_retries=0, timeout=15, max_output_tokens=512
            ).bind_tools([tool])
            question = HumanMessage(
                content="Use get_scheduling_link to arrange a meeting. Call the tool with query='meeting'."
            )
            response = model.invoke([question])
            if not response.tool_calls or response.invalid_tool_calls:
                raise ValueError("Native tool call missing or malformed")
            call = response.tool_calls[0]
            final = model.invoke(
                [question, response, ToolMessage(content=tool.invoke(call["args"]), tool_call_id=call["id"])]
            )
            if not final.content:
                raise ValueError("No final response after tool result")
            results.append({"check": "tool_roundtrip", "model": model_name, "status": "passed"})
        except Exception as exc:
            results.append(
                {
                    "check": "tool_roundtrip",
                    "model": model_name,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                }
            )
    print(json.dumps(results))
    return 1 if any(r["status"] == "failed" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
