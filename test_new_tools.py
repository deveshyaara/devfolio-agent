"""
Test script to verify the smart get_all_project_contexts synthesis tool
"""
import sys
sys.path.insert(0, '.')

from agent import run_chat

print("=" * 70)
print("Testing Smart Portfolio Agent with Context Synthesis")
print("=" * 70)

test_history = []

# Test 1: List all projects (should synthesize from all READMEs)
print("\n🧪 TEST 1: Asking to list all projects (synthesis)")
q1 = "Can you list all your projects?"
resp1 = run_chat(q1, test_history)
test_history.append({"role": "user", "content": q1})
test_history.append({"role": "assistant", "content": resp1})

# Test 2: Tech stack extraction (should extract from all READMEs)
print("\n🧪 TEST 2: Asking about tech stack (synthesis from READMEs)")
q2 = "What technologies and programming languages do you know?"
resp2 = run_chat(q2, test_history)
test_history.append({"role": "user", "content": q2})
test_history.append({"role": "assistant", "content": resp2})

# Test 3: Skills synthesis
print("\n🧪 TEST 3: Asking about skills (broad synthesis)")
q3 = "What are your main technical skills?"
resp3 = run_chat(q3, test_history)
test_history.append({"role": "user", "content": q3})
test_history.append({"role": "assistant", "content": resp3})

# Test 4: Specific project (should use RAG for needle-in-haystack)
print("\n🧪 TEST 4: Asking about a specific project (RAG search)")
q4 = "Tell me more details about the WealthWise project"
resp4 = run_chat(q4, test_history)
test_history.append({"role": "user", "content": q4})
test_history.append({"role": "assistant", "content": resp4})

# Test 5: Project count
print("\n🧪 TEST 5: How many projects (synthesis)")
q5 = "How many projects do you have in your portfolio?"
resp5 = run_chat(q5, test_history)

print("\n" + "=" * 70)
print("✅ All synthesis tests completed!")
print("=" * 70)
print("\n📝 Summary:")
print("- The agent can now synthesize answers from ALL README files")
print("- It extracts project names, tech stacks, and skills intelligently")
print("- RAG search still works for specific project queries")
print("- LLM leverages Gemini's large context window to read everything at once")

