from pathlib import Path
import ast
import json
import os
import re
from typing import Any

import ollama


COMANDOS_PROHIBIDOS = [
    r"\\documentclass",
    r"\\usepackage",
    r"\\begin\{document\}",
    r"\\end\{document\}",
    r"\\maketitle",
    r"\\title\{",
    r"\\author\{",
    r"\\date\{",
    r"\\institute\{",
]

PATRONES_ENCABEZADOS = [
    r"^\s*\\section\*?\{.*\}\s*$",
    r"^\s*\\chapter\*?\{.*\}\s*$",
]

PATRONES_ESTRUCTURA = [
    r"^\s*\\part\*?\{.*\}\s*$",
    r"^\s*\\subsubsection\*?\{.*\}\s*$",
    r"^\s*\\paragraph\*?\{.*\}\s*$",
]

COMANDOS_LATEX_PERMITIDOS = {
    "textbf",
    "textit",
    "emph",
    "underline",
    "cite",
    "citep",
    "citet",
    "ref",
    "label",
    "url",
    "href",
    "footnote",
    "item",
    "subsection",
    "subsubsection",
}


def _ollama_options() -> dict[str, Any]:
    options: dict[str, Any] = {
        "temperature": float(os.getenv("OLLAMA_TEMPERATURE", "0.0")),
        "top_p": float(os.getenv("OLLAMA_TOP_P", "0.9")),
        "repeat_penalty": float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.1")),
        "num_ctx": int(os.getenv("OLLAMA_NUM_CTX", "8192")),
    }
    num_predict = os.getenv("OLLAMA_NUM_PREDICT")
    if num_predict:
        options["num_predict"] = int(num_predict)
    return options


def _ollama_timeout() -> float:
    return float(os.getenv("OLLAMA_TIMEOUT", "120"))


def _ollama_chat(
    messages: list[dict[str, str]],
    modelo: str,
    response_format: str | None = None,
) -> dict[str, Any]:
    client = ollama.Client(timeout=_ollama_timeout())
    return client.chat(
        model=modelo,
        messages=messages,
        options=_ollama_options(),
        format=response_format,
    )


def _normalizar_escapes_llm(texto: str) -> str:
    if not texto:
        return ""
    normalizado = texto.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", " ")
    normalizado = normalizado.replace("\r\n", "\n").replace("\r", "\n")
    return normalizado


def _neutralizar_comandos_desconocidos(texto: str) -> str:
    def _reemplazo(match: re.Match[str]) -> str:
        comando = match.group(1)
        if comando in COMANDOS_LATEX_PERMITIDOS:
            return f"\\{comando}"
        return comando

    return re.sub(r"\\([A-Za-z]+)", _reemplazo, texto)


def _escape_ampersand_suelto(texto: str) -> str:
    return re.sub(r"(?<!\\)&", r"\\&", texto)


def _extraer_texto_estructurado(texto: str) -> str:
    candidato = (texto or "").strip()
    if not (candidato.startswith("{") and candidato.endswith("}")):
        return texto

    data: Any
    try:
        data = json.loads(candidato)
    except Exception:
        try:
            data = ast.literal_eval(candidato)
        except Exception:
            return texto

    if not isinstance(data, dict):
        return texto

    for clave in ("text", "contenido", "content", "abstract", "body"):
        valor = data.get(clave)
        if isinstance(valor, str) and valor.strip():
            return valor
        if isinstance(valor, list):
            partes = [str(item).strip() for item in valor if str(item).strip()]
            if partes:
                return "\n".join(partes)

    return texto


def _sanitizar_referencias(texto: str) -> str:
    texto = _normalizar_escapes_llm(texto)
    texto = _neutralizar_comandos_desconocidos(texto)
    lineas_limpias: list[str] = []

    for linea in texto.splitlines():
        linea_strip = linea.strip()

        if re.match(r"\\begin\{(itemize|enumerate|thebibliography)\}", linea_strip):
            continue
        if re.match(r"\\end\{(itemize|enumerate|thebibliography)\}", linea_strip):
            continue

        linea = re.sub(r"^\s*\\item\s*", "", linea)
        linea = re.sub(r"^\s*\\bibitem\{[^}]*\}\s*", "", linea)
        lineas_limpias.append(linea)

    resultado = "\n".join(lineas_limpias)
    return _escape_ampersand_suelto(resultado)


