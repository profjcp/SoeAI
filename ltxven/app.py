import os
import re
import time
from html import unescape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

try:
    from streamlit_quill import st_quill
except ImportError:
    st_quill = None

from core.latex_builder import ensamblar_documento, guardar_tex
from core.history_store import list_snapshots, load_payload, save_snapshot, update_snapshot
from core.ollama_client import texto_a_latex
from core.pdf_compiler import compilar_pdf


def _escape_latex_plain(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    result = text
    for source, target in replacements.items():
        result = result.replace(source, target)
    return result


def _metadata_a_latex(clave: str, texto: str) -> str:
    limpio = texto.strip()
    if not limpio:
        return ""

    if clave == "title":
        return _escape_latex_plain(" ".join(limpio.splitlines())).strip()

    if clave == "authors":
        autores = [_escape_latex_plain(linea.strip()) for linea in limpio.splitlines() if linea.strip()]
        return r" \\ ".join(autores)

    if clave == "keywords":
        keywords = " ".join(limpio.splitlines())
        return _escape_latex_plain(keywords).strip()

    return _escape_latex_plain(limpio)


def _limpiar_salida_previa(nombre_archivo: str) -> None:
    base_path = Path("output") / nombre_archivo
    extensiones = [".aux", ".log", ".out", ".pdf", ".tex"]
    for ext in extensiones:
        archivo = base_path.with_suffix(ext)
        if archivo.exists():
            archivo.unlink()


def _rich_html_to_text(html_content: str) -> str:
    if not html_content:
        return ""

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html_content, "html.parser")
        raw_text = soup.get_text("\n")
    else:
        raw_text = re.sub(r"<[^>]+>", " ", html_content)
        raw_text = unescape(raw_text)

    lineas = [linea.strip() for linea in raw_text.splitlines()]
    return "\n".join(linea for linea in lineas if linea)


def _restaurar_payload(payload: dict) -> None:
    st.session_state["norma_select"] = payload.get("norma", "IEEE")
    st.session_state["toggle_rich_editor"] = payload.get("usar_editor_enriquecido", True)
    st.session_state["modelo_input"] = payload.get("modelo", os.getenv("OLLAMA_MODEL", "llama3.2"))
    st.session_state["nombre_archivo_input"] = payload.get("nombre_archivo", "articulo")

    secciones = payload.get("secciones", {})
    if isinstance(secciones, dict):
        for clave, valor in secciones.items():
            st.session_state[f"field_{clave}"] = str(valor or "")
            st.session_state[f"quill_{clave}"] = str(valor or "")


load_dotenv()

st.set_page_config(page_title="LaTeX Article Generator", layout="wide")
st.title("📄 Generador de Artículos Científicos")
st.caption("Escribe tu artículo en texto plano. La IA lo convierte a LaTeX y PDF.")

if "norma_select" not in st.session_state:
    st.session_state["norma_select"] = "IEEE"
if "toggle_rich_editor" not in st.session_state:
    st.session_state["toggle_rich_editor"] = True
if "modelo_input" not in st.session_state:
    st.session_state["modelo_input"] = os.getenv("OLLAMA_MODEL", "llama3.2")
if "nombre_archivo_input" not in st.session_state:
    st.session_state["nombre_archivo_input"] = "articulo"

with st.sidebar:
    st.subheader("📚 Histórico")
    snapshots = list_snapshots(limit=20)
    opciones = [""] + [f"{item['run_id']} | {item.get('status', 'pending')}" for item in snapshots]
    seleccion = st.selectbox("Recuperar ejecución", opciones)

    if st.button("Cargar histórico"):
        if seleccion:
            run_id = seleccion.split(" | ")[0]
            payload = load_payload(run_id)
            if payload:
                _restaurar_payload(payload)
                st.success("Histórico cargado. Formulario restaurado.")
                st.rerun()
            else:
                st.warning("No se pudo cargar ese histórico.")
        else:
            st.info("Selecciona un histórico para cargar.")

norma = st.selectbox("📐 Selecciona la norma:", ["IEEE", "APA"], key="norma_select")
usar_editor_enriquecido = st.toggle(
    "📝 Usar editor enriquecido en campos largos",
    key="toggle_rich_editor",
    help="Permite aplicar formato visual al escribir; la app lo convierte automáticamente a texto limpio para LaTeX.",
)

if usar_editor_enriquecido and st_quill is None:
    st.warning("Editor enriquecido no disponible aún. Instala dependencias con: pip install -r requirements.txt")

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
        entradas[clave] = st.text_input(etiqueta, key=f"field_{clave}")
    else:
        if usar_editor_enriquecido and st_quill is not None:
            st.markdown(f"**{etiqueta}**")
            contenido_html = st_quill(
                key=f"quill_{clave}",
                value=st.session_state.get(f"quill_{clave}", ""),
                placeholder=f"Escribe aquí: {etiqueta}",
                html=True,
                toolbar=None,
            )
            entradas[clave] = _rich_html_to_text(contenido_html)
        else:
            entradas[clave] = st.text_area(etiqueta, height=alto, key=f"field_{clave}")

col1, col2 = st.columns([1, 1])
with col1:
    modelo = st.text_input("🤖 Modelo Ollama", key="modelo_input")
with col2:
    nombre_archivo = st.text_input("📁 Nombre de salida", key="nombre_archivo_input")

