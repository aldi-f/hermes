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

  - name: slack-grouped
    type: slack
    webhook_url: "https://hooks.slack.com/services/yyy"
    template:
      content: |
        {"text": "*Alert:* `{{ alerts[0].labels.severity }}` - {{ group_labels.alertname }}\n*Cluster:* `{{ group_labels.cluster }}`\n*Messages:*\n{% for alert in alerts %}\n• {{ alert.annotations.description }}\n{% endfor %}"}

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

  - name: monitoring-team
    destinations: [slack-grouped]
    group_by: ["alertname", "cluster"]  # Group alerts by these labels
    match:
      - type: label_equals
        label: cluster
        values: [production, staging]
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

### Grouped Output

By default, Hermes sends one message per alert. To send multiple alerts in a single message, configure `group_by` with the labels to group by:

```yaml
groups:
  - name: oxygen-team
    destinations: [slack-alerts]
    group_by: ["alertname", "cluster"]  # Group alerts with same alertname and cluster
    match:
      - type: label_equals
        label: namespace
        values: [oxygen, dhc]
```

When `group_by` is configured, alerts with matching label values are combined into one message. For example, with `group_by: ["alertname", "cluster"]`, all alerts with the same alertname and cluster will be sent together. If `group_by` is not specified or empty, alerts are sent individually (default behavior).

### Template Variables

#### Individual Alert Templates (default)

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

#### Grouped Alert Templates (when `group_by` is configured)

Available in templates:

| Variable | Description |
|----------|-------------|
| `alerts` | List of alert objects (iterate with `{% for alert in alerts %}`) |
| `group_labels` | Labels used for grouping (as configured in `group_by`) |
| `status` | `firing` or `resolved` |
| `group_name` | Matching group name |
| `destination_name` | Destination name |

Within `alerts` iteration, each alert object has: `status`, `labels`, `annotations`, `startsAt`, `endsAt`, `generatorURL`, `fingerprint`.

**Example grouped template:**

```yaml
template:
  content: |
    *Alert:* `{{ alerts[0].labels.severity }}` - {{ group_labels.alertname }}
    *Cluster:* `{{ group_labels.cluster }}`
    *Messages:*
    {% for alert in alerts %}
    • {{ alert.annotations.description }}
    {% endfor %}
```

## Docker

```bash
docker build -t hermes:latest .
docker run -p 8080:8080 -p 9090:9090 -v $(pwd)/config.yaml:/config/config.yaml hermes:latest
```

For multi-replica deployments with Redis:

```bash
docker run -p 8080:8080 -p 9090:9090 \
  -v $(pwd)/config.yaml:/config/config.yaml \
  -e REDIS_URL=redis://redis:6379/0 \
  hermes:latest
```

## Kubernetes

### Using Kustomize

```bash
kubectl apply -k k8s/kustomize/overlays/prod
```

### Using Helm Chart

```bash
# Pull and install from OCI registry
helm install hermes oci://ghcr.io/aldi-f/hermes/charts/hermes --version 0.1.0

# Install with custom values
helm install hermes oci://ghcr.io/aldi-f/hermes/charts/hermes --version 0.1.0 \
  --set config.destinations[0].name=slack \
  --set config.destinations[0].type=slack \
  --set config.destinations[0].webhook_url=https://hooks.slack.com/services/xxx
```

For multi-replica deployments, enable Redis:

```bash
helm install hermes oci://ghcr.io/aldi-f/hermes/charts/hermes --version 0.1.0 \
  --set redis.enabled=true \
  --set config.destinations[0].name=slack \
  --set config.destinations[0].type=slack \
  --set config.destinations[0].webhook_url=https://hooks.slack.com/services/xxx
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
| `REDIS_URL` | None | Redis connection URL (optional, for multi-replica deduplication) |

## Stateless Architecture

Hermes is designed to be completely stateless. All state is kept in-memory with optional Redis for distributed deduplication:

- **In-memory cache**: Primary state storage, persists only while Hermes is running
- **Redis (optional)**: Enables distributed deduplication across multiple Hermes replicas
- **No persistence**: Alert state is lost on restart

### Trade-offs

**Without Redis:**
- ✅ No external dependencies
- ✅ Simpler deployment
- ⚠️ No cross-replica deduplication (may send duplicate alerts in multi-replica setups)
- ⚠️ State is lost on restart (may resend "firing" alerts)

**With Redis:**
- ✅ Distributed deduplication across replicas
- ✅ State persists across restarts (within TTL)
- ⚠️ Additional dependency
- ⚠️ Slightly increased latency

For single-replica deployments, Redis is optional. For multi-replica production deployments, Redis is recommended to avoid duplicate notifications.

## Metrics

- `spreader_alerts_received_total` - Total alerts received
- `spreader_alerts_matched_total{group}` - Alerts matched to groups
- `spreader_alerts_sent_total{group,destination,status}` - Alerts sent to destinations
- `spreader_alerts_deduplicated_total{group}` - Deduplicated alerts
- `spreader_active_alerts{group}` - Currently active alerts per group
- `spreader_config_reload_success_total` - Successful config reloads
- `spreader_config_reload_failure_total` - Failed config reloads
