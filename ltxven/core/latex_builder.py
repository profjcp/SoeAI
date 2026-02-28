from pathlib import Path


def ensamblar_documento(secciones_latex: dict[str, str], norma: str) -> str:
    """Inserta las secciones generadas en la plantilla base."""
    template_path = Path("templates") / f"{norma.lower()}_template.tex"

    if not template_path.exists():
        raise FileNotFoundError(f"No se encontró la plantilla: {template_path}")

    template = template_path.read_text(encoding="utf-8")

    for seccion, contenido_latex in secciones_latex.items():
        marcador = f"%%{seccion.upper()}%%"
        template = template.replace(marcador, contenido_latex)

    # Limpia marcadores que no se hayan usado
    for marcador in [
        "%%TITLE%%",
        "%%AUTHORS%%",
        "%%ABSTRACT%%",
        "%%KEYWORDS%%",
        "%%INTRODUCTION%%",
        "%%RELATED_WORK%%",
        "%%METHODOLOGY%%",
        "%%RESULTS%%",
        "%%DISCUSSION%%",
        "%%CONCLUSION%%",
        "%%REFERENCES%%",
    ]:
        template = template.replace(marcador, "")

    return template


def guardar_tex(contenido: str, nombre: str = "articulo") -> str:
    """Guarda el .tex en la carpeta output/."""
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)

    ruta = output_dir / f"{nombre}.tex"
    ruta.write_text(contenido, encoding="utf-8")
    return str(ruta)
