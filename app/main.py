from fastapi import FastAPI
from pydantic import BaseModel
from app.rag import get_answer

app = FastAPI(
    title="SoeBOT API",
    description="API para interactuar con SoeBOT",
    version="1.0.0",
)

class Question(BaseModel):
    question: str

@app.get("/")
def leer_raiz():
    """
    Endpoint principal que da la bienvenida.
    """
    return {"mensaje": "¡Bienvenido a mi API con FastAPI! SoeBOT"}
@app.post("/ask")
def ask_question(q: Question):
    try:
        if not q.question or not q.question.strip():
            return {"error": "No se recibió una pregunta válida."}
        respuesta = get_answer(q.question)
        if not respuesta:
            return {"error": "No se obtuvo respuesta."}
        return respuesta
    except Exception as e:
        return {"error": f"Ocurrió un error: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", reload=True)