from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

# 1. Crear una instancia de FastAPI
app = FastAPI(
    title="Mi Primera API",
    description="Esta es una API de ejemplo muy simple.",
    version="1.0.0",
)

# 2. Definir un modelo de datos con Pydantic
# Esto asegura que los datos que recibes tienen la estructura correcta.
class Item(BaseModel):
    nombre: str
    precio: float
    en_stock: bool = True # Valor por defecto

# Una "base de datos" en memoria para empezar
db_items = []

# 3. Crear los "endpoints" (las URLs de tu API)

@app.get("/")
def leer_raiz():
    """
    Endpoint principal que da la bienvenida.
    """
    return {"mensaje": "¡Bienvenido a mi API con FastAPI!"}

@app.get("/items", response_model=List[Item])
def obtener_items():
    """
    Endpoint para obtener todos los items.
    """
    return db_items

@app.post("/items", response_model=Item, status_code=201)
def crear_item(item: Item):
    """
    Endpoint para crear un nuevo item.
    """
    db_items.append(item)
    return item