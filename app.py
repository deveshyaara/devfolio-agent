import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

from dotenv import load_dotenv
load_dotenv()

# Import agent and configuration
try:
    from agent import app as portfolio_agent
    from agent import MY_NAME, MY_PROFILE_PIC_URL, MY_LINKEDIN_URL, MY_RESUME_URL, GITHUB_USERNAME
except ImportError:
    st.error("❌ Could not import agent.py. Make sure it's in the same directory.")
    st.stop()

# Page configuration
st.set_page_config(
    page_title=f"{MY_NAME} - AI Portfolio Assistant",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="expanded"
)



# Main chat interface
st.title("🤖 Portfolio Assistant")
st.markdown(f'<p class="subtitle">Ask me anything about {MY_NAME}\'s work, skills, and projects</p>', unsafe_allow_html=True)

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant", 
            "content": f"👋 Hi! I'm {MY_NAME}'s AI assistant. I can help you learn about projects, technical skills, and experience. What would you like to know?"
        }
    ]

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar="🧑‍💻" if message["role"] == "user" else "🤖"):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("💬 Ask about projects, skills, experience..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("🤔 Thinking..."):
            try:
                # Generate thread ID if not exists
                if "thread_id" not in st.session_state:
                    import uuid
                    st.session_state.thread_id = str(uuid.uuid4())

                # Call agent using LangGraph checkpointer, sending ONLY the new message
                inputs = {"messages": [HumanMessage(content=prompt)]}
                config = {"configurable": {"thread_id": st.session_state.thread_id}}
                
                response = portfolio_agent.invoke(inputs, config=config)
                bot_response = response["messages"][-1].content
                if isinstance(bot_response, list):
                    bot_response = "".join(
                        item["text"] if isinstance(item, dict) and "text" in item else (item if isinstance(item, str) else "")
                        for item in bot_response
                    )

                # Display and save response
                st.markdown(bot_response)
                st.session_state.messages.append({"role": "assistant", "content": bot_response})

            except Exception as e:
                error_msg = f"❌ Sorry, I encountered an error: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
