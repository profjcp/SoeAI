import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from core.latex_builder import ensamblar_documento, guardar_tex
from core.ollama_client import texto_a_latex
from core.pdf_compiler import compilar_pdf


load_dotenv()

st.set_page_config(page_title="LaTeX Article Generator", layout="wide")
st.title("📄 Generador de Artículos Científicos")
st.caption("Escribe tu artículo en texto plano. La IA lo convierte a LaTeX y PDF.")

norma = st.selectbox("📐 Selecciona la norma:", ["IEEE", "APA"])

campos = [
    ("title", "Título del artículo", "input", 1),
    ("authors", "Autores (uno por línea)", "area", 100),
    ("abstract", "Abstract", "area", 180),
    ("keywords", "Palabras clave (separadas por coma)", "input", 1),
    ("introduction", "Introducción", "area", 220),
    ("related_work", "Trabajo relacionado", "area", 180),
    ("methodology", "Metodología", "area", 220),
    ("results", "Resultados", "area", 220),
    ("discussion", "Discusión", "area", 180),
    ("conclusion", "Conclusión", "area", 180),
    ("references", "Referencias (una por línea)", "area", 180),
]

entradas: dict[str, str] = {}
for clave, etiqueta, tipo, alto in campos:
    if tipo == "input":
        entradas[clave] = st.text_input(etiqueta)
    else:
        entradas[clave] = st.text_area(etiqueta, height=alto)

col1, col2 = st.columns([1, 1])
with col1:
    modelo = st.text_input("🤖 Modelo Ollama", value=os.getenv("OLLAMA_MODEL", "llama3.2"))
with col2:
    nombre_archivo = st.text_input("📁 Nombre de salida", value="articulo")

if st.button("🚀 Generar PDF", type="primary"):
    secciones_no_vacias = {k: v for k, v in entradas.items() if v.strip()}

    if not secciones_no_vacias:
        st.warning("Escribe al menos una sección antes de generar.")
        st.stop()

    try:
        with st.spinner("Convirtiendo secciones a LaTeX con Ollama..."):
            latex_secciones: dict[str, str] = {}
            progress = st.progress(0)

            for index, (clave, texto) in enumerate(secciones_no_vacias.items(), start=1):
                latex_secciones[clave] = texto_a_latex(clave, texto, norma, modelo=modelo)
                progress.progress(index / len(secciones_no_vacias))

        documento = ensamblar_documento(latex_secciones, norma)
        ruta_tex = guardar_tex(documento, nombre=nombre_archivo)
        ruta_pdf = compilar_pdf(ruta_tex)

        st.success("✅ PDF generado exitosamente")

        with open(ruta_tex, "rb") as tex_file:
            st.download_button(
                "⬇️ Descargar .tex",
                tex_file,
                Path(ruta_tex).name,
                "application/x-tex",
            )

        with open(ruta_pdf, "rb") as pdf_file:
            st.download_button(
                "⬇️ Descargar PDF",
                pdf_file,
                Path(ruta_pdf).name,
                "application/pdf",
            )

    except Exception as error:
        st.error(f"❌ Error: {error}")
        st.info("Revisa que Ollama esté corriendo y que `pdflatex` esté instalado.")
