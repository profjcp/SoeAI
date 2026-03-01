import os
import shutil
import subprocess
import time


def _run_pdflatex(ruta_tex: str, directorio: str, timeout_seg: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "-output-directory",
            directorio,
            ruta_tex,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seg,
    )


def compilar_pdf(ruta_tex: str, timeout_seg: int = 90) -> str:
    """Compila un archivo .tex a PDF con segunda pasada solo si es necesaria."""
    if shutil.which("pdflatex") is None:
        raise RuntimeError("No se encontró 'pdflatex' en el sistema. Instala TeX Live.")

    directorio = os.path.dirname(ruta_tex) or "."
    nombre_base = os.path.basename(ruta_tex).replace(".tex", "")
    ruta_pdf = f"{directorio}/{nombre_base}.pdf"

    inicio = time.perf_counter()

    try:
        primera_pasada = _run_pdflatex(ruta_tex, directorio, timeout_seg)
        salida_primera = f"{primera_pasada.stdout or ''}\n{primera_pasada.stderr or ''}"

        if primera_pasada.returncode != 0:
            raise RuntimeError(
                f"Error en 1ra pasada de pdflatex (rc={primera_pasada.returncode})."
                f"\n--- salida ---\n{salida_primera[-6000:]}"
            )

        requiere_segunda_pasada = any(
            marca in salida_primera
            for marca in [
                "Rerun to get cross-references right",
                "Label(s) may have changed",
                "There were undefined references",
                "Citation",
            ]
        )

        if requiere_segunda_pasada:
            segunda_pasada = _run_pdflatex(ruta_tex, directorio, timeout_seg)
            salida_segunda = f"{segunda_pasada.stdout or ''}\n{segunda_pasada.stderr or ''}"
            if segunda_pasada.returncode != 0:
                raise RuntimeError(
                    f"Error en 2da pasada de pdflatex (rc={segunda_pasada.returncode})."
                    f"\n--- salida ---\n{salida_segunda[-6000:]}"
                )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"pdflatex excedió el timeout de {timeout_seg}s para: {ruta_tex}."
        ) from error

    if os.path.exists(ruta_pdf):
        duracion = time.perf_counter() - inicio
        print(f"[pdf_compiler] PDF generado en {duracion:.2f}s -> {ruta_pdf}")
        return ruta_pdf

    raise RuntimeError("No se generó el PDF, aunque pdflatex no reportó error claro.")
