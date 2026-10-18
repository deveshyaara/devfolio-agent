from pathlib import Path
from types import SimpleNamespace

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from devfolio.runtime import Runtime

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def test_streamlit_request_path_and_session_isolation(settings, monkeypatch):
    import devfolio.runtime

    runtime = Runtime(
        SimpleNamespace(ready=lambda: True, projects=lambda: []),
        None,
        settings,
        model=FakeMessagesListChatModel(responses=[AIMessage(content="Documented answer.")]),
    )
    monkeypatch.setattr(devfolio.runtime, "get_runtime", lambda: runtime)
    first = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not first.exception
    first.chat_input[0].set_value("Tell me about the portfolio").run()
    assert not first.exception and first.markdown[-1].value == "Documented answer."
    second = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert first.session_state["chat_session"].thread_id != second.session_state["chat_session"].thread_id
    assert len(second.session_state["messages"]) == 1


def test_streamlit_safe_configuration_failure(monkeypatch):
    import devfolio.runtime

    def fail():
        raise ValueError("private-database-password")

    monkeypatch.setattr(devfolio.runtime, "get_runtime", fail)
    page = AppTest.from_file(APP_PATH, default_timeout=30).run()
    assert not page.exception
    assert "temporarily unavailable" in page.error[0].value
    assert "private-database-password" not in page.error[0].value
