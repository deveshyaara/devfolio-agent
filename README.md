# 🤖 DevFolio Agent - AI Portfolio Chatbot

An intelligent AI assistant that represents your portfolio, built with **LangGraph**, **Google Gemini**, and **Streamlit**. This chatbot automatically syncs with your GitHub portfolio projects and helps recruiters learn about your work, skills, and contact information through natural conversation.
---
Live - https://devfolio-agent.streamlit.app/
## ✨ Features

### 🔄 **Automated GitHub Sync**
- Automatically clones and syncs portfolio projects tagged with `portfolio` topic from GitHub
- Pulls latest changes to keep project information up-to-date
- Loads README files from each project for comprehensive knowledge

### 🧠 **Intelligent Question Answering**
- **Project Discovery**: Lists all portfolio projects with descriptions
- **Tech Stack Analysis**: Synthesizes all technologies used across projects
- **Specific Project Details**: Searches for detailed information about individual projects
- **Contact Information**: Provides LinkedIn, Resume, and Calendly scheduling links
- **Smart Context**: Uses RAG (Retrieval Augmented Generation) with FAISS vector store

### 🛠️ **Specialized Tools**
The agent uses 6 dedicated tools:
1. `get_all_project_contexts` - Returns ALL project READMEs for synthesis
2. `project_retriever` - Searches specific project details using FAISS
3. `get_personal_info` - Returns all contact links
4. `get_scheduling_link` - Provides Calendly meeting link
5. `get_linkedin_link` - Returns LinkedIn profile
6. `get_resume_link` - Returns resume/CV link

### 🎨 **Modern UI**
- Beautiful gradient backgrounds with glass-morphism effects
- Responsive chat interface built with Streamlit
- Custom avatars and typography
- Mobile-friendly design

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.12+**
- **Google API Key** (for Gemini)
- **GitHub Account** with portfolio projects tagged with `portfolio` topic

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/deveshyaara/devfolio-agent.git
   cd devfolio-agent
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   .\venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   
   Create a `.env` file in the project root:
   ```env
   # API Key
   GOOGLE_API_KEY="your-google-api-key-here"
   
   # GitHub Info
   GITHUB_USERNAME="your-github-username"
   PORTFOLIO_TOPIC="portfolio"
   
   # Personal & Contact Info
   MY_NAME="Your Name"
   MY_LINKEDIN_URL="https://linkedin.com/in/yourprofile"
   MY_RESUME_URL="https://yourportfolio.com/resume"
   MY_CALENDLY_LINK="https://calendly.com/yourlink/30min"
   ```

5. **Tag your GitHub repositories**
   
   Go to each portfolio project on GitHub and add the `portfolio` topic to make them discoverable by the agent.

### Running the Application

#### Web Interface (Streamlit)
```bash
streamlit run app.py
```
Then open `http://localhost:8501` in your browser.

#### Command Line (Testing)
```bash
python agent.py
```
This runs predefined test conversations to verify the agent works correctly.

---

## 📁 Project Structure

```
devfolio-agent/
├── agent.py                 # Core agent logic with LangGraph workflow
├── app.py                   # Streamlit web interface
├── chat_bot.py             # (Legacy/backup file)
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (not in git)
├── .gitignore             # Git ignore rules
├── README.md              # This file
└── project_repos/         # Cloned portfolio repositories (auto-generated)
```

---

## 🏗️ Architecture

### Agent Workflow (LangGraph)

```
┌─────────────┐
│   User      │
│   Query     │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  System Message │ ◄─── Defines role & tool usage
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Call Model     │ ◄─── Google Gemini 2.0 Flash
│  (LLM)          │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Need    │
    │ Tool?   │
    └────┬────┘
         │
    ┌────┴────────┐
    │             │
   Yes           No
    │             │
    ▼             ▼
┌───────────┐  ┌──────────┐
│ Call Tool │  │ Respond  │
└─────┬─────┘  └──────────┘
      │
      ▼
┌─────────────────┐
│  Tool Execution │
│  - Get Projects │
│  - Get Contacts │
│  - Search FAISS │
└────────┬────────┘
         │
         ▼
  ┌──────────────┐
  │ Back to LLM  │
  │ to generate  │
  │ final answer │
  └──────────────┘
```

### Technology Stack

- **LangGraph 1.0.2**: Agent orchestration and workflow management
- **Google Gemini 2.0 Flash**: LLM for chat and reasoning
- **HuggingFace Embeddings**: Local embedding model (all-MiniLM-L6-v2) as fallback
- **FAISS 1.12.0**: Vector database for semantic search
- **Streamlit 1.40.0**: Web UI framework
- **GitPython 3.1.45**: Automated repository cloning and syncing
- **LangChain 0.3.18**: Tool integration and RAG pipeline

---

## 🎯 Key Features Explained

### 1. **Smart Context Synthesis**
Instead of hardcoding project lists, the agent reads ALL README files and synthesizes information on demand. This allows it to:
- List projects dynamically
- Extract comprehensive tech stacks
- Answer open-ended questions about your work

