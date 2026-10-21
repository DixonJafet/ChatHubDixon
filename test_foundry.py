
import os

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

load_dotenv()

endpoint = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
model = os.environ["AZURE_AI_MODEL_DEPLOYMENT"]

project = AIProjectClient(
    endpoint=endpoint,
    credential=DefaultAzureCredential(),
)

client = project.get_openai_client()

response = client.responses.create(
    model=model,
    input=(
        "Responde en español en una sola frase: "
        "¿Cuál será tu función en un sistema RAG "
        "que responde preguntas sobre código?"
    ),
)

print(response.output_text)
