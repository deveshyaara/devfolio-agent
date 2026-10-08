import os
import git # For cloning repos
import requests # For calling the GitHub API
from pathlib import Path # For handling file paths
from dotenv import load_dotenv
from typing import TypedDict, Annotated
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# --- Import Gemini models ---
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.tools import Tool

# 1. SETUP: Load API key and Personal Info
load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME")
PORTFOLIO_TOPIC = os.environ.get("PORTFOLIO_TOPIC", "portfolio") # Defaults to 'portfolio'
MY_NAME = os.environ.get("MY_NAME", "the portfolio owner")
MY_LINKEDIN_URL = os.environ.get("MY_LINKEDIN_URL")
MY_RESUME_URL = os.environ.get("MY_RESUME_URL")
MY_CALENDLY_LINK = os.environ.get("MY_CALENDLY_LINK")
MY_PROFILE_PIC_URL = os.environ.get("MY_PROFILE_PIC_URL", "https://placehold.co/400x400/0D1117/FFFFFF?text=DM")

# Global variables to store project data
project_names_list = []
all_project_documents = []  # Store all README documents for synthesis
projects_metadata = [] # Store compact summaries

# Validate required variables
if not GOOGLE_API_KEY:
    print("Error: GOOGLE_API_KEY not set in .env file.")
    exit()
if not GITHUB_USERNAME:
    print("Error: GITHUB_USERNAME not set in .env file.")
    exit()


# --- 2. AUTOMATED GIT PROJECT LOADER ---
CLONE_DIR = "./project_repos" # A folder to store the cloned repos

