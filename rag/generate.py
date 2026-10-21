
import os

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

from rag.search import search

load_dotenv()

PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "").strip()
MODEL_DEPLOYMENT = os.getenv("AZURE_AI_MODEL_DEPLOYMENT", "").strip()


def create_client():
    if not PROJECT_ENDPOINT or not MODEL_DEPLOYMENT:
        raise ValueError(
            "Configura AZURE_AI_PROJECT_ENDPOINT y "
            "AZURE_AI_MODEL_DEPLOYMENT en el archivo .env."
        )

    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    return project.get_openai_client()


def answer_question(question: str, top_k: int = 3):
    if not question or not question.strip():
        raise ValueError("La pregunta no puede estar vacía.")

    # 1. Recuperar fragmentos relevantes con el buscador existente.
    results = search(question, top_k=top_k)

    # 2. Construir el contexto incluyendo referencias a los archivos.
    context_parts = []

    for i, result in enumerate(results, start=1):
        context_parts.append(
            f"[Fuente {i}]\n"
            f"Repositorio: {result.get('repository')}\n"
            f"Archivo: {result.get('file_path')}\n"
            f"Fragmento: {result.get('chunk_index')}\n"
            f"Similitud coseno: {result.get('score', 0):.4f}\n"
            f"Contenido:\n{result.get('text', '')}"
        )

    context = "\n\n".join(context_parts)

    # 3. Pedir a GPT-5 mini una respuesta fundamentada en el contexto.
    client = create_client()

    response = client.responses.create(
        model=MODEL_DEPLOYMENT,
        #max_output_tokens=500,
        instructions=(
                "Eres el asistente técnico de un portafolio de proyectos de software, que usa lenguaje natural" \
                "Tu trabajo es sintetizar información, NO explicar código, da como máximo 1 fuente principal de código." \
                "puedes mencionar tecnologias, breves descripción de como se implementa sin detalles demaciado técnicos"\
                "Si la pregunta no se relaciona con ningun proyecto o no existe fuente directa sobre eso,"
                " solo dilo," \
                "no des mucha información sobre el frontend" \
                "usa como máximo 100 palabras para responder, a menos que sea solicitada más información." \
                "no des info extra sobre otros proyectos."
        ),
        input=(
            f"PREGUNTA DEL USUARIO:\n{question}\n\n"
            f"CONTEXTO RECUPERADO:\n{context}\n\n"
            "Responde de forma clara y concreta. Incluye 1 referencia"
            "a las fuentes utilizadas."
        ),
    )

    # 4. Devolver la respuesta y las fuentes para que la API
    # pueda mostrarlas por separado.
    return {
        "answer": response.output_text,
        "sources": [
            {
                "repository": result.get("repository"),
                "file_path": result.get("file_path"),
                "chunk_index": result.get("chunk_index"),
                "score": result.get("score"),
            }
            for result in results
        ],
    }


if __name__ == "__main__":
    question = input("Pregunta sobre tus repositorios: ")

    try:
        result = answer_question(question)

        print("\nRESPUESTA:\n")
        print(result["answer"])

        print("\nFUENTES RECUPERADAS:\n")
        for source in result["sources"]:
            print(
                f"- {source['repository']} / "
                f"{source['file_path']} "
                f"(chunk {source['chunk_index']}, "
                f"similitud {source['score']:.4f})"
            )

    except Exception as error:
        print(f"Error al generar la respuesta: {error}")
        raise SystemExit(1)
