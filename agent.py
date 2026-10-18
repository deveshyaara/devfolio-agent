"""Portfolio agent entry point. Importing this module performs no ingestion or API calls."""

import os

from dotenv import load_dotenv

from devfolio.logging import configure_logging
from devfolio.runtime import get_runtime
from devfolio.sessions import ChatSession

load_dotenv()
configure_logging()
MY_NAME = os.getenv("MY_NAME", "the portfolio owner")
MY_PROFILE_PIC_URL = os.getenv("MY_PROFILE_PIC_URL", "https://placehold.co/400x400")
MY_LINKEDIN_URL = os.getenv("MY_LINKEDIN_URL")
MY_RESUME_URL = os.getenv("MY_RESUME_URL")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")


def create_project_retriever():
    return get_runtime().retrieval


def run_chat(question, thread_id=None, *, session=None):
    """CLI compatibility. Pass a session to retain an anonymous conversation."""
    session = session or ChatSession(get_runtime())
    return "".join(session.stream(question, thread_id=thread_id))


class LazyAgent:
    def invoke(self, inputs, config=None):
        # Compatibility for manual diagnostics; deliberately stateless.
        return get_runtime().graph().invoke(inputs, config=config)


app = LazyAgent()


if __name__ == "__main__":
    session = ChatSession(get_runtime())
    while question := input("You (empty line exits): ").strip():
        try:
            print(run_chat(question, session=session))
        except Exception:
            print("The assistant is temporarily unavailable. Please try again later.")
