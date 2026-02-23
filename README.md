# Hermes - Alertmanager Routing & Distribution System

Hermes is an intermediary alert routing service that solves Alertmanager's limitations with OR matching and many-to-many alert routing.

## Problem

Alertmanager routes alerts using tree-based routing with AND logic. When an alert belongs to multiple routes (many-to-many relationship), you need OR logic, which Alertmanager doesn't support.

## Solution

Hermes receives Alertmanager webhooks, evaluates each alert against configurable groups (OR logic), deduplicates per-group, applies templates, and sends to multiple destinations (Slack, Discord).

## Quick Start

### Install

```bash
pip install -e .
```

### Run

```bash
python -m src.main
```

### Configure

Edit `config.yaml`:

```yaml
settings:
  fingerprint_strategy: "auto"  # auto | alertmanager | custom
  deduplication_ttl: 300

destinations:
  - name: slack-alerts
    type: slack
    webhook_url: "https://hooks.slack.com/services/xxx"
    template:
      content: |
        {"text": "Alert: {{ status }} - {{ group_name }}"}

groups:
  - name: oxygen-team
    destinations: [slack-alerts]
    match:
      - type: label_equals
        label: namespace
        values: [oxygen, dhc]
      - type: label_matches
        label: container
        pattern: "oxygen-.*"
```

### Send Test Alert

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {"namespace": "oxygen", "alertname": "HighMemory"},
      "annotations": {"summary": "Memory usage high"},
      "startsAt": "2024-01-01T00:00:00Z"
    }]
  }'
```

## Configuration

### Settings

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `fingerprint_strategy` | string | `auto` | How to compute alert fingerprint: `auto` (use Alertmanager if available, else compute), `alertmanager` (require Alertmanager fingerprint), `custom` (always compute) |
| `deduplication_ttl` | int | 300 | Time in seconds to keep alert state for deduplication |
| `metrics_port` | int | 9090 | Port for Prometheus metrics |

### Match Types

| Type | Description |
|------|-------------|
| `label_equals` | Label value matches one of values |
| `label_contains` | Label value contains substring |
| `label_matches` | Label value matches regex pattern |
| `label_not_equals` | Label value does not match any value |
| `label_not_contains` | Label value does not contain substring |
| `label_not_matches` | Label value does not match regex |
| `annotation_equals` | Annotation value matches one of values |
| `annotation_contains` | Annotation value contains substring |
| `annotation_matches` | Annotation value matches regex pattern |
| `always_match` | Always match (catch-all) |

### Template Variables

Available in templates:

| Variable | Description |
|----------|-------------|
| `status` | `firing` or `resolved` |
| `labels` | Dict of alert labels |
| `annotations` | Dict of alert annotations |
| `startsAt` | Alert start timestamp |
| `endsAt` | Alert end timestamp (optional) |
| `generatorURL` | Link to Alertmanager/Prometheus |
| `fingerprint` | Alert fingerprint |
| `group_name` | Matching group name |
| `destination_name` | Destination name |

## Docker

```bash
docker build -t hermes:latest .
docker run -p 8080:8080 -p 9090:9090 -v $(pwd)/config.yaml:/config/config.yaml hermes:latest
```

## Kubernetes

```bash
kubectl apply -k k8s/overlays/prod
```

Requires:
- ConfigMap with `config.yaml`
- Secret with webhook URLs (optional, can use inline)

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /webhook` | Receive Alertmanager webhooks |
| `GET /metrics` | Prometheus metrics |
| `GET /health` | Health check |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_PATH` | `config.yaml` | Path to config file |
| `PORT` | `8080` | HTTP server port |
| `ENABLE_WATCH` | `true` | Watch config file for changes |

## Metrics

- `spreader_alerts_received_total` - Total alerts received
- `spreader_alerts_matched_total{group}` - Alerts matched to groups
- `spreader_alerts_sent_total{group,destination,status}` - Alerts sent to destinations
- `spreader_alerts_deduplicated_total{group}` - Deduplicated alerts
- `spreader_active_alerts{group}` - Currently active alerts per group
- `spreader_config_reload_success_total` - Successful config reloads
- `spreader_config_reload_failure_total` - Failed config reloads
