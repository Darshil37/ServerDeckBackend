# ServerDeck Agent

The ServerDeck Agent is a lightweight Python service you install on any Linux server. It connects to your ServerDeck dashboard and lets you manage that server — services, deployments, logs, SSL, firewall — without ever opening a terminal.

This repository contains only the agent. The ServerDeck backend and frontend are separate. You self-host the backend or use the hosted version at [serverdeck.online](https://serverdeck.online).

---

## How it works

```
┌─────────────────────────────────┐
│        ServerDeck Dashboard     │
│   (your browser + your backend) │
└──────────────┬──────────────────┘
               │ WebSocket (outbound from agent)
    ┌──────────┴──────────┐
    ▼                     ▼
┌──────────┐        ┌──────────┐
│  Agent   │        │  Agent   │
│ Server A │        │ Server B │
└──────────┘        └──────────┘
```

1. You add a server in the dashboard and get a one-line install command
2. You run that command on your Linux server
3. The agent installs itself as a systemd service and connects outbound to your backend
4. From that point you manage the server entirely from the dashboard

**The agent never opens any inbound ports.** All communication is outbound WebSocket from the agent to your backend. No firewall rules need to change on your server.

---

## What the agent can do

Once installed, the agent accepts commands from your backend to:

- **Monitor** — report CPU, RAM, disk usage, and uptime in real time
- **Nginx** — list sites, create/delete virtual hosts, enable/disable sites, edit configs, test config validity before applying
- **Systemd** — list, start, stop, restart, enable, disable services; create new unit files
- **PM2** — list, start, stop, restart, delete apps; create new app configs
- **SSL** — list certificates, issue new certs via Certbot, renew existing certs
- **Firewall** — list UFW rules, allow/deny ports, delete rules
- **Files** — list, read, write, delete files; create directories; upload and download
- **Logs** — fetch recent log lines or stream live logs from journald, nginx, or PM2
- **Processes** — list running processes, kill by PID
- **Terminal** — open a full interactive PTY session in your browser
- **Scripts** — run arbitrary shell scripts

---

## Security

This is the part that matters most — you are installing software on your production server, and you should know exactly what it does.

### What the agent does
- Opens a single outbound WebSocket connection to your ServerDeck backend
- Authenticates using a unique token generated when you add the server in the dashboard
- Listens for commands from your backend only
- Executes commands and sends results back over the same connection
- Reports telemetry (CPU, RAM, disk, uptime) on a regular interval

### What the agent does NOT do
- Does not open any inbound ports or listen for outside connections
- Does not send any data to Anthropic, third parties, or anyone other than your own backend
- Does not have access to your dashboard credentials or JWT secrets
- Does not execute anything that is not in the action allowlist (unknown commands are rejected)
- Does not persist any command history itself (that lives in your backend's audit log)

### Token security
- Your agent token is generated with `secrets.token_urlsafe(32)` — 256 bits of entropy
- The token is stored in `/etc/serverdeck/agent.json` with permissions `chmod 600` (root-readable only)
- The token is sent as a `Bearer` header on the WebSocket connection
- If a token is compromised, you can revoke and regenerate it from the dashboard — the agent will reconnect with the new token on reinstall

### Command allowlist
The agent maintains an explicit allowlist of every action it will accept. Any command not in that list is rejected outright with an error — the agent does not evaluate or execute unknown command names under any circumstances.

You can inspect the full allowlist in `serverdeck_agent/main.py` in this repository. Note that the installer compiles the agent to bytecode and removes all `.py` source from the server, so the installed machine carries only compiled `.pyc` files — audit the source here in the repo, not on the target host.

### Verifying the install script
Before running the install command, you can verify what it does:

```bash
# Download the install script without running it
curl -o install.sh https://serverdeck.online/agent/install.sh

# Read it
cat install.sh

# Check the SHA256 of the agent archive before installing
curl -s https://serverdeck.online/agent/checksum.txt
```

The install script:
1. Downloads the agent tar.gz and verifies its checksum
2. Extracts it to `/opt/serverdeck/`
3. Creates a Python virtual environment and installs dependencies
4. Compiles the agent to bytecode and deletes all `.py` source files
5. Writes your agent token to `/etc/serverdeck/agent.json`
6. Creates and enables a systemd service `serverdeck-agent`

Nothing else.

### Verifying what the agent is doing after install
```bash
# Check what network connections the agent has open
ss -tnp | grep serverdeck

# View the agent's live logs
journalctl -u serverdeck-agent -f

# See the agent config (token is in here)
cat /etc/serverdeck/agent.json

# Check what the systemd service looks like
systemctl cat serverdeck-agent
```

---

## Installation

You get your install command from the ServerDeck dashboard when you add a server. It looks like this:

```bash
curl -fsSL https://serverdeck.online/agent/install.sh | bash -s -- --token YOUR_TOKEN --backend wss://serverdeck.online
```

**Requirements:**
- Ubuntu 20.04+ or Debian 11+ (other distros may work but are untested)
- Python 3.10 or higher
- systemd
- Root or sudo access for the install

---

## Uninstalling

From the dashboard: go to the server, click Delete. If the server is online, the dashboard sends a self-uninstall command to the agent which removes everything cleanly.

Manually:
```bash
systemctl stop serverdeck-agent
systemctl disable serverdeck-agent
rm -rf /opt/serverdeck/
rm -rf /etc/serverdeck/
rm /etc/systemd/system/serverdeck-agent.service
systemctl daemon-reload
```

---

## Files installed on your server

| Path | What it is |
|---|---|
| `/opt/serverdeck/` | Compiled agent bytecode (`.pyc`, no source) and Python virtual environment |
| `/etc/serverdeck/agent.json` | Config file: backend URL and agent token (chmod 600) |
| `/etc/systemd/system/serverdeck-agent.service` | Systemd unit file |
| `/var/log/` | Logs go through journald, not a separate file |

That is everything. No cron jobs, no additional services, no other files.

---

## Running from source

If you want to run the agent directly instead of using the install script:

```bash
git clone https://github.com/ashvn24/serverdeck-agent
cd serverdeck-agent

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create config
mkdir -p /etc/serverdeck
echo '{"backend_url": "wss://your-backend.com", "agent_token": "your-token"}' > /etc/serverdeck/agent.json

# Run
python -m serverdeck_agent.main
```

---

## Contributing

Found a security issue? Please do not open a public issue. Email **ashwinvk77@gmail.com** directly.

Found a bug or want to suggest something? Open an issue or pull request. The agent is open source specifically so you can read it, audit it, and improve it.

---

## License

MIT — do whatever you want with it.