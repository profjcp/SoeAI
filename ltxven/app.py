import os
import re
import time
import base64
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


DEFAULT_OLLAMA_MODEL = "llama3.2"


def _modelo_base() -> str:
    return (os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL).strip()


def _modelo_fallback() -> str:
    return (os.getenv("OLLAMA_FALLBACK_MODEL", DEFAULT_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL).strip()


def _resolver_modelos(modelo_preferido: str) -> list[str]:
    principal = (modelo_preferido or "").strip() or _modelo_base()
    fallback = _modelo_fallback()
    modelos = [principal]
    if fallback and fallback not in modelos:
        modelos.append(fallback)
    return modelos


def _generar_seccion_con_fallback(seccion: str, texto: str, norma: str, modelos: list[str]) -> tuple[str, str]:
    ultimo_error: Exception | None = None
    errores: list[str] = []
    for modelo in modelos:
        try:
            return texto_a_latex(seccion=seccion, contenido=texto, norma=norma, modelo=modelo), modelo
        except TypeError:
            try:
                return texto_a_latex(texto, seccion, norma, modelo=modelo), modelo
            except Exception as error:  # noqa: PERF203
                ultimo_error = error
                errores.append(f"{modelo}: {type(error).__name__}: {error}")
        except Exception as error:  # noqa: PERF203
            ultimo_error = error
            errores.append(f"{modelo}: {type(error).__name__}: {error}")

    detalle = " | ".join(errores) if errores else "sin detalle"
    raise RuntimeError(
        f"No se pudo convertir la sección '{seccion}'. Detalle: {detalle}"
    ) from ultimo_error


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

    if isinstance(html_content, dict):
        ops = html_content.get("ops", [])
        partes: list[str] = []
        for op in ops:
            if not isinstance(op, dict):
                continue
            insercion = op.get("insert", "")
            if isinstance(insercion, str):
                partes.append(insercion)
        html_content = "\n".join(partes)

    if not isinstance(html_content, str):
        html_content = str(html_content)

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
    st.session_state["modelo_input"] = payload.get("modelo", _modelo_base())
    st.session_state["nombre_archivo_input"] = payload.get("nombre_archivo", "articulo")

    secciones = payload.get("secciones", {})
    secciones_raw = payload.get("secciones_raw", {})

    def _texto_a_html_simple(valor: str) -> str:
        if not valor.strip():
            return ""
        lineas = [linea.strip() for linea in valor.splitlines() if linea.strip()]
        return "".join(f"<p>{linea}</p>" for linea in lineas)

    if "restore_nonce" not in st.session_state:
        st.session_state["restore_nonce"] = 0
    st.session_state["restore_nonce"] += 1

    if isinstance(secciones, dict):
        for clave, valor in secciones.items():
            texto_plano = str(valor or "")
            st.session_state[f"field_{clave}"] = texto_plano

            if isinstance(secciones_raw, dict) and clave in secciones_raw:
                st.session_state[f"quill_seed_{clave}"] = str(secciones_raw.get(clave) or "")
            else:
                st.session_state[f"quill_seed_{clave}"] = _texto_a_html_simple(texto_plano)


def _estado_color(estado: str) -> str:
    mapping = {
        "pending": "#cbd5e1",
        "running": "#f59e0b",
        "done": "#16a34a",
        "error": "#dc2626",
    }
    return mapping.get(estado, "#cbd5e1")


def _render_flujo_pipeline(steps: list[dict[str, str | float]]) -> None:
    st.markdown("### Flujo del pipeline")
    if not steps:
        st.info("Aún no hay ejecución en esta sesión.")
        return

    timeline_parts: list[str] = []
    detalle_activo = ""
    paso_activo = ""

    for idx, step in enumerate(steps, start=1):
        estado = str(step.get("status", "pending"))
        nombre = str(step.get("name", f"Paso {idx}"))
        detalle = str(step.get("detail", "")).strip()

        if estado in {"running", "error"} and not paso_activo:
            paso_activo = f"Paso {idx}: {nombre}"
            detalle_activo = detalle

        timeline_parts.append(
            f"""
            <div class='tl-item'>
                <div class='tl-node tl-{estado}' style='border-color:{_estado_color(estado)}; color:{_estado_color(estado)};'>
                    {idx}
                </div>
                <div class='tl-label'>{nombre}</div>
            </div>
            """
        )

        if idx < len(steps):
            siguiente_estado = str(steps[idx].get("status", "pending"))
            line_class = "tl-line-active" if siguiente_estado in {"running", "done"} else "tl-line-idle"
            timeline_parts.append(f"<div class='tl-line {line_class}'></div>")

    st.markdown(
        """
        <style>
        .tl-wrap {
            display: flex;
            align-items: center;
            gap: 8px;
            overflow-x: auto;
            padding: 6px 0 2px 0;
            margin-bottom: 4px;
        }
        .tl-item {
            min-width: 110px;
            text-align: center;
            flex-shrink: 0;
        }
        .tl-node {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            border: 2px solid;
            margin: 0 auto 4px auto;
            font-size: 13px;
            font-weight: 700;
            display: flex;
            align-items: center;
            justify-content: center;
            background: white;
        }
        .tl-label {
            font-size: 11px;
            line-height: 1.2;
            color: #334155;
        }
        .tl-line {
            height: 2px;
            min-width: 34px;
            margin-top: -14px;
            flex-shrink: 0;
        }
        .tl-line-active { background: #16a34a; }
        .tl-line-idle { background: #cbd5e1; }
        .tl-running {
            box-shadow: 0 0 0 rgba(245,158,11, 0.6);
            animation: tl-pulse 1.2s infinite;
        }
        .tl-error {
            background: #fff1f2;
        }
        @keyframes tl-pulse {
            0% { box-shadow: 0 0 0 0 rgba(245,158,11, 0.45); }
            70% { box-shadow: 0 0 0 10px rgba(245,158,11, 0); }
            100% { box-shadow: 0 0 0 0 rgba(245,158,11, 0); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(f"<div class='tl-wrap'>{''.join(timeline_parts)}</div>", unsafe_allow_html=True)

    if paso_activo:
        st.caption(f"{paso_activo} · {detalle_activo}" if detalle_activo else paso_activo)


def _run_review_skills(tex_content: str, selected_skills: dict[str, bool]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    if selected_skills.get("style"):
        if re.search(r"\s{2,}", tex_content):
            findings.append({
                "severity": "info",
                "skill": "Estilo académico",
                "message": "Se detectaron espacios repetidos; considera limpieza adicional de estilo.",
            })

    if selected_skills.get("citations"):
        citas = len(re.findall(r"\\cite\w*\{", tex_content))
        refs = len(re.findall(r"\\bibitem\{", tex_content))
        if refs == 0:
            findings.append({
                "severity": "warning",
                "skill": "Referencias y citas",
                "message": "No se detectaron entradas \\bibitem en el resultado final.",
            })
        elif citas == 0:
            findings.append({
                "severity": "info",
                "skill": "Referencias y citas",
                "message": "Hay referencias pero no se detectaron citas dentro del texto.",
            })

    if selected_skills.get("consistency"):
        if "%%" in tex_content:
            findings.append({
                "severity": "warning",
                "skill": "Consistencia por secciones",
                "message": "Se detectaron marcadores sin reemplazar en la plantilla (%%...%%).",
            })

    if selected_skills.get("latex_errors"):
        prohibidos = [r"\\begin\{document\}", r"\\end\{document\}", r"\\documentclass", r"\\usepackage"]
        for patron in prohibidos:
            if re.search(patron, tex_content):
                findings.append({
                    "severity": "blocking",
                    "skill": "Errores LaTeX comunes",
                    "message": f"Se detectó patrón no permitido: {patron}",
                })

    return findings


def _render_pdf_preview(pdf_path: str) -> None:
    if not pdf_path or not Path(pdf_path).exists():
        st.info("No hay PDF disponible para vista previa.")
        return
    pdf_bytes = Path(pdf_path).read_bytes()
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    iframe = (
        f'<iframe src="data:application/pdf;base64,{b64}" '
        'width="100%" height="820" type="application/pdf"></iframe>'
    )
    st.markdown(iframe, unsafe_allow_html=True)


def _plantillas_disponibles(norma: str) -> list[str]:
    templates_dir = Path("templates")
    if not templates_dir.exists():
        return []

    norma_prefix = f"{norma.lower()}_"
    candidatas = sorted(
        [p.name for p in templates_dir.glob("*.tex") if p.name.startswith(norma_prefix)]
    )
    if not candidatas:
        default_name = f"{norma.lower()}_template.tex"
        default_path = templates_dir / default_name
        if default_path.exists():
            return [default_name]
    return candidatas


load_dotenv()

st.set_page_config(page_title="LaTeX Article Generator", layout="wide")
st.title("📄 Generador de Artículos Científicos")
st.caption("Panel izquierdo: configuración y checklist. Panel derecho: contenido del artículo, flujo y resultados.")

if "norma_select" not in st.session_state:
    st.session_state["norma_select"] = "IEEE"
if "toggle_rich_editor" not in st.session_state:
    st.session_state["toggle_rich_editor"] = True
if "modelo_input" not in st.session_state:
    st.session_state["modelo_input"] = _modelo_base()
if "nombre_archivo_input" not in st.session_state:
    st.session_state["nombre_archivo_input"] = "articulo"
if "restore_nonce" not in st.session_state:
    st.session_state["restore_nonce"] = 0
if "selected_snapshot" not in st.session_state:
    st.session_state["selected_snapshot"] = ""
if "selected_template" not in st.session_state:
    st.session_state["selected_template"] = ""
if "last_run" not in st.session_state:
    st.session_state["last_run"] = None
if "skill_style" not in st.session_state:
    st.session_state["skill_style"] = True
if "skill_citations" not in st.session_state:
    st.session_state["skill_citations"] = True
if "skill_consistency" not in st.session_state:
    st.session_state["skill_consistency"] = True
if "skill_latex_errors" not in st.session_state:
    st.session_state["skill_latex_errors"] = True

panel_right = st.container()

norma = st.session_state.get("norma_select", "IEEE")
usar_editor_enriquecido = st.session_state.get("toggle_rich_editor", True)

templates = _plantillas_disponibles(norma)
default_template = f"{norma.lower()}_template.tex"
if not templates:
    templates = [default_template]

if st.session_state.get("selected_template") not in templates:
    st.session_state["selected_template"] = default_template if default_template in templates else templates[0]

template_name = st.session_state.get("selected_template", templates[0])

skill_style = st.session_state.get("skill_style", True)
skill_citations = st.session_state.get("skill_citations", True)
skill_consistency = st.session_state.get("skill_consistency", True)
skill_latex_errors = st.session_state.get("skill_latex_errors", True)

with st.sidebar:
    st.subheader("📚 Sidebar")
    snapshots = list_snapshots(limit=30)
    opciones = [""] + [f"{item['run_id']} | {item.get('status', 'pending')}" for item in snapshots]
    seleccion = st.selectbox("Recuperar ejecución", opciones, key="selected_snapshot")

    if st.button("Cargar histórico", use_container_width=True):
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

    norma = st.selectbox("📐 Norma", ["IEEE", "APA"], key="norma_select")
    usar_editor_enriquecido = st.toggle(
        "📝 Editor enriquecido",
        key="toggle_rich_editor",
        help="Permite aplicar formato visual al escribir; la app lo convierte automáticamente a texto limpio para LaTeX.",
    )

    if usar_editor_enriquecido and st_quill is None:
        st.warning("Editor enriquecido no disponible aún. Instala dependencias con: pip install -r requirements.txt")

    st.markdown("### 🧩 Template Manager")
    templates = _plantillas_disponibles(norma)
    default_template = f"{norma.lower()}_template.tex"
    if not templates:
        templates = [default_template]

    if st.session_state.get("selected_template") not in templates:
        st.session_state["selected_template"] = default_template if default_template in templates else templates[0]

    template_name = st.selectbox(
        "Plantilla activa",
        templates,
        key="selected_template",
    )
    st.caption(f"Compatibilidad esperada con norma: {norma}")

    template_path = Path("templates") / template_name
    if template_path.exists():
        with st.expander("Ver placeholders de plantilla"):
            content = template_path.read_text(encoding="utf-8")
            placeholders = sorted(set(re.findall(r"%%[A-Z_]+%%", content)))
            if placeholders:
                for p in placeholders:
                    st.write(f"- {p}")
            else:
                st.caption("No se detectaron placeholders.")

    modelo = st.text_input("🤖 Modelo Ollama", key="modelo_input")
    st.caption(f"Modelo recomendado para estabilidad: {DEFAULT_OLLAMA_MODEL}")
    nombre_archivo = st.text_input("📁 Nombre de salida", key="nombre_archivo_input")

    st.markdown("### ✅ Skills de revisión")
    skill_style = st.checkbox("Revisión de estilo académico", key="skill_style")
    skill_citations = st.checkbox("Revisión de referencias y citas", key="skill_citations")
    skill_consistency = st.checkbox("Revisión de consistencia de secciones", key="skill_consistency")
    skill_latex_errors = st.checkbox("Revisión de errores LaTeX comunes", key="skill_latex_errors")

norma = st.session_state.get("norma_select", norma)
usar_editor_enriquecido = st.session_state.get("toggle_rich_editor", usar_editor_enriquecido)
template_name = st.session_state.get("selected_template", template_name)
skill_style = st.session_state.get("skill_style", skill_style)
skill_citations = st.session_state.get("skill_citations", skill_citations)
skill_consistency = st.session_state.get("skill_consistency", skill_consistency)
skill_latex_errors = st.session_state.get("skill_latex_errors", skill_latex_errors)

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
entradas_raw: dict[str, str] = {}
with panel_right:
    st.subheader("✍️ Contenido y ejecución")
    with st.expander("✍️ Contenido del artículo", expanded=True):
        for clave, etiqueta, tipo, alto in campos:
            if tipo == "input":
                valor_input = st.text_input(etiqueta, key=f"field_{clave}")
                entradas[clave] = valor_input
                entradas_raw[clave] = valor_input
            else:
                if usar_editor_enriquecido and st_quill is not None:
                    st.markdown(f"**{etiqueta}**")
                    quill_key = f"quill_{clave}_{st.session_state.get('restore_nonce', 0)}"
                    contenido_html = st_quill(
                        key=quill_key,
                        value=st.session_state.get(f"quill_seed_{clave}", ""),
                        placeholder=f"Escribe aquí: {etiqueta}",
                        html=True,
                        toolbar=None,
                    )
                    entradas[clave] = _rich_html_to_text(contenido_html)
                    entradas_raw[clave] = contenido_html or ""
                    st.session_state[f"quill_seed_{clave}"] = contenido_html or st.session_state.get(
                        f"quill_seed_{clave}", ""
                    )
                else:
                    valor_text_area = st.text_area(etiqueta, height=alto, key=f"field_{clave}")
                    entradas[clave] = valor_text_area
                    entradas_raw[clave] = valor_text_area

with panel_right:
    st.subheader("🧭 Flujo y resultados")
    render_area = st.container()

generar = panel_right.button("🚀 Generar PDF", type="primary", use_container_width=True)

if generar:
    payload_snapshot = {
        "norma": norma,
        "usar_editor_enriquecido": usar_editor_enriquecido,
        "modo_batch": False,
        "modelo": modelo,
        "nombre_archivo": nombre_archivo,
        "template": template_name,
        "review_skills": {
            "style": skill_style,
            "citations": skill_citations,
            "consistency": skill_consistency,
            "latex_errors": skill_latex_errors,
        },
        "secciones": entradas,
        "secciones_raw": entradas_raw,
    }
    run_id = save_snapshot(payload_snapshot)

    secciones_no_vacias = {k: v for k, v in entradas.items() if v.strip()}

    if not secciones_no_vacias:
        update_snapshot(run_id, status="error", error="No se ingresaron secciones con contenido.")
        panel_right.warning("Escribe al menos una sección antes de generar.")
        st.stop()

    try:
        tiempo_ollama_total = 0.0
        tiempo_por_seccion: dict[str, float] = {}
        modelos_usados: set[str] = set()
        etiquetas_campos = {clave: etiqueta for clave, etiqueta, _, _ in campos}
        secciones_metadata = {"title", "authors", "keywords"}
        secciones_ollama = {k: v for k, v in secciones_no_vacias.items() if k not in secciones_metadata}
        modelos_preferidos = _resolver_modelos(modelo)
        total_pasos = len(secciones_no_vacias) + 4

        skill_cfg = {
            "style": skill_style,
            "citations": skill_citations,
            "consistency": skill_consistency,
            "latex_errors": skill_latex_errors,
        }

        steps = [
            {"name": "Preparación de entrada", "status": "pending", "detail": "Validando y limpiando secciones."},
            {"name": "Conversión por secciones", "status": "pending", "detail": "Conversión de texto plano a LaTeX."},
            {"name": "Ensamblado de documento", "status": "pending", "detail": "Inserción sobre la plantilla seleccionada."},
            {"name": "Compilación PDF", "status": "pending", "detail": "Ejecución de pdflatex."},
            {"name": "Revisión posterior", "status": "pending", "detail": "Aplicación de skills de revisión."},
        ]

        paso_actual = 0

        with panel_right:
            etapa_actual = st.empty()
            detalle_etapa = st.empty()
            progress = st.progress(0, text="Etapa 0/{}: Inicializando...".format(total_pasos))
            with render_area:
                _render_flujo_pipeline(steps)

        with panel_right:
            status_holder = st.status("Generando documento...", expanded=True)

        with status_holder as status:
            etapa_actual.info("⏳ Etapa actual: Preparando datos de entrada")
            status.write("Preparando secciones no vacías...")
            status.write(f"Modelos en orden de uso: {', '.join(modelos_preferidos)}")
            steps[0]["status"] = "running"
            paso_actual += 1
            progress.progress(paso_actual / total_pasos, text=f"Etapa {paso_actual}/{total_pasos}: Preparación")
            with render_area:
                _render_flujo_pipeline(steps)

            latex_secciones: dict[str, str] = {}

            metadata_items = [(k, v) for k, v in secciones_no_vacias.items() if k in secciones_metadata]

            for index, (clave, texto) in enumerate(metadata_items, start=1):
                nombre_seccion = etiquetas_campos.get(clave, clave)
                detalle_etapa.caption(f"Procesando sección metadata {index}/{len(metadata_items)}")
                etapa_actual.info(f"⏳ Etapa actual: Formateando sección '{nombre_seccion}'")
                status.write(f"Formato local: preparando sección '{nombre_seccion}'...")
                inicio_seccion = time.perf_counter()
                latex_secciones[clave] = _metadata_a_latex(clave, texto)
                duracion_seccion = time.perf_counter() - inicio_seccion

                tiempo_por_seccion[clave] = duracion_seccion

                paso_actual += 1
                progress.progress(
                    paso_actual / total_pasos,
                    text=f"Etapa {paso_actual}/{total_pasos}: Sección '{nombre_seccion}' completada",
                )

            if secciones_ollama:
                steps[1]["status"] = "running"
                for clave, texto in secciones_ollama.items():
                    nombre_seccion = etiquetas_campos.get(clave, clave)
                    etapa_actual.info(f"⏳ Etapa actual: Ollama convirtiendo sección '{nombre_seccion}'")
                    status.write(f"Ollama: convirtiendo sección '{nombre_seccion}'...")
                    inicio_seccion = time.perf_counter()
                    latex_generado, modelo_usado = _generar_seccion_con_fallback(
                        clave,
                        texto,
                        norma,
                        modelos_preferidos,
                    )
                    latex_secciones[clave] = latex_generado
                    modelos_usados.add(modelo_usado)
                    if modelo_usado != modelos_preferidos[0]:
                        status.write(f"Sección '{nombre_seccion}' usó fallback: {modelo_usado}")
                    duracion_seccion = time.perf_counter() - inicio_seccion
                    tiempo_por_seccion[clave] = duracion_seccion
                    tiempo_ollama_total += duracion_seccion

                    paso_actual += 1
                    progress.progress(
                        paso_actual / total_pasos,
                        text=f"Etapa {paso_actual}/{total_pasos}: Sección '{nombre_seccion}' completada",
                    )
                    with render_area:
                        _render_flujo_pipeline(steps)

            steps[0]["status"] = "done"
            steps[1]["status"] = "done"

            etapa_actual.info("⏳ Etapa actual: Ensamblando documento LaTeX")
            detalle_etapa.caption("Insertando secciones en la plantilla seleccionada")
            status.write("Ensamblando documento final .tex...")
            steps[2]["status"] = "running"

            status.write("Limpiando archivos previos de salida...")
            _limpiar_salida_previa(nombre_archivo)

            documento = ensamblar_documento(latex_secciones, norma)
            ruta_tex = guardar_tex(documento, nombre=nombre_archivo)
            steps[2]["status"] = "done"

            paso_actual += 1
            progress.progress(paso_actual / total_pasos, text=f"Etapa {paso_actual}/{total_pasos}: Documento .tex listo")
            with render_area:
                _render_flujo_pipeline(steps)

            etapa_actual.info("⏳ Etapa actual: Compilando PDF con pdflatex")
            detalle_etapa.caption("Ejecutando compilación LaTeX")
            status.write("Compilando PDF con pdflatex...")
            steps[3]["status"] = "running"

            inicio_pdf = time.perf_counter()
            ruta_pdf = compilar_pdf(ruta_tex)
            tiempo_pdf = time.perf_counter() - inicio_pdf
            tiempo_total = tiempo_ollama_total + tiempo_pdf
            steps[3]["status"] = "done"

            paso_actual += 1
            progress.progress(paso_actual / total_pasos, text=f"Etapa {paso_actual}/{total_pasos}: PDF generado")
            with render_area:
                _render_flujo_pipeline(steps)

            etapa_actual.info("⏳ Etapa actual: Ejecutando revisión posterior")
            steps[4]["status"] = "running"
            findings = _run_review_skills(documento, skill_cfg)
            steps[4]["status"] = "done"

            paso_actual += 1
            progress.progress(paso_actual / total_pasos, text=f"Etapa {paso_actual}/{total_pasos}: Revisión completada")
            with render_area:
                _render_flujo_pipeline(steps)

            etapa_actual.success("✅ Etapa actual: Generación finalizada")
            detalle_etapa.caption("Todo listo para descargar")
            status.update(label="✅ Generación completada", state="complete")

        update_snapshot(run_id, status="ok", pdf_path=ruta_pdf)

        st.session_state["last_run"] = {
            "run_id": run_id,
            "ruta_tex": ruta_tex,
            "ruta_pdf": ruta_pdf,
            "tiempo_ollama": tiempo_ollama_total,
            "tiempo_pdf": tiempo_pdf,
            "tiempo_total": tiempo_total,
            "tiempo_por_seccion": tiempo_por_seccion,
            "modelos_usados": sorted(modelos_usados),
            "llamadas_ollama": len(secciones_ollama),
            "pipeline_steps": steps,
            "findings": findings,
            "documento": documento,
            "norma": norma,
            "template": template_name,
        }

    except Exception as error:
        update_snapshot(run_id, status="error", error=str(error))
        for step in steps:
            if step["status"] == "running":
                step["status"] = "error"
        panel_right.error(f"❌ Error: {error}")
        panel_right.info("Revisa que Ollama esté corriendo y que pdflatex esté instalado.")
        panel_right.caption(f"Histórico guardado con ID: {run_id}")

last_run = st.session_state.get("last_run")

with panel_right:
    tabs = st.tabs(["Pipeline", "Resultados", "Vista previa"])

    with tabs[0]:
        if last_run:
            _render_flujo_pipeline(last_run.get("pipeline_steps", []))
            st.caption(f"Run ID: {last_run.get('run_id', '')}")
            st.caption(f"Norma: {last_run.get('norma', '')} | Template: {last_run.get('template', '')}")
        else:
            st.info("Aún no hay resultados para mostrar en flujo.")

    with tabs[1]:
        if last_run:
            st.success("✅ PDF generado exitosamente")
            m1, m2, m3 = st.columns(3)
            m1.metric("⏱️ Tiempo Ollama", f"{last_run['tiempo_ollama']:.2f}s")
            m2.metric("🧾 Tiempo PDF", f"{last_run['tiempo_pdf']:.2f}s")
            m3.metric("📊 Tiempo total", f"{last_run['tiempo_total']:.2f}s")

            if last_run["tiempo_ollama"] > last_run["tiempo_pdf"]:
                st.info("Bottleneck detectado: Ollama (conversión texto → LaTeX).")
            else:
                st.info("Bottleneck detectado: compilación LaTeX a PDF.")

            with st.expander("Ver tiempos por sección"):
                for seccion, duracion in last_run["tiempo_por_seccion"].items():
                    st.write(f"- {seccion}: {duracion:.2f}s")

            if last_run.get("modelos_usados"):
                st.caption(f"Modelos usados: {', '.join(last_run['modelos_usados'])}")
            st.caption(f"Llamadas estimadas a Ollama: {last_run.get('llamadas_ollama', 0)}")

            with open(last_run["ruta_tex"], "rb") as tex_file:
                st.download_button(
                    "⬇️ Descargar .tex",
                    tex_file,
                    Path(last_run["ruta_tex"]).name,
                    "application/x-tex",
                )

            with open(last_run["ruta_pdf"], "rb") as pdf_file:
                st.download_button(
                    "⬇️ Descargar PDF",
                    pdf_file,
                    Path(last_run["ruta_pdf"]).name,
                    "application/pdf",
                )
        else:
            st.info("Aún no hay resultados para mostrar.")

    with tabs[2]:
        if last_run:
            preview_tabs = st.tabs(["PDF", "LaTeX"])
            with preview_tabs[0]:
                _render_pdf_preview(last_run["ruta_pdf"])
            with preview_tabs[1]:
                tex_path = last_run["ruta_tex"]
                if Path(tex_path).exists():
                    st.code(Path(tex_path).read_text(encoding="utf-8"), language="latex")
                else:
                    st.info("No hay archivo .tex disponible para vista previa.")
        else:
            st.info("Genera un documento para habilitar la vista previa.")

with st.sidebar:
    st.markdown("### 📋 Resultado de checklist")
    if last_run:
        findings = last_run.get("findings", [])
        if not findings:
            st.success("Sin hallazgos críticos en skills seleccionadas.")
        else:
            for f in findings:
                sev = f.get("severity", "info").upper()
                st.write(f"- [{sev}] {f.get('skill', '')}: {f.get('message', '')}")
    else:
        st.info("Aún no hay revisión ejecutada en esta sesión.")
