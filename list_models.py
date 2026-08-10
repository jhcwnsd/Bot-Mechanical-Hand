import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client()

print("Listing available models from API:")
try:
    for model in client.models.list():
        print(model.name)
except Exception as e:
    print(f"Error listing models: {str(e)}")
