# LaTeX Article Generator (Ollama + Streamlit)

Genera artículos científicos en PDF (IEEE o APA) desde texto plano, usando IA local con Ollama.

## 1) Requisitos del sistema (Linux)

### Python y venv
```bash
python3 --version
python3 -m venv --help
```

### Compilador LaTeX (`pdflatex`)
```bash
sudo apt-get update
sudo apt-get install -y texlive-full
```

### Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version
```

Descarga de modelo sugerido:
```bash
ollama pull llama3.2
```

## 2) Crear y activar entorno virtual

Desde la raíz del proyecto:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3) Instalar dependencias Python

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 4) Configurar variables de entorno

```bash
cp .env.example .env
```

Opcional: editar `.env` para cambiar el modelo.

Configuración recomendada para estabilidad:
- `OLLAMA_MODEL=llama3.2`
- `OLLAMA_FALLBACK_MODEL=llama3.2`
- `OLLAMA_NUM_THREAD=6` (ajústalo a núcleos físicos - 2 en tu servidor)
- `OLLAMA_TIMEOUT=300`
- `OLLAMA_RETRIES=3`

## 5) Levantar servicios

### Iniciar Ollama
```bash
ollama serve
```

En otra terminal (con el `venv` activo):
```bash
streamlit run app.py
```

La app queda en:
- `http://localhost:8501`

## 6) Open WebUI (opcional, recomendado)

Para ejecutar Open WebUI como en el plan original, necesitas Docker instalado.

### Instalar Docker (requiere sudo)
```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

Luego cierra sesión y vuelve a entrar para aplicar el grupo `docker`.

### Levantar Open WebUI
```bash
docker run -d -p 3000:8080 \
	--add-host=host.docker.internal:host-gateway \
	-v open-webui:/app/backend/data \
	--name open-webui \
	ghcr.io/open-webui/open-webui:main
```

Accede en:
- `http://localhost:3000`

## 7) Flujo de uso

1. Elige norma IEEE o APA.
2. Pega texto en las secciones.
3. Presiona **Generar PDF** (la generación se ejecuta en modo seccional para mayor estabilidad).
4. Descarga `.tex` y `.pdf`.

## 8) Estructura

```text
.
├── app.py
├── core/
│   ├── ollama_client.py
│   ├── latex_builder.py
│   └── pdf_compiler.py
├── templates/
├── prompts/
├── output/
├── requirements.txt
└── .env.example
```
