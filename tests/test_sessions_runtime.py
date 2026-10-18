import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from devfolio.runtime import Runtime, system_prompt, with_transient_fallback
from devfolio.sessions import ChatSession, RequestLimits, RequestRejected, validate_question


def runtime(settings, responses=None):
    reader = SimpleNamespace(ready=lambda: True, projects=lambda: [{"name": "one"}])
    model = FakeMessagesListChatModel(responses=responses or [AIMessage(content="Hello")])
    return Runtime(reader, None, settings, model=model)


def test_real_graph_tools_preserved_and_tool_result_flow(settings, monkeypatch):
    monkeypatch.setenv("MY_CALENDLY_LINK", "https://calendly.com/owner")
    responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "get_scheduling_link",
                    "args": {"__arg1": "meeting"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Use the scheduling link."),
    ]
    agent = runtime(settings, responses)
    assert {t.name for t in agent.tools} == {
        "get_personal_info",
        "get_scheduling_link",
        "get_linkedin_link",
        "get_resume_link",
        "get_projects",
        "project_retriever",
    }
    result = agent.graph().invoke({"messages": [HumanMessage(content="Schedule a meeting")]})
    tool = next(m for m in result["messages"] if isinstance(m, ToolMessage))
    assert "https://calendly.com/owner" in tool.content
    assert result["messages"][-1].content == "Use the scheduling link."


def test_policy_precedes_untrusted_injection(settings):
    policy = system_prompt("Owner")
    assert "untrusted data" in policy and "Never invent" in policy
    assert "Never disclose credentials" in policy
    # This is policy/architecture verification, not proof of live model robustness.
    assert "execute code" in policy


def test_malformed_tool_calls_fail_safely(settings):
    response = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "get_projects",
                "args": "{broken",
                "id": "invalid",
                "error": "invalid json",
                "type": "invalid_tool_call",
            }
        ],
    )
    with pytest.raises(ValueError, match="Malformed model tool call"):
        runtime(settings, [response]).graph().invoke({"messages": [HumanMessage(content="projects")]})


def test_conversations_isolate_checkpoints_and_reject_cross_thread(settings):
    owner = ChatSession(runtime(settings))
    other = ChatSession(owner.runtime)
    assert "".join(owner.stream("first")) == "Hello"
    assert "".join(other.stream("other")) == "Hello"
    owner_state = owner.graph.get_state({"configurable": {"thread_id": owner.thread_id}})
    other_state = other.graph.get_state({"configurable": {"thread_id": other.thread_id}})
    assert owner_state.values["messages"][0].content == "first"
    assert other_state.values["messages"][0].content == "other"
    with pytest.raises(RequestRejected):
        list(other.stream("steal", thread_id=owner.thread_id))
    restarted = ChatSession(owner.runtime)
    assert not restarted.graph.get_state({"configurable": {"thread_id": owner.thread_id}}).values


def test_expired_session_starts_new_thread(settings):
    session = ChatSession(runtime(settings))
    old = session.thread_id
    session.last_used = time.monotonic() - 1801
    list(session.stream("new"))
    assert session.thread_id != old


class EventRuntime:
    def __init__(self):
        self.closed = 0

    def graph(self, saver):
        def stream(*args, **kwargs):
            try:
                yield AIMessage(content="first "), {"langgraph_node": "call_model"}
                yield AIMessage(content="second"), {"langgraph_node": "call_model"}
            finally:
                self.closed += 1

        return SimpleNamespace(stream=stream)


def test_stream_cancel_timeout_and_cleanup():
    fake = EventRuntime()
    limits = RequestLimits(concurrent=1)
    session = ChatSession(fake, limits)
    original = session.thread_id
    stream = session.stream("question")
    assert next(stream) == "first "
    stream.close()
    assert fake.closed == 1 and session.thread_id != original
    assert "".join(session.stream("next")) == "first second"
    with pytest.raises(TimeoutError):
        list(session.stream("timeout", timeout=-1))
    with pytest.raises(TimeoutError):
        list(session.stream("cancel", cancelled=lambda: True))
    assert fake.closed == 4


def test_rate_and_concurrency_limits():
    limits = RequestLimits(concurrent=1, per_minute=3)
    with limits.acquire():
        with pytest.raises(RequestRejected):
            with limits.acquire():
                pass
    with limits.acquire():
        pass
    with pytest.raises(RequestRejected):
        with limits.acquire():
            pass
    session = ChatSession(EventRuntime())
    for _ in range(6):
        list(session.stream("question"))
    with pytest.raises(RequestRejected):
        list(session.stream("too many"))


@pytest.mark.parametrize("question", ["", "  ", None, "x" * 4001, {}])
def test_input_validation(question):
    with pytest.raises(RequestRejected):
        validate_question(question)


def test_import_has_no_external_calls():
    code = "import socket; socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network during import')); import agent; print('safe import')"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "safe import" in result.stdout


@pytest.mark.parametrize("code,uses_fallback", [(429, True), (503, True), (401, False), (400, False)])
def test_fallback_preserves_rate_limit_recovery_without_retrying_auth(code, uses_fallback):
    import requests
    from langchain_core.runnables import RunnableLambda

    calls = []

    def primary(messages):
        raise requests.HTTPError(response=SimpleNamespace(status_code=code))

    def secondary(messages):
        calls.append(1)
        return AIMessage(content="fallback")

    model = with_transient_fallback(RunnableLambda(primary), RunnableLambda(secondary))
    if uses_fallback:
        assert model.invoke([]).content == "fallback" and calls == [1]
    else:
        with pytest.raises(requests.HTTPError):
            model.invoke([])
        assert calls == []
