from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaLLM
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from ddgs import DDGS
from app.utils import cargar_documento



def inicializar_qa_chain():
    print("Cargando documentos...")
    documentos_dir = "documentos"
    docs_raw = cargar_documento(documentos_dir)
    print("Dividiendo documentos...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=250)
    documents = text_splitter.split_documents(docs_raw)
    print("Cargando embeddings...")
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    print("Creando vectorstore...")
    vectorstore = FAISS.from_documents(documents, embeddings)
    print("Cargando LLM...")
    llm = OllamaLLM(model="llama3.2")
    template = """
Usa la siguiente información de contexto para responder la pregunta al final.
Si no sabes la respuesta, simplemente di que no la sabes, no intentes inventar una respuesta.
Mantén la respuesta lo más concisa posible.

Contexto: {context}
Pregunta: {question}
Respuesta útil:
"""
    QA_CHAIN_PROMPT = PromptTemplate.from_template(template)
    qa_chain = RetrievalQA.from_chain_type(
        llm,
        retriever=vectorstore.as_retriever(),
        chain_type_kwargs={"prompt": QA_CHAIN_PROMPT}
    )
    print("QA Chain inicializado.")
    return qa_chain

qa_chain = None

def get_answer(question: str):
    global qa_chain
    if qa_chain is None:
        try:
            qa_chain = inicializar_qa_chain()
        except Exception as e:
            return {"error": f"Error inicializando QA Chain: {str(e)}"}
    try:
        result = qa_chain.invoke({"query": question})
        respuesta = result["result"]
    except Exception as e:
        return {"error": f"Error en la llamada QA: {str(e)}"}
    # Si la respuesta indica que no sabe, busca en internet
    if "no tengo" in respuesta.lower() or "no " in respuesta.lower():
        try:
            with DDGS() as ddgs:
                resultados = ddgs.text(question)
                for r in resultados:
                    return {"respuesta": respuesta, "internet": r["body"]}
        except Exception as e:
            return {"respuesta": respuesta, "error_internet": f"Error en búsqueda internet: {str(e)}"}
    return {"respuesta": respuesta}
