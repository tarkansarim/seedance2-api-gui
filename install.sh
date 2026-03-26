#!/bin/bash
set -e
cd "$(dirname "$0")"
APP_DIR="$(pwd)"

echo "=== Seedance 2 API GUI - Installer ==="

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found. Install Python 3.10+ first."
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Found Python $PY_VER"

# Create venv
if [ ! -d venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Linux: check for ffmpeg (needed for thumbnail extraction)
if [[ "$(uname)" == "Linux" ]]; then
    if ! command -v ffmpeg &>/dev/null; then
        echo ""
        echo "Warning: ffmpeg not found. Install it for video thumbnail previews:"
        echo "  sudo apt install ffmpeg"
    fi
fi

# Create output dir
mkdir -p output

# Create .env if missing
if [ ! -f .env ]; then
    echo "MUAPI_API_KEY=your_key_here" > .env
    echo ""
    echo "Created .env file. Edit it with your MuAPI key, or set it in the app's Settings."
fi

# Create desktop launcher (Linux)
if [[ "$(uname)" == "Linux" ]]; then
    DESKTOP_DIR="$HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"
    ICON_PATH="$APP_DIR/icon-256.png"
    if [ ! -f "$ICON_PATH" ]; then
        ICON_PATH="$APP_DIR/icon.png"
    fi
    cat > "$DESKTOP_DIR/seedance2.desktop" << DEOF
[Desktop Entry]
Name=Seedance 2.0
Comment=Seedance 2.0 Video Generation GUI
Exec=bash -c 'cd $APP_DIR && source venv/bin/activate && python seedance_ui.py'
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=AudioVideo;Video;Graphics;
StartupNotify=true
DEOF
    chmod +x "$DESKTOP_DIR/seedance2.desktop"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    echo "Desktop launcher created: search 'Seedance' in your app launcher."
fi

# Create app launcher (macOS)
if [[ "$(uname)" == "Darwin" ]]; then
    APP_BUNDLE="$HOME/Applications/Seedance 2.0.app"
    mkdir -p "$APP_BUNDLE/Contents/MacOS"
    cat > "$APP_BUNDLE/Contents/MacOS/seedance" << MEOF
#!/bin/bash
cd "$APP_DIR"
source venv/bin/activate
python seedance_ui.py
MEOF
    chmod +x "$APP_BUNDLE/Contents/MacOS/seedance"
    cat > "$APP_BUNDLE/Contents/Info.plist" << PEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Seedance 2.0</string>
    <key>CFBundleExecutable</key><string>seedance</string>
    <key>CFBundleIdentifier</key><string>com.seedance.gui</string>
    <key>CFBundleVersion</key><string>1.0</string>
</dict>
</plist>
PEOF
    echo "macOS app created: ~/Applications/Seedance 2.0.app"
fi

echo ""
echo "=== Installation complete ==="
echo "Run with: ./run.sh"
echo "Or:       source venv/bin/activate && python seedance_ui.py"
