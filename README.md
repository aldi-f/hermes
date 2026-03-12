# Hermes - Alertmanager Routing & Distribution System

Hermes is an intermediary alert routing service that solves Alertmanager's limitations with OR matching and many-to-many alert routing.

## 🚀 Getting Started

**New to Hermes?** Start with our [10-minute tutorial](docs/tutorials/getting-started.md) to get Hermes running locally.

**Quick reference for experienced users:**

```bash
# Install
pip install -e .

# Run
python -m src.main

# Test
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"alerts":[{"status":"firing","labels":{"namespace":"test"},"annotations":{"summary":"test"},"startsAt":"2024-01-01T00:00:00Z"}]}'
```

## 📚 Documentation

- [Getting Started Tutorial](docs/tutorials/getting-started.md) - Zero to running in 10 minutes
- [Documentation Overview](docs/README.md) - Complete documentation guide
- [Tutorials](docs/tutorials/) - Hands-on tutorials for common scenarios
- [Concepts](docs/concepts/) - Deep dives into architecture and features
- [Examples](docs/examples/) - Complete, working configuration examples

### Quick Links

| Topic | Link |
|-------|------|
| Getting started | [Getting Started Guide](docs/tutorials/getting-started.md) |
| Configure Slack/Discord | [Alert Routing Guide](docs/tutorials/basic-alert-routing.md) |
| Reduce notification noise | [Alert Grouping Guide](docs/tutorials/group-alerts.md) |
| Multiple destinations | [Multiple Destinations Guide](docs/tutorials/multiple-destinations.md) |
| Advanced configuration | [Advanced Configuration Guide](docs/tutorials/advanced-routing.md) |
| How routing works | [Routing and Groups](docs/concepts/routing-and-groups.md) |
| How deduplication works | [Deduplication](docs/concepts/deduplication.md) |
| How to customize messages | [Templating](docs/concepts/templating.md) |
| Config examples | [Examples](docs/examples/) |
| Deploy to Kubernetes | [Kubernetes Section](#kubernetes) |
| Troubleshooting | [Troubleshooting Guide](docs/troubleshooting.md) |

## Configuration

For detailed configuration options, see the [Alert Routing Guide](docs/tutorials/basic-alert-routing.md) and [Examples](docs/examples/).

### Quick Config Example

```yaml
settings:
  fingerprint_strategy: "auto"
  deduplication_ttl: 300

destinations:
  - name: slack-alerts
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
    template:
      content: |
        {"text": "Alert: {{ status }} - {{ labels.alertname }}"}

groups:
  - name: team-a-alerts
    destinations: [slack-alerts]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
```

**For a complete working example**, see [docs/examples/simple-config.yaml](docs/examples/simple-config.yaml).

## Configuration

For detailed configuration options, see:
- [Alert Routing Guide](docs/tutorials/basic-alert-routing.md) - Setting up destinations and match rules
- [Routing and Groups](docs/concepts/routing-and-groups.md) - How OR routing works
- [Deduplication](docs/concepts/deduplication.md) - Fingerprinting and deduplication windows
- [Templating](docs/concepts/templating.md) - Customizing message formats
- [Examples](docs/examples/) - Complete configuration examples

### Quick Reference

**Config Reload:**
- Hermes automatically reloads config when file changes (every 30s by default)
- Environment: `CONFIG_RELOAD_INTERVAL=10` checks every 10s

**Key Settings:**
- `fingerprint_strategy`: `auto`, `alertmanager`, or `custom`
- `deduplication_ttl`: Keep alert state for N seconds (default: 300)
- `metrics_port`: Prometheus metrics port (default: 9090)

**Environment Variables:**
```bash
CONFIG_PATH=config.yaml       # Config file path
PORT=8080                     # HTTP server port
REDIS_URL=redis://localhost  # Optional: for multi-replica deduplication
SLACK_WEBHOOK_URL=...        # Use ${VAR_NAME} in config
```

### Quick Config Reference

| Feature | Description | Docs |
|---------|-------------|------|
| Match types | `label_equals`, `label_matches`, `label_contains`, etc. | [Routing](docs/concepts/routing-and-groups.md) |
| Group alerts | Combine similar alerts with `group_by` | [Tutorial](docs/tutorials/group-alerts.md) |
| Deduplication window | Resend grouped alerts every N seconds | [Deduplication](docs/concepts/deduplication.md) |
| Templates | Jinja2 templates for Slack/Discord | [Templating](docs/concepts/templating.md) |
| Multiple destinations | Send alerts to Slack + Discord | [Tutorial](docs/tutorials/multiple-destinations.md) |

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
| `ENABLE_RELOAD_CHECK` | `true` | Enable periodic config reload checks |
| `CONFIG_RELOAD_INTERVAL` | `30` | Config reload check interval in seconds |
| `REDIS_URL` | None | Redis connection URL (optional, for multi-replica deduplication) |

### Using Environment Variables in Config

Configuration values can reference environment variables using `${VAR_NAME}` syntax:

```yaml
destinations:
  - name: slack-alerts
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
```

If a referenced environment variable is not found, the application will fail to start with an error.

### Kubernetes Deployment

#### Using Helm

```yaml
# values.yaml
redis:
  enabled: true
  url: "redis-redis-master"
  port: 6379

envFrom:
  - secretRef:
      name: webhook-secrets
```

```bash
helm install hermes ./k8s/chart -f values.yaml
```

Or use an existing secret for Redis URL:

```yaml
redis:
  enabled: true
  existingSecret: "redis-secret"
  existingSecretKey: "redis-url"
```

#### Using Kustomize

Create a patch to inject environment variables:

```yaml
# deployment-patch.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hermes
spec:
  template:
    spec:
      containers:
        - name: hermes
          envFrom:
            - secretRef:
                name: webhook-secrets
```

Add to your kustomization:

```yaml
patches:
  - path: deployment-patch.yaml
```

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
