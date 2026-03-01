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


def _sanitizar_latex_generado(texto: str) -> str:
    lineas_limpias: list[str] = []

    for linea in texto.splitlines():
        linea_strip = linea.strip()

        if linea_strip.startswith("```"):
            continue

        if any(re.search(patron, linea_strip) for patron in COMANDOS_PROHIBIDOS):
            continue

        lineas_limpias.append(linea)

    resultado = "\n".join(lineas_limpias).strip()
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
    return _sanitizar_latex_generado(contenido)
