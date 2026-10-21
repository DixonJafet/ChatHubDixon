
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

load_dotenv()

ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")

INPUT_PATH = Path("data/chunks.jsonl")
OUTPUT_PATH = Path("data/embeddings.jsonl")
BATCH_SIZE = 32


def create_client():
    if not ENDPOINT or not DEPLOYMENT:
        raise ValueError(
            "Configura AZURE_OPENAI_ENDPOINT y "
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT en .env"
        )

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://ai.azure.com/.default",
    )

    return OpenAI(
        base_url=f"{ENDPOINT}/openai/v1/",
        api_key=token_provider,
    )


def generate_embeddings():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"No existe {INPUT_PATH}. Ejecuta primero la ingesta."
        )

    with INPUT_PATH.open("r", encoding="utf-8") as source:
        chunks = [
            json.loads(line)
            for line in source
            if line.strip()
        ]

    if not chunks:
        raise ValueError("No hay chunks para procesar.")

    records = embed_records(chunks)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nEmbeddings generados: {len(records)}")
    print(f"Archivo: {OUTPUT_PATH.resolve()}")


def embed_records(chunks):
    if not chunks:
        raise ValueError("No hay fragmentos para generar embeddings.")

    client = create_client()
    records = []

    for start in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[start:start + BATCH_SIZE]
        response = client.embeddings.create(
            model=DEPLOYMENT,
            input=[item["text"] for item in batch],
        )
        vectors = sorted(response.data, key=lambda item: item.index)

        if len(vectors) != len(batch):
            raise RuntimeError(
                "Azure devolvió una cantidad inesperada de embeddings."
            )

        records.extend(
            {
                **item,
                "embedding": vector.embedding,
            }
            for item, vector in zip(batch, vectors)
        )
        print(f"Procesados: {len(records)}/{len(chunks)}")

    return records


if __name__ == "__main__":
    try:
        generate_embeddings()
    except Exception as error:
        print(f"Error generando embeddings: {error}")
        raise SystemExit(1)