if st.button("🚀 Generar PDF", type="primary"):
    payload_snapshot = {
        "norma": norma,
        "usar_editor_enriquecido": usar_editor_enriquecido,
        "modelo": modelo,
        "nombre_archivo": nombre_archivo,
        "secciones": entradas,
    }
    run_id = save_snapshot(payload_snapshot)

    secciones_no_vacias = {k: v for k, v in entradas.items() if v.strip()}

    if not secciones_no_vacias:
        update_snapshot(run_id, status="error", error="No se ingresaron secciones con contenido.")
        st.warning("Escribe al menos una sección antes de generar.")
        st.stop()

    try:
        tiempo_ollama_total = 0.0
        tiempo_por_seccion: dict[str, float] = {}
        etiquetas_campos = {clave: etiqueta for clave, etiqueta, _, _ in campos}
        secciones_metadata = {"title", "authors", "keywords"}
        total_pasos = len(secciones_no_vacias) + 3
        paso_actual = 0

        etapa_actual = st.empty()
        detalle_etapa = st.empty()
        progress = st.progress(0, text="Etapa 0/{}: Inicializando...".format(total_pasos))

        with st.status("Generando documento...", expanded=True) as status:
            etapa_actual.info("⏳ Etapa actual: Preparando datos de entrada")
            status.write("Preparando secciones no vacías...")
            paso_actual += 1
            progress.progress(paso_actual / total_pasos, text=f"Etapa {paso_actual}/{total_pasos}: Preparación")

            latex_secciones: dict[str, str] = {}

            for index, (clave, texto) in enumerate(secciones_no_vacias.items(), start=1):
                nombre_seccion = etiquetas_campos.get(clave, clave)
                detalle_etapa.caption(f"Procesando sección {index}/{len(secciones_no_vacias)}")

                if clave in secciones_metadata:
                    etapa_actual.info(f"⏳ Etapa actual: Formateando sección '{nombre_seccion}'")
                    status.write(f"Formato local: preparando sección '{nombre_seccion}'...")
                    inicio_seccion = time.perf_counter()
                    latex_secciones[clave] = _metadata_a_latex(clave, texto)
                    duracion_seccion = time.perf_counter() - inicio_seccion
                else:
                    etapa_actual.info(f"⏳ Etapa actual: Ollama convirtiendo sección '{nombre_seccion}'")
                    status.write(f"Ollama: convirtiendo sección '{nombre_seccion}'...")
                    inicio_seccion = time.perf_counter()
                    latex_secciones[clave] = texto_a_latex(clave, texto, norma, modelo=modelo)
                    duracion_seccion = time.perf_counter() - inicio_seccion
                    tiempo_ollama_total += duracion_seccion

                tiempo_por_seccion[clave] = duracion_seccion

                paso_actual += 1
                progress.progress(
                    paso_actual / total_pasos,
                    text=f"Etapa {paso_actual}/{total_pasos}: Sección '{nombre_seccion}' completada",
                )

            etapa_actual.info("⏳ Etapa actual: Ensamblando documento LaTeX")
            detalle_etapa.caption("Insertando secciones en la plantilla seleccionada")
            status.write("Ensamblando documento final .tex...")

            status.write("Limpiando archivos previos de salida...")
            _limpiar_salida_previa(nombre_archivo)

            documento = ensamblar_documento(latex_secciones, norma)
            ruta_tex = guardar_tex(documento, nombre=nombre_archivo)

            paso_actual += 1
            progress.progress(paso_actual / total_pasos, text=f"Etapa {paso_actual}/{total_pasos}: Documento .tex listo")

            etapa_actual.info("⏳ Etapa actual: Compilando PDF con pdflatex")
            detalle_etapa.caption("Ejecutando compilación LaTeX")
            status.write("Compilando PDF con pdflatex...")

            inicio_pdf = time.perf_counter()
            ruta_pdf = compilar_pdf(ruta_tex)
            tiempo_pdf = time.perf_counter() - inicio_pdf
            tiempo_total = tiempo_ollama_total + tiempo_pdf

            paso_actual += 1
            progress.progress(paso_actual / total_pasos, text=f"Etapa {paso_actual}/{total_pasos}: PDF generado")

            etapa_actual.success("✅ Etapa actual: Generación finalizada")
            detalle_etapa.caption("Todo listo para descargar")
            status.update(label="✅ Generación completada", state="complete")

        update_snapshot(run_id, status="ok", pdf_path=ruta_pdf)

        st.success("✅ PDF generado exitosamente")

        col_metric_1, col_metric_2, col_metric_3 = st.columns(3)
        col_metric_1.metric("⏱️ Tiempo Ollama", f"{tiempo_ollama_total:.2f}s")
        col_metric_2.metric("🧾 Tiempo PDF", f"{tiempo_pdf:.2f}s")
        col_metric_3.metric("📊 Tiempo total", f"{tiempo_total:.2f}s")

        if tiempo_ollama_total > tiempo_pdf:
            st.info("Bottleneck detectado: Ollama (conversión texto → LaTeX).")
        else:
            st.info("Bottleneck detectado: compilación LaTeX a PDF.")

        with st.expander("Ver tiempos por sección (Ollama)"):
            for seccion, duracion in tiempo_por_seccion.items():
                st.write(f"- {seccion}: {duracion:.2f}s")

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
        update_snapshot(run_id, status="error", error=str(error))
        st.error(f"❌ Error: {error}")
        st.info("Revisa que Ollama esté corriendo y que `pdflatex` esté instalado.")
        st.caption(f"Histórico guardado con ID: {run_id}")
