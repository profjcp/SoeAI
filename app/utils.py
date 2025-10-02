import os
from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredWordDocumentLoader

def cargar_documento(documentos_dir):
    archivos = [f for f in os.listdir(documentos_dir) if os.path.isfile(os.path.join(documentos_dir, f))]
    if not archivos:
        raise Exception(f"No se encontró ningún archivo en la carpeta '{documentos_dir}'.")
    nombre_archivo = os.path.join(documentos_dir, archivos[0])
    extension = nombre_archivo.lower().split('.')[-1]
    if extension == "pdf":
        loader = PyPDFLoader(nombre_archivo)
    elif extension == "txt":
        loader = TextLoader(nombre_archivo)
    elif extension in ["docx", "doc"]:
        loader = UnstructuredWordDocumentLoader(nombre_archivo)
    else:
        raise Exception(f"Tipo de archivo '{extension}' no soportado.")
    return loader.load()