def fetch_and_load_projects():
    """
    Fetches repo URLs from GitHub API based on a topic,
    then clones/pulls them and loads their README.md files.
    Also populates global project_names_list and all_project_documents.
    """
    global project_names_list, all_project_documents
    print(f"Fetching repos for user '{GITHUB_USERNAME}' with topic '{PORTFOLIO_TOPIC}'...")
    
    api_url = f"https://api.github.com/search/repositories?q=user:{GITHUB_USERNAME}+topic:{PORTFOLIO_TOPIC}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    try:
        response = requests.get(api_url, headers=headers)
        response.raise_for_status() 
        data = response.json()
        repo_urls = []
        for item in data.get("items", []):
            repo_urls.append(item["clone_url"])
            projects_metadata.append({
                "name": item["name"],
                "description": item.get("description", "No description provided."),
                "language": item.get("language", "Unknown"),
                "url": item["html_url"],
            })
        
        if not repo_urls:
            print(f"Warning: No repos found with topic '{PORTFOLIO_TOPIC}'. Check GitHub.")
            return []
            
        print(f"Found {len(repo_urls)} portfolio repos.")

    except Exception as e:
        print(f"Error fetching from GitHub API: {e}")
        print("Falling back to any existing local repos.")
        repo_urls = [] 

    print("Loading project data from Git repos...")
    os.makedirs(CLONE_DIR, exist_ok=True)
    project_documents = []

    local_repos = {d.name: d for d in Path(CLONE_DIR).iterdir() if d.is_dir()}
    
    for repo_url in repo_urls:
        repo_name = repo_url.split('/')[-1].replace(".git", "")
        repo_path = Path(CLONE_DIR) / repo_name
        
        try:
            if repo_path.exists():
                print(f"Pulling latest changes for {repo_name}...")
                try:
                    repo = git.Repo(repo_path)
                    repo.remotes.origin.pull()
                except Exception as e:
                    print(f"Detected invalid repository state for {repo_name} ({e}). Recreating local clone...")
                    import shutil
                    shutil.rmtree(repo_path)
                    git.Repo.clone_from(repo_url, repo_path)
            else:
                print(f"Cloning {repo_name}...")
                git.Repo.clone_from(repo_url, repo_path)
            
            local_repos.pop(repo_name, None)
            
            readme_path = repo_path / "README.md"
            if readme_path.exists():
                with open(readme_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                doc = Document(
                    page_content=content,
                    metadata={"source": repo_url, "name": repo_name}
                )
                project_documents.append(doc)
            else:
                print(f"Warning: No README.md found in {repo_name}")

        except Exception as e:
            print(f"Error processing repo {repo_url}: {e}")

    for old_repo_name in local_repos:
        print(f"Note: Local repo '{old_repo_name}' no longer tagged, but still in cache.")

    # Populate global variables
    project_names_list = [doc.metadata["name"] for doc in project_documents]
    all_project_documents = project_documents  # Store all documents globally

    return project_documents

# --- 3. RAG TOOL SETUP ---

def create_project_retriever():
    """Creates a vector store and retriever from our project data."""
    documents = fetch_and_load_projects()
    
    if not documents:
        print("Error: No project documents were loaded. Cannot create retriever.")
        return None

    print(f"Embedding {len(documents)} project READMEs...")
    
    print("Initializing Gemini embedding model...")
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-2")

    print("Creating vector store...")
    vector_store = FAISS.from_documents(documents, embeddings)
    
    retriever = vector_store.as_retriever(search_kwargs={"k": 2})
    print("Retriever created.")
    return retriever

# --- 4. PERSONAL INFO TOOLS ---
def get_personal_info(query: str = ""):
    """Returns all available contact links."""
    links = []
    links.append(f"**Name:** {MY_NAME}")
    if MY_LINKEDIN_URL:
        links.append(f"**LinkedIn:** {MY_LINKEDIN_URL}")
    if MY_CALENDLY_LINK:
        links.append(f"**Schedule a Meeting:** {MY_CALENDLY_LINK}")
    if MY_RESUME_URL:
        links.append(f"**Resume:** {MY_RESUME_URL}")
    
    return "\n".join(links)

def get_scheduling_link(query: str = ""):
    """Returns the scheduling/Calendly link."""
    if MY_CALENDLY_LINK:
        return f"You can schedule a meeting with {MY_NAME} using this Calendly link: {MY_CALENDLY_LINK}"
    else:
        return "Sorry, the scheduling link is not available at the moment."

def get_linkedin_link(query: str = ""):
    """Returns the LinkedIn profile link."""
    if MY_LINKEDIN_URL:
        return f"Here is {MY_NAME}'s LinkedIn profile: {MY_LINKEDIN_URL}"
    else:
        return "Sorry, the LinkedIn profile is not available."

def get_resume_link(query: str = ""):
    """Returns the resume link."""
    if MY_RESUME_URL:
        return f"Here is {MY_NAME}'s resume: {MY_RESUME_URL}"
    else:
        return "Sorry, the resume link is not available at the moment."

# --- NEW TOOL: Get Compact Project Summaries ---

def get_projects(query: str = "") -> str:
    """
    Returns a compact summary of ALL projects in the portfolio (name, description, tech stack, URL).
    Use this tool when asked to 'list all projects', 'what projects do you have', 
    or any general question about the portfolio's contents.
    
    Args:
        query: Optional query string
    
    Returns:
        JSON string of project metadata
    """
    if not projects_metadata:
        return "No project metadata is currently loaded."
    import json
    return json.dumps(projects_metadata, indent=2)

# --- 5. LANGGRAPH "FROM SCRATCH" SETUP ---

print("Initializing retriever and tools...")
retriever = create_project_retriever()

personal_info_tool = Tool(
    name="get_personal_info",
    func=get_personal_info,
    description="Get general contact information including all available links (LinkedIn, Calendly, Resume)."
)

scheduling_tool = Tool(
    name="get_scheduling_link",
    func=get_scheduling_link,
    description="Get the Calendly/scheduling link to book a meeting or call. Use this when user asks to schedule, book, or wants a meeting."
)

linkedin_tool = Tool(
    name="get_linkedin_link", 
    func=get_linkedin_link,
    description="Get the LinkedIn profile link."
)

resume_tool = Tool(
    name="get_resume_link",
    func=get_resume_link,
    description="Get the resume/CV link."
)

all_projects_context_tool = Tool(
    name="get_projects",
    func=get_projects,
    description=(
        "Returns a lightweight summary of all projects. "
        "Use this tool when asked to 'list all projects', 'what projects do you have', "
        "or to see a high-level overview before querying specific project details."
    )
)

tools = [personal_info_tool, scheduling_tool, linkedin_tool, resume_tool, all_projects_context_tool]

if retriever:
    project_search_tool = Tool(
        name="project_retriever",
        func=retriever.invoke,
        description=(
            "Searches your project README files for details. "
            "Use this tool whenever a recruiter asks about a specific project, "
            "your tech stack, or your role in a project."
        )
    )
    tools.append(project_search_tool)
    print("Project retriever tool created successfully.")
else:
    print("WARNING: Project retriever tool not created. Agent will lack project knowledge.")

# (The rest of the script is the same from here)
tool_node = ToolNode(tools)

# Configure primary model with 0 retries so 429 fails immediately
primary_model = ChatGoogleGenerativeAI(temperature=0, model="gemini-3.5-flash", max_retries=0)
fallback_model = ChatGoogleGenerativeAI(temperature=0, model="gemma-4-26b-a4b-it")

# Bind tools and add fallback
primary_with_tools = primary_model.bind_tools(tools)
fallback_with_tools = fallback_model.bind_tools(tools)
model_with_tools = primary_with_tools.with_fallbacks([fallback_with_tools])

print("Building agent graph from scratch...")

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

def call_model_node(state: AgentState):
    print("-> Calling Model")
    messages = state["messages"]
    
    # Add system message if not present
    if not messages or not isinstance(messages[0], SystemMessage):
        system_msg = SystemMessage(content=f"""You are an AI assistant representing {MY_NAME}'s portfolio. 
Your role is to help recruiters and visitors learn about {MY_NAME}'s projects, skills, and contact information.

IMPORTANT: You MUST use the provided tools to answer questions. Never make up or hallucinate information.
- For listing projects or high-level summaries: Use get_projects
- For deep dives into a specific project's tech stack or architecture: Use project_retriever
- For scheduling/Calendly links: Use get_scheduling_link tool
- For LinkedIn: Use get_linkedin_link tool  
- For resume: Use get_resume_link tool
- For general contact info: Use get_personal_info tool

Be professional, concise, and helpful. Always refer to {MY_NAME} in the third person when discussing their work.""")
        messages = [system_msg] + messages
    
    response = model_with_tools.invoke(messages)
    return {"messages": [response]}

def call_tool_node(state: AgentState):
    print("-> Calling Tool")
    # ToolNode handles the execution automatically
    return tool_node.invoke(state)

def should_continue(state: AgentState):
    if state["messages"][-1].tool_calls:
        return "call_tool"
    return END

workflow = StateGraph(AgentState)
workflow.add_node("call_model", call_model_node)
workflow.add_node("call_tool", call_tool_node) 
workflow.set_entry_point("call_model")
workflow.add_conditional_edges(
    "call_model",
    should_continue,
    {"call_tool": "call_tool", END: END}
)
workflow.add_edge("call_tool", "call_model")
from langgraph.checkpoint.memory import MemorySaver
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
print("Agent is ready!")

# --- 6. RUN THE AGENT ---
def run_chat(question, thread_id="default"):
    print(f"\n---")
    print(f"Recruiter: {question}")
    
    # We no longer manually reconstruct history. The checkpointer handles it.
    inputs = {"messages": [HumanMessage(content=question)]}
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        output = app.invoke(inputs, config=config)
        final_response = output["messages"][-1].content
        if isinstance(final_response, list):
            final_response = "".join(
                item["text"] if isinstance(item, dict) and "text" in item else (item if isinstance(item, str) else "")
                for item in final_response
            )
        print(f"Agent: {final_response}")
        return final_response
    except Exception as e:
        print(f"Agent: Error - {e}")
        return "Sorry, I ran into an error."

# --- 7. TEST IT ---
if __name__ == "__main__":
    print("\n--- Running agent.py in test mode ---")
    
    # Test 1
    q1 = "Hello, who are you?"
    run_chat(q1)
    
    # Test 2
    q2 = "What projects are in your portfolio?"
    run_chat(q2)

    # Test 3
    q3 = "Do you have a link to your resume?"
    run_chat(q3)

    # Test 4 - Scheduling link
    q4 = "Give me the Calendly link"
    run_chat(q4)
    
    # Test 5 - Alternative scheduling request
    q5 = "scheduling"
    run_chat(q5)
    print(f"\n✅ All tests completed successfully!")

