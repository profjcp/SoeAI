#!/usr/bin/env bash
# =============================================================================
# install.sh — Instalador completo para ltxven
# Ubuntu 24.04 LTS
# Uso: bash install.sh
# =============================================================================

set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_USER="${SUDO_USER:-$(whoami)}"
SERVICE_NAME="ltxven"
PORT=8501

# ─── Colores ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ─── Verificar root ──────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    error "Ejecuta el instalador con sudo: sudo bash install.sh"
fi

echo ""
echo "======================================================="
echo "  ltxven — Instalador"
echo "  Directorio: $APP_DIR"
echo "  Usuario:    $APP_USER"
echo "  Puerto:     $PORT"
echo "======================================================="
echo ""

# ─── 1. Dependencias del sistema ─────────────────────────────────────────────
info "Actualizando paquetes del sistema..."
apt-get update -qq

info "Instalando dependencias del sistema..."
apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    pipx \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    curl

success "Dependencias del sistema instaladas."

# ─── 2. Ollama (binario) ─────────────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    success "Ollama binario ya instalado: $(ollama --version)"
else
    info "Instalando Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    success "Ollama instalado."
fi

# Habilitar y arrancar el servicio ollama
info "Habilitando servicio ollama..."
systemctl enable ollama --quiet
systemctl start ollama
sleep 2
success "Servicio ollama activo."

# ─── 3. Entorno virtual Python para la app ───────────────────────────────────
VENV_DIR="$APP_DIR/.venv"

if [[ -d "$VENV_DIR" ]]; then
    warn "Entorno virtual ya existe en $VENV_DIR — se usará el existente."
else
    info "Creando entorno virtual Python en $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    success "Entorno virtual creado."
fi

info "Instalando dependencias Python desde requirements.txt..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
success "Dependencias Python instaladas."

# ─── 4. Archivo .env (si no existe) ─────────────────────────────────────────
ENV_FILE="$APP_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    info "Creando archivo .env base..."
    cat > "$ENV_FILE" <<EOF
# Configuración de ltxven
OLLAMA_HOST=http://localhost:11434
DEFAULT_MODEL=llama3.2
EOF
    chown "${APP_USER}:${APP_USER}" "$ENV_FILE"
    success "Archivo .env creado en $ENV_FILE"
else
    success "Archivo .env ya existe."
fi

# ─── 5. Permisos del directorio output ───────────────────────────────────────
info "Ajustando permisos en output/..."
mkdir -p "$APP_DIR/output/history"
chown -R "${APP_USER}:${APP_USER}" "$APP_DIR/output"
success "Permisos ajustados."

# ─── 6. Script de arranque ───────────────────────────────────────────────────
START_SCRIPT="$APP_DIR/start.sh"
info "Creando script de arranque $START_SCRIPT..."
cat > "$START_SCRIPT" <<EOF
#!/usr/bin/env bash
# Arrancar ltxven
cd "$(realpath "$APP_DIR")"
exec .venv/bin/streamlit run app.py \
    --server.port $PORT \
    --server.address 0.0.0.0 \
    --server.headless true
EOF
chmod +x "$START_SCRIPT"
chown "${APP_USER}:${APP_USER}" "$START_SCRIPT"
success "Script de arranque creado."

# ─── 7. Servicio systemd ─────────────────────────────────────────────────────
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
info "Creando servicio systemd ${SERVICE_NAME}.service..."

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=ltxven — Generador de LaTeX con IA
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/streamlit run app.py --server.port ${PORT} --server.address 0.0.0.0 --server.headless true
Restart=on-failure
RestartSec=5
Environment="PATH=${APP_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=-${APP_DIR}/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" --quiet
success "Servicio ${SERVICE_NAME} habilitado para arranque automático."

# ─── 8. Iniciar el servicio ───────────────────────────────────────────────────
info "Iniciando servicio ${SERVICE_NAME}..."
systemctl restart "${SERVICE_NAME}"
sleep 3

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    success "Servicio ${SERVICE_NAME} corriendo correctamente."
else
    warn "El servicio no arrancó. Revisa con: sudo journalctl -u ${SERVICE_NAME} -n 30"
fi

# ─── Resumen ─────────────────────────────────────────────────────────────────
echo ""
echo "======================================================="
echo -e "${GREEN}  Instalación completada${NC}"
echo "======================================================="
echo "  App URL:      http://$(hostname -I | awk '{print $1}'):${PORT}"
echo "  Local:        http://localhost:${PORT}"
echo ""
echo "  Comandos útiles:"
echo "    sudo systemctl status ${SERVICE_NAME}"
echo "    sudo systemctl restart ${SERVICE_NAME}"
echo "    sudo journalctl -u ${SERVICE_NAME} -f"
echo "======================================================="
echo ""
