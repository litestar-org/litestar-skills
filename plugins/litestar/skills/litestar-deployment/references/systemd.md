# systemd Native Deployment

Deploy Litestar directly on a Linux host using systemd service units. Suitable for bare-metal servers, VMs, and environments where containers are not used.

## Service unit file

```ini
# /etc/systemd/system/litestar.service
[Unit]
Description=Litestar ASGI Application
After=network.target postgresql.service redis.service
Wants=postgresql.service redis.service

[Service]
Type=exec
User=litestar
Group=litestar
WorkingDirectory=/opt/litestar/app

# Environment
Environment=LITESTAR_APP=app.server.asgi:create_app
Environment=LITESTAR_HOST=0.0.0.0
Environment=LITESTAR_PORT=8000
EnvironmentFile=/opt/litestar/.env

# Start command
ExecStart=/opt/litestar/app/.venv/bin/litestar run --host 0.0.0.0 --port 8000

# Graceful shutdown
KillSignal=SIGINT
TimeoutStopSec=30

# Restart policy
Restart=on-failure
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/litestar/app/logs
PrivateTmp=true
CapabilityBoundingSet=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
```

## SAQ worker unit

```ini
# /etc/systemd/system/litestar-worker.service
[Unit]
Description=Litestar SAQ Worker
After=network.target postgresql.service redis.service
Wants=redis.service

[Service]
Type=exec
User=litestar
Group=litestar
WorkingDirectory=/opt/litestar/app
EnvironmentFile=/opt/litestar/.env
ExecStart=/opt/litestar/app/.venv/bin/litestar workers run
KillSignal=SIGINT
TimeoutStopSec=120
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

## Setup commands

```bash
# Create system user
sudo useradd --system --shell /usr/sbin/nologin --home-dir /opt/litestar litestar

# Install application
sudo mkdir -p /opt/litestar/app
cd /opt/litestar/app
uv venv
uv pip install /path/to/app-1.0.0-py3-none-any.whl

# Create env file (restrict permissions)
sudo touch /opt/litestar/.env
sudo chmod 600 /opt/litestar/.env
sudo chown litestar:litestar /opt/litestar/.env

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable litestar.service litestar-worker.service
sudo systemctl start litestar.service litestar-worker.service

# Check status
sudo systemctl status litestar.service
sudo journalctl -u litestar.service -f
```

## Key decisions

| Decision | Rationale |
| --- | --- |
| `KillSignal=SIGINT` | Granian handles SIGINT for graceful shutdown. Matches Dockerfile `STOPSIGNAL`. |
| `TimeoutStopSec=30` (web) / `120` (worker) | Web: fast shutdown. Worker: allow in-flight tasks to complete. |
| `ProtectSystem=strict` | Read-only filesystem except `ReadWritePaths`. Defense in depth. |
| `EnvironmentFile` | Secrets stay in a 600-permission file, not in the unit. |
| Separate units for web + worker | Independent restart, logging, and resource control. |

## Reverse proxy

Pair with nginx or Caddy as a reverse proxy for TLS termination:

```nginx
# /etc/nginx/sites-available/litestar
upstream litestar {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl http2;
    server_name app.example.com;

    ssl_certificate /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;

    location / {
        proxy_pass http://litestar;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
