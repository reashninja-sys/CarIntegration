#!/data/data/com.termux/files/usr/bin/bash
# One-time setup. Run once after installing Termux from F-Droid.

set -e

echo "=== Updating Termux packages ==="
pkg update -y && pkg upgrade -y

echo "=== Installing Python ==="
pkg install python -y

echo "=== Installing Python dependencies ==="
pip install flask python-dotenv seatconnect aiohttp

echo ""
echo "=== Done! Next steps ==="
echo ""
echo "1. Create your config:"
echo "   cp .env.example .env && nano .env"
echo ""
echo "2. Generate an API key and paste it into .env as API_KEY:"
echo "   python -c \"import secrets; print(secrets.token_urlsafe(24))\""
echo ""
echo "3. Test Cupra auth first:"
echo "   python test_cupra.py"
echo ""
echo "4. Start the server:"
echo "   bash start.sh"
echo ""
echo "5. (Optional) Auto-start on boot:"
echo "   Install Termux:Boot from F-Droid, open it once, then:"
echo "   bash install-boot.sh"
