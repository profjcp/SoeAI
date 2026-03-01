from pathlib import Path
import re

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


def _escape_ampersand_suelto(texto: str) -> str:
    return re.sub(r"(?<!\\)&", r"\\&", texto)


def _sanitizar_referencias(texto: str) -> str:
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
    lineas_limpias: list[str] = []

    for linea in texto.splitlines():
        linea_strip = linea.strip()

        if any(re.match(patron, linea_strip) for patron in PATRONES_ENCABEZADOS):
            continue

        if linea_strip.startswith(r"\abstract{"):
            resto = linea_strip[len(r"\abstract{") :].strip()
            if resto.endswith("}"):
                resto = resto[:-1].strip()
            if resto:
                lineas_limpias.append(resto)
            continue

        if linea_strip == "}":
            continue

        lineas_limpias.append(linea)

    return "\n".join(lineas_limpias).strip()


def _sanitizar_latex_generado(texto: str, seccion: str) -> str:
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

    return resultado


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

    response = ollama.chat(
        model=modelo,
        messages=[{"role": "user", "content": prompt}],
    )

    contenido = response["message"]["content"].strip()
    return _sanitizar_latex_generado(contenido, seccion)
