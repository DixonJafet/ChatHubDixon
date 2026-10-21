
import os

from azure.identity import DefaultAzureCredential
from azure.identity import get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "").rstrip("/")
SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "").strip()


def create_client():
    if not ENDPOINT or not DEPLOYMENT:
        raise ValueError(
            "Configura el endpoint y el despliegue en .env."
        )

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://ai.azure.com/.default",
    )

    return OpenAI(
        base_url=f"{ENDPOINT}/openai/v1/",
        api_key=token_provider,
    )


def create_search_client(credential):
    if not SEARCH_ENDPOINT or not SEARCH_INDEX:
        raise ValueError(
            "Configura AZURE_SEARCH_ENDPOINT y AZURE_SEARCH_INDEX."
        )

    return SearchClient(
        endpoint=SEARCH_ENDPOINT,
        index_name=SEARCH_INDEX,
        credential=credential,
    )


def search(question: str, top_k: int = 5):
    if not question.strip():
        raise ValueError("La pregunta no puede estar vacía.")

    if top_k < 1:
        raise ValueError("top_k debe ser al menos 1.")

    if not SEARCH_ENDPOINT or not SEARCH_INDEX:
        raise ValueError(
            "Configura AZURE_SEARCH_ENDPOINT y AZURE_SEARCH_INDEX."
        )

    embedding_client = create_client()

    response = embedding_client.embeddings.create(
        model=DEPLOYMENT,
        input=question,
    )
    query_vector = response.data[0].embedding
    credential = DefaultAzureCredential()
    search_client = create_search_client(credential)

    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="embedding",
    )
    try:
        matches = search_client.search(
            search_text=None,
            vector_queries=[vector_query],
            top=top_k,
            select=[
                "repository",
                "file_path",
                "chunk_index",
                "text",
            ],
        )

        return [
            {
                "score": result["@search.score"],
                "repository": result.get("repository"),
                "file_path": result.get("file_path"),
                "chunk_index": result.get("chunk_index"),
                "text": result["text"],
            }
            for result in matches
        ]
    finally:
        search_client.close()
        credential.close()


if __name__ == "__main__":
    question = input("Pregunta sobre tus repositorios: ")

    try:
        results = search(question, top_k=5)

        print("\nFragmentos más relevantes:\n")

        for position, result in enumerate(results, start=1):
            print("=" * 70)
            print(f"Resultado: {position}")
            print(f"Similitud coseno: {result['score']:.4f}")
            print(
                f"Repositorio: {result['repository']}"
            )
            print(f"Archivo: {result['file_path']}")
            print(f"Chunk: {result['chunk_index']}")
            print("\nContenido:")
            print(result["text"])
            print()

    except Exception as error:
        print(f"Error durante la búsqueda: {error}")
        raise SystemExit(1)
