import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage

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
                # Convert to LangChain format
                history = []
                for msg in st.session_state.messages:
                    if msg["role"] == "user":
                        history.append(HumanMessage(content=msg["content"]))
                    else:
                        history.append(AIMessage(content=msg["content"]))

                # Call agent
                response = portfolio_agent.invoke({"messages": history})
                bot_response = response["messages"][-1].content

                # Display and save response
                st.markdown(bot_response)
                st.session_state.messages.append({"role": "assistant", "content": bot_response})

            except Exception as e:
                error_msg = f"❌ Sorry, I encountered an error: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
