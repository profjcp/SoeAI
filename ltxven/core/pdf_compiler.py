import os
import re
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


def _auto_reparar_tex(ruta_tex: str) -> bool:
    if not os.path.exists(ruta_tex):
        return False

    with open(ruta_tex, "r", encoding="utf-8") as file_tex:
        contenido_original = file_tex.read()

    lineas_reparadas: list[str] = []
    dentro_abstract_wrapper = False
    buffer_abstract: list[str] = []
    ultimo_no_vacio: str | None = None

    for linea in contenido_original.splitlines():
        linea_strip = linea.strip()

        if not dentro_abstract_wrapper and (
            linea_strip.startswith(r"\Abstract{")
            or linea_strip.startswith(r"\abstract{")
        ):
            resto = linea_strip[linea_strip.find("{") + 1 :]
            if resto.endswith("}"):
                resto = resto[:-1].strip()
                if resto:
                    linea = resto
                    linea_strip = linea.strip()
                else:
                    continue
            else:
                dentro_abstract_wrapper = True
                if resto.strip():
                    buffer_abstract.append(resto)
                continue

        elif dentro_abstract_wrapper:
            if linea_strip == "}":
                dentro_abstract_wrapper = False
                merged = " ".join(parte.strip() for parte in buffer_abstract if parte.strip())
                buffer_abstract = []
                if not merged:
                    continue
                linea = merged
                linea_strip = linea.strip()
            else:
                buffer_abstract.append(linea)
                continue

        if linea_strip in {r"\begin{abstract}", r"\end{abstract}"}:
            continue

        if (
            linea_strip
            and linea_strip == ultimo_no_vacio
            and re.match(r"^\\(section|chapter)\*?\{.*\}$", linea_strip)
        ):
            continue

        linea = re.sub(r"(?<!\\)&", r"\\&", linea)

        lineas_reparadas.append(linea)
        if linea_strip:
            ultimo_no_vacio = linea_strip

    contenido_reparado = "\n".join(lineas_reparadas).strip() + "\n"

    if contenido_reparado == contenido_original:
        return False

    with open(ruta_tex, "w", encoding="utf-8") as file_tex:
        file_tex.write(contenido_reparado)

    base = ruta_tex[:-4] if ruta_tex.endswith(".tex") else ruta_tex
    for ext in (".aux", ".log", ".out"):
        artefacto = f"{base}{ext}"
        if os.path.exists(artefacto):
            os.remove(artefacto)

    return True


def _compilar_con_pasadas(ruta_tex: str, directorio: str, timeout_seg: int) -> tuple[bool, str]:
    primera_pasada = _run_pdflatex(ruta_tex, directorio, timeout_seg)
    salida_primera = f"{primera_pasada.stdout or ''}\n{primera_pasada.stderr or ''}"

    if primera_pasada.returncode != 0:
        return False, salida_primera

    requiere_segunda_pasada = any(
        marca in salida_primera
        for marca in [
            "Rerun to get cross-references right",
            "Label(s) may have changed",
            "There were undefined references",
            "Citation",
        ]
    )

    if not requiere_segunda_pasada:
        return True, salida_primera

    segunda_pasada = _run_pdflatex(ruta_tex, directorio, timeout_seg)
    salida_segunda = f"{segunda_pasada.stdout or ''}\n{segunda_pasada.stderr or ''}"

    if segunda_pasada.returncode != 0:
        return False, salida_segunda

    return True, salida_segunda


def compilar_pdf(ruta_tex: str, timeout_seg: int = 90) -> str:
    """Compila un archivo .tex a PDF con segunda pasada solo si es necesaria."""
    if shutil.which("pdflatex") is None:
        raise RuntimeError("No se encontró 'pdflatex' en el sistema. Instala TeX Live.")

    directorio = os.path.dirname(ruta_tex) or "."
    nombre_base = os.path.basename(ruta_tex).replace(".tex", "")
    ruta_pdf = f"{directorio}/{nombre_base}.pdf"

    inicio = time.perf_counter()

    try:
        compilacion_ok, salida = _compilar_con_pasadas(ruta_tex, directorio, timeout_seg)

        if not compilacion_ok:
            reparado = _auto_reparar_tex(ruta_tex)
            if reparado:
                compilacion_ok, salida = _compilar_con_pasadas(ruta_tex, directorio, timeout_seg)

            if not compilacion_ok:
                raise RuntimeError(
                    "Error en compilación de pdflatex tras intento de auto-reparación."
                    f"\n--- salida ---\n{salida[-6000:]}"
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
