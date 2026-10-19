#!/bin/bash
# One-line installer for the RE4 Mac save editor:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/gdragotto/re4-mac-save-editor/main/install.sh)"
# Installs into ~/Library/Application Support/RE4 Save Editor, adds a launcher to the Desktop, then starts it.
set -e

APP="$HOME/Library/Application Support/RE4 Save Editor"
TARBALL="https://github.com/gdragotto/re4-mac-save-editor/archive/refs/heads/main.tar.gz"
LAUNCHER="$HOME/Desktop/RE4 Save Editor.command"

echo "Installing the RE4 Mac save editor..."

# Python comes with Apple's free developer tools; macOS installs them with one click.
if ! xcode-select -p >/dev/null 2>&1; then
  echo
  echo "Your Mac needs Apple's free developer tools first (they include Python)."
  echo "A window will pop up: click Install and wait for it to finish (a few minutes)."
  echo "Then paste the same command again."
  xcode-select --install >/dev/null 2>&1 || true
  exit 1
fi

TMP="$(mktemp -d)"
curl -fsSL "$TARBALL" | tar -xz -C "$TMP" --strip-components 1
rm -rf "$APP"
mkdir -p "$(dirname "$APP")"
mv "$TMP" "$APP"

cat > "$LAUNCHER" <<'EOF'
#!/bin/bash
cd "$HOME/Library/Application Support/RE4 Save Editor" && exec /usr/bin/python3 -m re4save
EOF
chmod +x "$LAUNCHER"

echo "Installed. Next time, just double-click \"RE4 Save Editor\" on your Desktop."
echo
cd "$APP"
exec /usr/bin/python3 -m re4save
