from pathlib import Path

import ollama


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

    return response["message"]["content"].strip()
