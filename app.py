import logging

import streamlit as st

from agent import MY_NAME
from devfolio.runtime import get_runtime
from devfolio.sessions import ChatSession, RequestRejected

st.set_page_config(page_title=f"{MY_NAME} - AI Portfolio Assistant", page_icon="🤖", layout="centered")
st.title("🤖 Portfolio Assistant")
st.caption(f"Ask me about {MY_NAME}'s work, skills, and projects.")

try:
    if "chat_session" not in st.session_state:
        st.session_state.chat_session = ChatSession(get_runtime())
except Exception as exc:
    logging.getLogger(__name__).error("configuration_unavailable", extra={"error_type": type(exc).__name__})
    st.error("The assistant is temporarily unavailable. Please try again later.")
    st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": f"👋 Hi! I'm {MY_NAME}'s AI assistant. What would you like to know?"}
    ]

if st.session_state.chat_session.expire_if_needed():
    st.session_state.messages = []
    st.info("Your temporary conversation expired. A new conversation has started.")

if st.button("New conversation"):
    st.session_state.chat_session.reset()
    st.session_state.messages = []
    st.rerun()

st.caption(
    "Anonymous conversations are temporary: they reset after 30 minutes of inactivity, 12 turns, a stopped request, or a backend restart."
)
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="🧑‍💻" if message["role"] == "user" else "🤖"):
        st.markdown(message["content"])

# Streamlit's native Stop control interrupts a running script. The generator's
# finally block closes the graph stream and drops any incomplete checkpoints.
if prompt := st.chat_input("Ask about projects, skills, experience…", max_chars=4000):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)
    with st.chat_message("assistant", avatar="🤖"):
        try:
            with st.spinner("🤔 Thinking…"):
                answer = st.write_stream(st.session_state.chat_session.stream(prompt))
            if not answer:
                answer = "I couldn't complete that answer. Please try again."
                st.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
        except RequestRejected as exc:
            st.warning(str(exc))
        except Exception as exc:
            logging.getLogger(__name__).warning("chat_unavailable", extra={"error_type": type(exc).__name__})
            st.error(
                "The response was interrupted or the assistant is temporarily unavailable. Start a new conversation or try again later."
            )
    # Bound displayed history independently from graph retention.
    st.session_state.messages = st.session_state.messages[-26:]