def _sanitizar_contenido_seccion(texto: str) -> str:
    texto = _normalizar_escapes_llm(texto)
    texto = _neutralizar_comandos_desconocidos(texto)
    lineas_limpias: list[str] = []
    dentro_de_abstract = False

    for linea in texto.splitlines():
        linea_strip = linea.strip()

        if any(re.match(patron, linea_strip) for patron in PATRONES_ENCABEZADOS):
            continue

        if any(re.match(patron, linea_strip) for patron in PATRONES_ESTRUCTURA):
            continue

        if re.match(r"^\\begin\{abstract\}\s*$", linea_strip, flags=re.IGNORECASE):
            dentro_de_abstract = True
            continue

        if re.match(r"^\\end\{abstract\}\s*$", linea_strip, flags=re.IGNORECASE):
            dentro_de_abstract = False
            continue

        wrapper_match = re.match(r"^\\[Aa]bstract\s*\{?(.*)\}?\s*$", linea_strip)
        if wrapper_match:
            resto = wrapper_match.group(1).strip()
            if resto.endswith("}"):
                resto = resto[:-1].strip()
            if resto:
                lineas_limpias.append(resto)
            dentro_de_abstract = True
            continue

        if dentro_de_abstract and linea_strip == "}":
            dentro_de_abstract = False
            continue

        # Quita wrappers de comandos no deseados pero preserva su contenido textual.
        linea = re.sub(r"\\[A-Za-z]+\*?\{([^{}]*)\}", r"\1", linea)

        # Quita comandos estructurales sueltos (sin llaves).
        linea = re.sub(r"\\(section|subsection|chapter|part|paragraph|abstract)\*?\b", "", linea)

        # Normaliza llaves huérfanas para evitar ruido de salida.
        if linea.strip() in {"{", "}"}:
            continue

        lineas_limpias.append(linea)

    return "\n".join(lineas_limpias).strip()


def _sanitizar_latex_generado(texto: str, seccion: str) -> str:
    texto = _extraer_texto_estructurado(texto)
    texto = _normalizar_escapes_llm(texto)
    texto = _neutralizar_comandos_desconocidos(texto)
    lineas_limpias: list[str] = []

    for linea in texto.splitlines():
        linea_strip = linea.strip()

        if linea_strip.startswith("```"):
            continue

        if any(re.search(patron, linea_strip) for patron in COMANDOS_PROHIBIDOS):
            continue

        lineas_limpias.append(linea)

    resultado = "\n".join(lineas_limpias).strip()

    if seccion.lower() == "references":
        resultado = _sanitizar_referencias(resultado)
    else:
        resultado = _sanitizar_contenido_seccion(resultado)

    resultado = resultado.replace(r"\n", "\n").replace(r"\t", " ")

    return resultado


def _normalizar_json_laxo(texto: str) -> str:
    normalizado = (texto or "").replace("\r\n", "\n").replace("\r", "\n")
    normalizado = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", normalizado)
    normalizado = re.sub(r"\\(?![\"\\/bfnrtu])", r"\\\\", normalizado)
    return normalizado


def _extraer_json(texto: str) -> dict[str, Any]:
    limpio = (texto or "").strip()
    limpio = re.sub(r"^\s*```(?:json)?\s*", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"\s*```\s*$", "", limpio)

    try:
        return json.loads(limpio)
    except Exception:
        inicio = limpio.find("{")
        fin = limpio.rfind("}")
        if inicio == -1 or fin == -1 or fin <= inicio:
            raise ValueError("No se pudo parsear JSON de la respuesta del modelo.")

        candidato = limpio[inicio : fin + 1]
        try:
            return json.loads(candidato)
        except Exception:
            candidato_laxo = _normalizar_json_laxo(candidato)
            try:
                return json.loads(candidato_laxo)
            except Exception as exc:
                raise ValueError("No se pudo parsear JSON de la respuesta del modelo.") from exc


def texto_a_latex(seccion: str, contenido: str, norma: str, modelo: str = "llama3.2") -> str:
    """Convierte texto plano a LaTeX por sección usando Ollama."""
    prompt_path = Path("prompts") / f"{norma.lower()}_prompt.txt"

    if not prompt_path.exists():
        raise FileNotFoundError(f"No se encontró el prompt: {prompt_path}")

    base_prompt = prompt_path.read_text(encoding="utf-8")

    prompt = f"""{base_prompt}

Sección: {seccion}
Texto del autor:
{contenido}

Genera SOLO el código LaTeX de esta sección, sin explicaciones."""

    response = _ollama_chat(
        messages=[{"role": "user", "content": prompt}],
        modelo=modelo,
    )

    contenido = response["message"]["content"].strip()
    return _sanitizar_latex_generado(contenido, seccion)


def texto_a_latex_batch(secciones: dict[str, str], norma: str, modelo: str = "llama3.2") -> dict[str, str]:
    """Convierte múltiples secciones en una sola llamada al modelo."""
    payload = {k: (v or "").strip() for k, v in secciones.items()}

    prompt = (
        "Convierte texto plano a LaTeX por secciones.\n"
        f"Norma: {norma}\n"
        "Responde SOLO JSON válido con las mismas claves del input.\n"
        "No incluyas preámbulo, begin/end document, títulos de sección, ni markdown.\n\n"
        f"INPUT_JSON:\n{json.dumps(payload, ensure_ascii=False)}"
    )

    response = _ollama_chat(
        messages=[
            {"role": "system", "content": "Eres un formateador LaTeX estricto. Responde solo JSON válido."},
            {"role": "user", "content": prompt},
        ],
        modelo=modelo,
        response_format="json",
    )

    contenido = response["message"]["content"].strip()
    try:
        data = _extraer_json(contenido)
    except ValueError:
        return {
            seccion: texto_a_latex(seccion, original, norma, modelo=modelo)
            for seccion, original in payload.items()
        }

    salida: dict[str, str] = {}
    for seccion, original in payload.items():
        generado = str(data.get(seccion, original))
        salida[seccion] = _sanitizar_latex_generado(generado, seccion)

    return salida
