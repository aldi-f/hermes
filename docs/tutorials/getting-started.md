# Getting Started Guide

This guide covers installation and basic setup options for Hermes.

## Installation

### Python Installation

Install Hermes using pip:

```bash
pip install -e .
```

**Requirements:**
- Python 3.11 or higher

### Docker Installation

Build a Docker image:

```bash
docker build -t hermes:latest .
```

Run Hermes with Docker:

```bash
docker run -p 8080:8080 -p 9090:9090 \
  -v $(pwd)/config.yaml:/config/config.yaml \
  hermes:latest
```

## Basic Configuration

Create a `config.yaml` file in the Hermes directory:

```yaml
settings:
  fingerprint_strategy: "auto"
  deduplication_ttl: 300

destinations:
  - name: stdout-alerts
    type: stdout
    template:
      content: |
        Alert: {{ status }}
        Namespace: {{ labels.namespace }}
        Summary: {{ annotations.summary }}

groups:
  - name: all-alerts
    destinations: [stdout-alerts]
    match:
      - type: always_match
```

**Configuration Options:**

**Settings:**
- `fingerprint_strategy`: How to compute alert identity (`auto`, `alertmanager`, `custom`)
- `deduplication_ttl`: Seconds to keep alert state for deduplication (default: 300)
- `metrics_port`: Prometheus metrics port (default: 9090)

**Destination Types:**
- `stdout`: Print to terminal (useful for testing)
- `slack`: Send to Slack webhooks
- `discord`: Send to Discord webhooks

**Match Types:**
- `always_match`: Match all alerts
- `label_equals`: Label value equals one of values
- `label_contains`: Label value contains substring
- `label_matches`: Label value matches regex pattern

## Running Hermes

### Running with Python

```bash
python -m src.main
```

**Custom Port:**
```bash
PORT=8081 python -m src.main
```

### Running with Docker

```bash
docker run -p 8080:8080 -v $(pwd)/config.yaml:/config/config.yaml hermes:latest
```

**With Environment Variables:**
```bash
docker run -p 8080:8080 \
  -v $(pwd)/config.yaml:/config/config.yaml \
  -e CONFIG_RELOAD_INTERVAL=10 \
  -e REDIS_URL=redis://redis:6379/0 \
  hermes:latest
```

## Sending Test Alerts

### Using curl

Send a test alert to verify Hermes is working:

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "HighMemory",
        "namespace": "production"
      },
      "annotations": {
        "summary": "Memory usage at 95%"
      },
      "startsAt": "2024-01-01T00:00:00Z"
    }]
  }'
```

**Test Alert Examples:**

**Firing alert:**
```json
{
  "alerts": [{
    "status": "firing",
    "labels": {"alertname": "TestAlert", "namespace": "production"},
    "annotations": {"summary": "Test firing alert"},
    "startsAt": "2024-01-01T00:00:00Z"
  }]
}
```

**Resolved alert:**
```json
{
  "alerts": [{
    "status": "resolved",
    "labels": {"alertname": "TestAlert", "namespace": "production"},
    "annotations": {"summary": "Test resolved alert"},
    "startsAt": "2024-01-01T00:00:00Z",
    "endsAt": "2024-01-01T01:00:00Z"
  }]
}
```

## Health Check

Verify Hermes is running:

```bash
curl http://localhost:8080/health
```

**Expected response:**
```json
{
  "status": "ok",
  "config_loaded": true,
  "redis": "not_configured",
  "queue_size": 0
}
```

**Health Endpoints:**
- `/health` - Basic health status
- `/ready` - Readiness check
- `/metrics` - Prometheus metrics
- `/destinations` - List configured destinations
- `/state` - State information

## Environment Variables

Configure Hermes using environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_PATH` | `config.yaml` | Path to config file |
| `PORT` | `8080` | HTTP server port |
| `ENABLE_RELOAD_CHECK` | `true` | Enable periodic config reload checks |
| `CONFIG_RELOAD_INTERVAL` | `30` | Config reload check interval in seconds |
| `REDIS_URL` | `None` | Redis connection URL (optional) |

**Using Environment Variables in Config:**

```yaml
destinations:
  - name: slack-alerts
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
```

Set the variable:
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

## Configuration Reload

Hermes automatically reloads configuration when the config file changes:

```bash
# Set check interval to 10 seconds
CONFIG_RELOAD_INTERVAL=10 python -m src.main
```

**Reload behavior:**
1. Computes SHA-256 checksum of config file
2. Compares with previous checksum
3. If different: reloads configuration
4. Updates cached checksum

## Next Steps

- [Alert Routing Guide](basic-alert-routing.md) - Configure routing to Slack/Discord
- [Routing and Groups](../concepts/routing-and-groups.md) - Understand OR-based routing
- [Examples](../examples/) - Complete configuration examples
- [Alertmanager Integration](../alertmanager-integration.md) - Configure Alertmanager to send to Hermes
