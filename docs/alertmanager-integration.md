# Alertmanager Integration

This guide shows how to configure Alertmanager to send alerts to Hermes.

## Basic Configuration

Add Hermes as a receiver in your `alertmanager.yml`:

```yaml
route:
  receiver: 'hermes'
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: 'hermes'
    webhook_configs:
      - url: 'http://hermes.default.svc.cluster.local/webhook'
        send_resolved: true
```

## Advanced Routing

If you want to use Hermes alongside other receivers:

```yaml
route:
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'hermes'
    - match:
        severity: warning
      receiver: 'hermes-warning'

receivers:
  - name: 'hermes'
    webhook_configs:
      - url: 'http://hermes.default.svc.cluster.local/webhook'
        send_resolved: true

  - name: 'hermes-warning'
    webhook_configs:
      - url: 'http://hermes.default.svc.cluster.local/webhook'
        send_resolved: true

  - name: 'default'
    slack_configs:
      - channel: '#alerts'
        send_resolved: true
```

## Webhook Payload Format

Alertmanager sends the following payload to Hermes:

```json
{
  "receiver": "hermes",
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "HighMemoryUsage",
        "namespace": "oxygen",
        "severity": "critical"
      },
      "annotations": {
        "summary": "Memory usage above 90%",
        "description": "Pod oxygen-api has memory usage at 95%"
      },
      "startsAt": "2024-01-15T10:30:00Z",
      "endsAt": null,
      "generatorURL": "http://prometheus/graph?g0.expr=...",
      "fingerprint": "abc123def456"
    }
  ],
  "groupLabels": {
    "alertname": "HighMemoryUsage"
  },
  "commonLabels": {
    "severity": "critical"
  },
  "commonAnnotations": {},
  "externalURL": "http://alertmanager:9093"
}
```

## Testing the Integration

### Using curl

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "TestAlert",
        "namespace": "oxygen"
      },
      "annotations": {
        "summary": "Test alert from curl"
      },
      "startsAt": "2024-01-15T10:00:00Z"
    }]
  }'
```

### Using amtool

```bash
amtool alert add \
  alertname=TestAlert \
  namespace=oxygen \
  severity=warning \
  --annotation=summary="Test alert" \
  --alertmanager.url=http://localhost:9093
```

## Verification

Check the Hermes health endpoint:

```bash
curl http://hermes:8080/health
```

Expected response:
```json
{
  "status": "ok",
  "config_loaded": true,
  "redis": "connected",
  "queue_size": 0
}
```

## Troubleshooting

### Alerts not being received

1. Check Alertmanager logs:
   ```bash
   kubectl logs -l app=alertmanager
   ```

2. Verify the webhook URL is correct:
   ```bash
   kubectl get svc hermes
   ```

3. Check network connectivity:
   ```bash
   kubectl exec -it <alertmanager-pod> -- curl http://hermes:80/health
   ```

### Alerts being deduplicated unexpectedly

Check the fingerprint strategy in your config:

```yaml
settings:
  fingerprint_strategy: "auto"  # Uses Alertmanager fingerprint if available
```

### Missing destinations

Verify your group configuration:

```bash
curl http://hermes:8080/destinations
```