import os
import subprocess


def compilar_pdf(ruta_tex: str) -> str:
    """Compila un archivo .tex a PDF con dos pasadas de pdflatex."""
    directorio = os.path.dirname(ruta_tex) or "."
    nombre_base = os.path.basename(ruta_tex).replace(".tex", "")

    last_result: subprocess.CompletedProcess[str] | None = None

    for _ in range(2):
        last_result = subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-output-directory",
                directorio,
                ruta_tex,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    ruta_pdf = f"{directorio}/{nombre_base}.pdf"

    if os.path.exists(ruta_pdf):
        return ruta_pdf

    stderr = last_result.stderr if last_result else "Sin salida de error"
    stdout = last_result.stdout if last_result else "Sin salida estándar"
    raise RuntimeError(f"Error compilando PDF.\nSTDERR:\n{stderr}\n\nSTDOUT:\n{stdout}")
