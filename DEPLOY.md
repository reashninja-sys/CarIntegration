# Cupra Battery Widget — Deployment Guide

## Architecture

```
Garmin vivoactive 4
      │  makeWebRequest (proxied through Garmin Connect Mobile)
      ▼
Android phone (Termux)
  Flask server on port 5000
      │  Python aiohttp
      ▼
Cupra/VW Group cloud APIs
  identity.vwgroup.io   ← OAuth2 login
  tokenrefreshservice.apps.emea.vwapps.io  ← token exchange
  ola.prod.code.seat.cloud.vwgroup.com     ← battery data
```

## ⚠️  Why this MUST run on your phone (Termux)

The Cupra cloud API's token exchange service (`tokenrefreshservice.apps.emea.vwapps.io`)
returns **503 Service Unavailable** for requests coming from desktop/server IPs.
It only accepts connections from mobile app traffic — i.e., the same network context
as the MyCupra app. Running on your Android phone via Termux puts us in exactly that
context.

## Step 1 — Install Termux

Install **Termux** from [F-Droid](https://f-droid.org/en/packages/com.termux/)
(NOT from Google Play — the Play version is outdated and broken).

Optionally also install **Termux:Boot** from F-Droid if you want auto-start on reboot.

## Step 2 — Copy the files to your phone

From your PC, push the `backend/` folder to your phone. Options:

**Option A — USB (ADB):**
```
adb push C:\Users\daveb\CarIntegration\backend /sdcard/cupra-battery
```
Then in Termux:
```bash
cp -r /sdcard/cupra-battery ~/cupra-battery
cd ~/cupra-battery
```

**Option B — Syncthing / Google Drive / USB file transfer:**
Copy the `backend/` folder to your phone, then in Termux:
```bash
# If you put it in /sdcard/cupra-battery:
cp -r /sdcard/cupra-battery ~/cupra-battery
cd ~/cupra-battery
```

**Option C — Git (if you push the repo to GitHub):**
```bash
pkg install git -y
git clone https://github.com/YOUR_USERNAME/CarIntegration ~/cupra-battery
cd ~/cupra-battery/backend
```

## Step 3 — Run setup

In Termux:
```bash
cd ~/cupra-battery   # or wherever you copied the files

# Make scripts executable
chmod +x setup-termux.sh start.sh install-boot.sh

# Run setup (installs Python packages)
bash setup-termux.sh
```

## Step 4 — Configure credentials

```bash
cp .env.example .env
nano .env
```

Fill in:
```
CUPRA_USERNAME=your.email@example.com
CUPRA_PASSWORD=your_cupra_password
CUPRA_VIN=VSSZZZ...        ← from MyCupra app / door jamb / V5C logbook
API_KEY=GENERATE_BELOW
```

Generate a random API key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Paste the output into `.env` as `API_KEY=...`

## Step 5 — Test auth first

```bash
python test_cupra.py
```

**Expected output on success:**
```
✓ Loaded .env from ...
→ Username : your.email@example.com
→ VIN      : VSSZZZ...
→ Password : **************

⏳  Authenticating… (this takes 10-30 s)

==================================================
✓ SUCCESS
==================================================
  Battery : 78 %
  Range   : 276 km
  Charging: False
==================================================
```

If you see `✗ AUTH ERROR: Wrong username or password` — check your `.env`.

If you see `✗ API ERROR: OLA API returned 403 Forbidden` — you're NOT running this
on your phone yet. The tokenrefreshservice is blocked from desktop IPs.

## Step 6 — Start the server

```bash
bash start.sh
```

The server prints your phone's LAN IP and port when it starts:
```
====================================================
  Cupra battery server running

  ➜  Garmin Connect widget settings — Server URL:
     http://192.168.1.42:5000

  ➜  Test from phone browser (no key needed):
     http://192.168.1.42:5000/ping
====================================================
```

Test connectivity from your PC browser: `http://192.168.1.42:5000/ping`

## Step 7 — Auto-start on boot (optional but recommended)

```bash
# Install Termux:Boot from F-Droid, then open it ONCE (to grant permissions)
bash install-boot.sh
```

The server will now start automatically when your phone reboots.

## Step 8 — Configure the Garmin widget

In **Garmin Connect Mobile** → My Device → Widget Settings:

| Setting | Value |
|---------|-------|
| Server URL | `http://192.168.1.42:5000` (use the IP from Step 6) |
| Api Key | The value of `API_KEY` from your `.env` |

> **Note:** The Garmin widget communicates via Garmin Connect Mobile on your phone,
> which then makes HTTP calls to the Flask server. Phone and watch must be paired
> and within Bluetooth range.

## Step 9 — Sideload the widget

The widget `.prg` file needs to be built from the `widget/` folder using the
[Garmin Connect IQ SDK](https://developer.garmin.com/connect-iq/sdk/).

1. Install Connect IQ SDK on your PC
2. Open the `widget/` folder in VS Code with the Monkey C extension
3. Build → `monkeyc -d vivoactive4 -o cupra_battery.prg -m widget/monkey.jungle`
4. Sideload via: Connect IQ SDK → Build & Run (or Transfer to Device)

Or if you just want to test, add it via Garmin Express / Connect IQ Store
(requires uploading to the store — for private use, use the SDK simulator first).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `503` from tokenrefreshservice | You're running on PC. Move to Termux on phone. |
| `403` from OLA API | Token exchange failed — see row above. |
| `AUTH ERROR: Wrong username/password` | Check `.env` credentials |
| `No login form on VW Group page` | VW Group changed their page — open a GitHub issue |
| Widget shows `--` | Check phone's Garmin Connect Mobile is running and paired |
| Widget shows `ERR` | Server is unreachable — check phone IP and port 5000 is open |
| Server port busy | `lsof -i:5000` / change `PORT=5001` in `.env` |

## Keeping the server running (advanced)

Instead of `bash start.sh` in a Termux window, you can run in background:
```bash
nohup python server.py > server.log 2>&1 &
echo $! > server.pid
```

Stop it with:
```bash
kill $(cat server.pid)
```

Or just use the Termux:Boot approach from Step 7 — it auto-starts on reboot
and `server.log` captures all output.
