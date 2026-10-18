import logging
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

log = logging.getLogger(__name__)


class RequestRejected(ValueError):
    pass


def validate_question(question):
    if (
        not isinstance(question, str)
        or not question.strip()
        or len(question) > 4000
        or len(question.encode()) > 16000
    ):
        raise RequestRejected("Please enter a message of 1–4000 characters.")
    return question.strip()


class RequestLimits:
    def __init__(self, concurrent=4, per_minute=120):
        self.slots = threading.BoundedSemaphore(concurrent)
        self.lock = threading.Lock()
        self.requests = deque()
        self.per_minute = per_minute

    @contextmanager
    def acquire(self):
        with self.lock:
            current = time.monotonic()
            while self.requests and self.requests[0] < current - 60:
                self.requests.popleft()
            if len(self.requests) >= self.per_minute:
                raise RequestRejected("The assistant is busy. Please try again in a minute.")
            self.requests.append(current)
        if not self.slots.acquire(blocking=False):
            raise RequestRejected("The assistant is busy. Please try again shortly.")
        try:
            yield
        finally:
            self.slots.release()


LIMITS = RequestLimits()


def text_content(content):
    if isinstance(content, str):
        return content
    return "".join(
        item if isinstance(item, str) else item.get("text", "")
        for item in content
        if isinstance(item, (str, dict))
    )


class ChatSession:
    """A capability owned by one Streamlit session. No global thread lookup exists."""

    def __init__(self, runtime, limits=None):
        self.runtime = runtime
        self.limits = limits or LIMITS
        self.requests = deque()
        self._busy = threading.Lock()
        self.reset()

    def reset(self):
        self.thread_id = str(uuid.uuid4())
        self.graph = self.runtime.graph(MemorySaver())
        self.last_used = time.monotonic()
        self.turns = 0

    def expire_if_needed(self):
        if time.monotonic() - self.last_used > 1800 or self.turns >= 12:
            self.reset()
            return True
        return False

    def stream(self, question, thread_id=None, timeout=60, cancelled=None):
        question = validate_question(question)
        if thread_id is not None and thread_id != self.thread_id:
            raise RequestRejected("Conversation does not belong to this session.")
        if not self._busy.acquire(blocking=False):
            raise RequestRejected("A message is already running in this conversation.")
        events = None
        complete = False
        started, request_id = time.monotonic(), str(uuid.uuid4())
        try:
            self.expire_if_needed()
            while self.requests and self.requests[0] < started - 60:
                self.requests.popleft()
            if len(self.requests) >= 6:
                raise RequestRejected("Please wait a minute before sending more messages.")
            self.requests.append(started)
            with self.limits.acquire():
                events = self.graph.stream(
                    {"messages": [HumanMessage(content=question)]},
                    config={
                        "configurable": {"thread_id": self.thread_id, "deadline": started + timeout},
                        "recursion_limit": 12,
                    },
                    stream_mode="messages",
                )
                first = True
                for message, metadata in events:
                    if (cancelled and cancelled()) or time.monotonic() - started > timeout:
                        raise TimeoutError("Request stopped or timed out")
                    if metadata.get("langgraph_node") != "call_model":
                        continue
                    text = text_content(message.content)
                    if text:
                        if first:
                            log.info(
                                "first_token",
                                extra={
                                    "request_id": request_id,
                                    "duration_ms": round((time.monotonic() - started) * 1000),
                                },
                            )
                            first = False
                        yield text
                complete = True
                self.turns += 1
                self.last_used = time.monotonic()
        finally:
            try:
                if events is not None:
                    events.close()
            finally:
                if not complete:
                    # Discard possibly incomplete tool-call state after interruption/failure.
                    self.reset()
                self._busy.release()
            log.info(
                "chat_finished",
                extra={
                    "request_id": request_id,
                    "completed": complete,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                },
            )