### 2. **Automatic GitHub Sync**
```python
# On startup, the agent:
1. Fetches all repos with 'portfolio' topic via GitHub API
2. Clones new repos to ./project_repos/
3. Pulls latest changes for existing repos
4. Loads all README.md files
5. Creates FAISS vector embeddings
```

### 3. **Tool-First Approach**
The system message explicitly instructs the LLM to:
- **NEVER hallucinate** contact information
- **ALWAYS use tools** for factual data
- Map specific question types to appropriate tools

### 4. **Fallback Embedding Model**
If Google's embedding API quota is exceeded, the system automatically falls back to local HuggingFace embeddings, ensuring uninterrupted service.

---

## 💡 Usage Examples

### Example Conversations

**Getting Contact Information:**
```
User: How can I contact him?
Agent: Here are Devesh Tiwari's contact links:
       - LinkedIn: https://linkedin.com/in/deveshcodes
       - Schedule a Meeting: https://calendly.com/tiwaridevesh887/30min
       - Resume: https://devfolio-taupe.vercel.app/resume
```

**Scheduling a Meeting:**
```
User: I want to schedule a meeting
Agent: You can schedule a meeting with Devesh Tiwari using this 
       Calendly link: https://calendly.com/tiwaridevesh887/30min
```

**Listing Projects:**
```
User: What projects are in your portfolio?
Agent: Devesh Tiwari's portfolio includes:
       - WealthWise: An AI-powered finance platform
       - E-Commerce-Backend: A RESTful API for e-commerce
       - devfolio: A personal portfolio website
       - Healthlink_RPC: Blockchain-based healthcare system
       - Healthlink_Agent: AI healthcare communication system
```

**Tech Stack Inquiry:**
```
User: What technologies do you know?
Agent: [Synthesizes from all READMEs]
       Based on the projects, Devesh has experience with:
       - Languages: Python, JavaScript, TypeScript, Java, Solidity
       - Frameworks: Next.js, React, Spring Boot, Flask, Streamlit
       - Databases: PostgreSQL, MongoDB, Redis
       - Cloud: AWS, Azure, Hyperledger Fabric
       - AI/ML: LangChain, OpenAI, Gemini, FAISS
```

---

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | ✅ Yes | Google API key for Gemini |
| `GITHUB_USERNAME` | ✅ Yes | Your GitHub username |
| `PORTFOLIO_TOPIC` | ❌ No | GitHub topic to filter repos (default: "portfolio") |
| `MY_NAME` | ❌ No | Your full name |
| `MY_LINKEDIN_URL` | ❌ No | LinkedIn profile URL |
| `MY_RESUME_URL` | ❌ No | Resume/CV link |
| `MY_CALENDLY_LINK` | ❌ No | Calendly scheduling link |

### Customization

**Change the LLM Model:**
```python
# In agent.py, line ~43
model = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash-exp",  # Change to another Gemini model
    temperature=0.7
)
```

**Adjust Embedding Model:**
```python
# In agent.py, line ~95
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"  # Change model
)
```

**Modify UI Colors:**
```python
# In app.py, update the CSS gradient
background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
```

---

## 🐛 Troubleshooting

### Common Issues

**1. Import Error: ToolExecutor not found**
- **Solution**: Update to LangGraph 1.0.2+ which uses `ToolNode` instead

**2. Google API Quota Exceeded**
- **Solution**: The system automatically falls back to HuggingFace embeddings

**3. Agent hallucinating contact info**
- **Solution**: Ensure system message explicitly instructs to use tools (already implemented)

**4. Projects not loading**
- **Solution**: 
  - Verify `GITHUB_USERNAME` is correct
  - Ensure repos are tagged with `portfolio` topic
  - Check GitHub API rate limits

**5. Streamlit app won't start**
- **Solution**: 
  ```bash
  pip install --upgrade streamlit
  streamlit run app.py
  ```

---

## 📝 Development

### Running Tests
```bash
python agent.py
```
This executes predefined test queries and shows the agent's responses.

### Adding New Tools

1. **Define the function** in `agent.py`:
   ```python
   def my_new_tool(query: str = ""):
       # Your logic here
       return "result"
   ```

2. **Create the tool**:
   ```python
   my_tool = Tool(
       name="my_new_tool",
       func=my_new_tool,
       description="Clear description for LLM"
   )
   ```

3. **Add to tools list**:
   ```python
   tools = [...existing tools..., my_tool]
   ```

4. **Update system message** to instruct when to use it

---

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **LangChain/LangGraph** for the agent framework
- **Google Gemini** for powerful LLM capabilities
- **Streamlit** for the beautiful UI framework
- **HuggingFace** for local embedding models

---

## 📧 Contact

**Devesh Tiwari**
- LinkedIn: [deveshcodes](https://linkedin.com/in/deveshcodes)
- Portfolio: [devfolio-taupe.vercel.app](https://devfolio-taupe.vercel.app)
- Schedule: [Book a meeting](https://calendly.com/tiwaridevesh887/30min)

---

## 🌟 Star History

If you find this project useful, please consider giving it a ⭐!

---


