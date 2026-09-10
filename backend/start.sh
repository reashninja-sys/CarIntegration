#!/data/data/com.termux/files/usr/bin/bash
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "ERROR: .env not found. Copy .env.example and fill it in first."
    exit 1
fi

echo "Starting Cupra battery server …"
python server.py
