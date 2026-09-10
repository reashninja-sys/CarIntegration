#!/data/data/com.termux/files/usr/bin/bash
# Auto-start via Termux:Boot (install from F-Droid and open once first).

BOOT_DIR="$HOME/.termux/boot"
HERE="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$BOOT_DIR"

cat > "$BOOT_DIR/cupra-battery.sh" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd "$HERE"
python server.py >> "$HERE/server.log" 2>&1 &
EOF

chmod +x "$BOOT_DIR/cupra-battery.sh"
echo "Boot script installed. Server will start automatically after reboot."
echo "Logs: $HERE/server.log"
