
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from rag.generate import answer_question

app = FastAPI(
    title="AI Portfolio API",
    description="API para responder preguntas sobre mis proyectos de GitHub",
    version="0.2.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dixon-gpt.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)

class ChatRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000,
        description="Pregunta sobre los repositorios del portafolio",
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/v1/chat")
def chat(request: ChatRequest):
    try:
        result = answer_question(request.question)

        return {
            "question": request.question,
            "answer": result["answer"],
            "sources": result["sources"],
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

    except Exception as error:
        # Registrar el detalle en el servidor, sin exponerlo al cliente.
        print(f"Error en el endpoint /api/v1/chat: {error}")

        raise HTTPException(
            status_code=500,
            detail="No se pudo generar una respuesta. Inténtalo de nuevo.",
        ) from error
