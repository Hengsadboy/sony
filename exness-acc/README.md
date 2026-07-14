# Exness MT5 Python Service Layer API

A dedicated FastAPI service designed to run on a separate Ubuntu VPS. It exposes secure REST endpoints for checking account validity (Login) and checking balances (Check Balance) using MetaTrader 5 (MT5). The service implements dynamic account switching, encryption of stored trading passwords, and thread-safe operations.

## Features
- **API Key Security**: Endpoints are secured with an API key header `X-API-Key`.
- **Credential Encryption**: MT5 passwords stored in SQLite are encrypted using AES-256 (Fernet).
- **Dynamic Connection Switching**: Uses a central `asyncio.Lock` to serialise terminal access and switches connections using `mt5.login(...)` dynamically.
- **Pluggable Mock Mode**: Local test run without MT5 terminal setup by changing `MT5_MOCK_MODE=True`.
- **Systemd Service & Wine Integration Guide**: Optimized instructions to run headlessly on Ubuntu.

---

## Project Structure
```
app/
├── config.py         # Loads and validates settings from .env file
├── database.py       # Manages SQLite connection and saves credentials
├── security.py       # Handles encryption and decryption of passwords
├── main.py           # FastAPI entrypoint, health endpoint
├── routers/
│   └── accounts.py   # Register, Login, and Check Balance API endpoints
└── services/
    └── mt5_service.py # Core MT5 connector & dynamic switching controller
```

---

## Configuration (`.env`)
Create a `.env` file in the root directory based on `.env.example`:

```ini
API_KEY=your_super_secure_api_key_between_vps
ENCRYPTION_KEY=32_byte_base64_key_here
DATABASE_URL=sqlite:///./exness_service.db
MT5_MOCK_MODE=False
MT5_TERMINAL_PATH=/home/ubuntu/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe
```

> **Warning**: Ensure you generate a secure `ENCRYPTION_KEY` using:
> `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

---

## Ubuntu VPS Deployment & Wine Setup Guide

MetaTrader 5 requires a Windows subsystem. To run it on an Ubuntu VPS, we run it headlessly inside Wine.

### Step 1: Install Wine & Xvfb (Virtual Framebuffer)
Run the following commands on your Ubuntu VPS:
```bash
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y wine64 wine32 xvfb python3-pip
```

### Step 2: Install MetaTrader 5 under Wine
Download the official Exness MT5 setup executable or generic MT5:
```bash
wget https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
```

Initialize Wine prefix and install MT5:
```bash
xvfb-run wine mt5setup.exe /contents
```
This runs the installer inside a virtual display. Follow the installation prompt (which uses Wine's interface window or default settings).

### Step 3: Install dependencies in the Wine Python Environment
Since MT5 Python package binds directly to the terminal, it needs to run under the Wine Python environment, or you can run Python natively on Linux and connect using `mt5linux` (a bridge utilizing RPyC).

#### Option A: Running the API Service under Wine Python
1. Install Python for Windows inside your Wine prefix:
   ```bash
   wget https://www.python.org/ftp/python/3.10.8/python-3.10.8-amd64.exe
   wine python-3.10.8-amd64.exe /quiet InstallAllUsers=1 PrependPath=1
   ```
2. Install requirements using Wine's pip:
   ```bash
   wine pip install -r requirements.txt MetaTrader5
   ```
3. Run uvicorn inside Wine:
   ```bash
   xvfb-run wine python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

#### Option B: Utilizing RPyC Bridge (mt5linux)
Alternatively, you can run the FastAPI server natively on Ubuntu Python, and run an RPyC server inside Wine.
Follow details on [mt5linux Github](https://github.com/lucas-campagna/mt5linux) to set up the RPyC server.

---

## Firewall Security (UFW)
Only expose the port (e.g. `8000`) to your main VPS IP (the one hosting your Telegram Bot or Website). Do not leave the port open to the public.

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Deny all access to port 8000 by default
sudo ufw deny 8000/tcp

# Allow only the main VPS IP
sudo ufw allow from <MAIN_VPS_IP> to any port 8000 proto tcp

# Enable firewall
sudo ufw enable
```
