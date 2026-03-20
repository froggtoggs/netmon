# NetMon

A lightweight, self-hosted network monitoring dashboard. Tracks latency and uptime for hosts inside and outside your network, displayed on a clean dark-theme dashboard suitable for a wall screen.

![Dashboard showing status cards for multiple hosts with latency graphs and uptime indicators]

## Features

- **ICMP ping** and **HTTP/HTTPS** checks
- Live latency, avg/min/max stats, uptime percentage
- Sparkline history chart and per-check status bar on every card
- Add and remove hosts from the UI without restarting
- Checks all hosts in parallel every 30 seconds
- 24 hours of check history stored in SQLite
- Single Docker container, no external database required

## Quick Start

```bash
git clone <your-repo-url>
cd netmon
docker compose up -d
```

Open **http://localhost:8080**.

## Configuration

### Adding hosts via config file

Edit `config/hosts.yml` before starting, or to bulk-add hosts:

```yaml
hosts:
  - name: "Router"
    host: "192.168.1.1"
    type: "ping"

  - name: "Production API"
    host: "https://api.example.com/health"
    type: "http"
```

| Field  | Values             | Description                        |
|--------|--------------------|------------------------------------|
| `name` | any string         | Display name shown on the card     |
| `host` | IP, hostname, URL  | Target to monitor                  |
| `type` | `ping` \| `http`   | Check method                       |

Restart the container after editing the file:

```bash
docker compose restart
```

### Adding hosts via the dashboard

Click **+ Add Host** in the top-right corner. The first check runs within a few seconds.

### Environment variables

| Variable         | Default | Description                          |
|------------------|---------|--------------------------------------|
| `CHECK_INTERVAL` | `30`    | Seconds between checks               |

Set in `docker-compose.yml` under `environment`.

## Changing the port

Edit `docker-compose.yml`:

```yaml
ports:
  - "9000:8080"  # expose on port 9000 instead
```

## Data persistence

Check history is stored in a named Docker volume (`netmon_data`). It survives container restarts and updates. To reset all data:

```bash
docker compose down -v
```

## Updating

```bash
docker compose pull   # if using a registry
docker compose build  # or rebuild from source
docker compose up -d
```

## Project structure

```
netmon/
├── docker-compose.yml
├── config/
│   └── hosts.yml          # Host configuration
└── app/
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py             # FastAPI app and routes
    ├── database.py         # SQLite operations
    ├── monitor.py          # Ping and HTTP check logic
    └── static/
        └── index.html      # Dashboard (single-page app)
```

## Requirements

- Docker and Docker Compose
- The container needs `CAP_NET_RAW` for ICMP ping (granted automatically by `docker-compose.yml`)
