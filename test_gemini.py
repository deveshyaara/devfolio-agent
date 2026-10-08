import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
print("Initialized.")
model = ChatGoogleGenerativeAI(temperature=0, model="gemini-3.8-flash")
print("Calling model...")
response = model.invoke("Say hi.")
print("Response:", response.content)
