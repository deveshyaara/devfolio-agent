import os
from dotenv import load_dotenv
load_dotenv()

from langchain_huggingface import HuggingFaceEndpoint, HuggingFaceEmbeddings

print("Testing Embeddings...")
try:
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    res = embeddings.embed_query("Hello world")
    print("Embeddings OK, length:", len(res))
except Exception as e:
    print("Embeddings Error:", repr(e))

print("\nTesting LLM...")
try:
    llm = HuggingFaceEndpoint(
        endpoint_url="https://api-inference.huggingface.co/models/HuggingFaceH4/zephyr-7b-beta",
        task="text-generation",
        max_new_tokens=10,
        huggingfacehub_api_token=os.environ.get("HUGGINGFACEHUB_API_TOKEN")
    )
    res = llm.invoke("Hello world")
    print("LLM OK:", res)
except Exception as e:
    print("LLM Error:", repr(e))
