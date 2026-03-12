# Architecture

## Overview

Hermes is an alert routing and distribution system that sits between Alertmanager and notification destinations (Slack, Discord). It solves the problem of OR-based routing and many-to-many alert relationships that Alertmanager doesn't support natively.

```
┌──────────────┐     ┌─────────┐     ┌──────────────────┐
│ Alertmanager │────▶│ Hermes  │────▶│ Slack / Discord  │
└──────────────┘     └─────────┘     └──────────────────┘
                             │
                             ▼
                      ┌─────────────┐
                      │    Redis    │ (optional, for distributed state)
                      └─────────────┘
```

## Components

### 1. Webhook Receiver (`src/main.py`)

FastAPI application that receives Alertmanager webhooks on `/webhook`.

- Validates incoming payloads
- Routes to AlertProcessor
- Exposes `/health`, `/ready`, `/metrics` endpoints

### 2. Alert Processor (`src/webhooks.py`)

Core processing logic:

1. Receives webhook payload
2. For each alert:
   - Match against group rules (OR logic)
   - Check deduplication with StateManager
   - Render templates
   - Send to destinations

### 3. Matcher Engine (`src/matcher.py`)

Rule matching with OR logic:

```
Group "team-a":
  namespace == "namespace-a" OR namespace == "namespace-b"
  OR container =~ "container-a-.*"
  OR queueName contains "queue-a"
```

Supported match types:
- `label_equals` / `label_not_equals`
- `label_contains` / `label_not_contains`
- `label_matches` / `label_not_matches`
- `annotation_*` variants
- `always_match`

### 4. State Manager (`src/state.py`)

Hybrid state management:

```
┌─────────────────────────────────────────────────────────────┐
│                      StateManager                            │
│                                                              │
│   ┌──────────────┐     ┌──────────────┐                     │
│   │ Local Cache  │────▶│   Redis      │                     │
│   │  (in-memory) │     │ (optional)   │                     │
│   └──────────────┘     └──────────────┘                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Write path:**
1. Update local cache (immediate)
2. Write to Redis (async, if available)

**Read path:**
1. Try Redis (if available)
2. Fallback to local cache

### 5. Replay Queue

When Redis is unavailable:

```
┌──────────┐     ┌───────────────┐     ┌──────────┐
│  Alert   │────▶│ Replay Queue  │────▶│  Redis   │
│ Received │     │ (in-memory)   │     │Recovered │
└──────────┘     └───────────────┘     └──────────┘
                        │
                        │ Max size: 1000
                        │ (configurable)
                        ▼
                 Drop oldest if full
```

### 6. Circuit Breaker

Prevents cascade failures:

```
         ┌─────────────────┐
         │      START      │
         └────────┬────────┘
                  │
                  ▼
         ┌─────────────────┐
    ┌───▶│     CLOSED      │◀────┐
    │    │  (operating)    │     │
    │    └────────┬────────┘     │
    │             │              │
    │   3+ failures│              │ Recovery
    │             │              │
    │             ▼              │
    │    ┌─────────────────┐     │
    │    │      OPEN       │     │
    │    │  (failing fast) │     │
    │    └────────┬────────┘     │
    │             │              │
    │   60s timeout│              │
    │             │              │
    │             ▼              │
    │    ┌─────────────────┐     │
    │    │   HALF_OPEN     │─────┘
    │    │    (testing)    │  Success
    │    └─────────────────┘
    │             │
    │    Failure  │
    └─────────────┘
```

### 7. Template Engine (`src/templates.py`)

Jinja2-based templating:

```jinja2
{
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "{% if status == 'firing' %}🚨 Alert{% else %}✅ Resolved{% endif %}"
      }
    }
  ]
}
```

Available context:
- `status`, `labels`, `annotations`
- `startsAt`, `endsAt`, `generatorURL`
- `fingerprint`, `group_name`, `destination_name`

## Data Flow

### Alert Processing Flow

```
┌───────────────┐
│ Webhook POST  │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Parse Payload │
└───────┬───────┘
        │
        ▼
┌───────────────┐     ┌─────────────┐
│ For Each Alert│────▶│ Match Rules │
└───────────────┘     └──────┬──────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │  Match Found    │           │  No Match       │
    └────────┬────────┘           └─────────────────┘
             │
             ▼
    ┌─────────────────┐
    │  Check State    │
    │  (Deduplicate)  │
    └────────┬────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌─────────┐    ┌─────────────┐
│   Send  │    │  Duplicate  │
└────┬────┘    └─────────────┘
     │
     ▼
┌─────────────────┐
│ Render Template │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  POST Webhook   │
│  (with retries) │
└─────────────────┘
```

### Deduplication Logic

```
                    ┌─────────────┐
                    │ Alert       │
                    │ status=firing│
                    └──────┬──────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ State exists for       │
              │ fingerprint + group?   │
              └────────────┬───────────┘
                    │             │
                   Yes            No
                    │             │
                    ▼             ▼
            ┌─────────────┐ ┌─────────────┐
            │ status ==   │ │ Create state│
            │ "firing"?   │ │ Send alert  │
            └──────┬──────┘ └─────────────┘
               │         │
              Yes        No
               │         │
               ▼         ▼
        ┌───────────┐ ┌─────────────┐
        │ Duplicate │ │ Update state│
        │ (skip)    │ │ Send alert  │
        └───────────┘ └─────────────┘

                    ┌─────────────┐
                    │ Alert       │
                    │ status=resolved│
                    └──────┬──────┘
                           │
                           ▼
              ┌────────────────────────┐
              │ State exists with      │
              │ status="firing"?       │
              └────────────┬───────────┘
                    │             │
                   Yes            No
                    │             │
                    ▼             ▼
            ┌─────────────┐ ┌─────────────┐
            │ Update state│ │ Skip        │
            │ Send alert  │ │ (no firing) │
            └─────────────┘ └─────────────┘
```

## Deployment

### Single Replica (Dev/Test)

```
┌─────────────────────────────────────────┐
│                 Pod                      │
│                                          │
│   ┌──────────┐                           │
│   │ Hermes   │ (in-memory state)        │
│   └──────────┘                           │
│                                          │
└─────────────────────────────────────────┘
```

### Multi-Replica (Production)

```
┌─────────────────────────────────────────────────────────────┐
│                      Kubernetes Cluster                      │
│                                                              │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│   │ Hermes Pod 1│  │ Hermes Pod 2│  │ Hermes Pod 3│         │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│          │                │                │                │
│          └────────────────┼────────────────┘                │
│                           │                                 │
│                           ▼                                 │
│                    ┌─────────────┐                          │
│                    │    Redis    │                          │
│                    │  (Sentinel) │                          │
│                    └─────────────┘                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_PATH` | `config.yaml` | Path to config file |
| `PORT` | `8080` | HTTP server port |
| `ENABLE_RELOAD_CHECK` | `true` | Enable periodic config reload checks |
| `CONFIG_RELOAD_INTERVAL` | `30` | Config reload check interval in seconds |
| `REDIS_URL` | None | Redis connection URL (optional) |
| `LOG_FORMAT` | `text` | Log format (text/json) |
| `LOG_LEVEL` | `INFO` | Log level |

### Config File Structure

```yaml
settings:
  fingerprint_strategy: "auto"
  deduplication_ttl: 300
  redis_url: "redis://redis:6379/0"
  replay_queue_size: 1000

destinations:
  - name: slack-blockkit
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
    template:
      content: '{"blocks": [...]}'

  - name: slack-legacy
    type: slack
    webhook_url: "${SLACK_LEGACY_WEBHOOK_URL}"
    attachments_template:
      content: '[{"color": "...", "fields": [...]}]'

groups:
  - name: team-a
    destinations: [slack-blockkit]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
```

**Note:** Only one of `template` or `attachments_template` can be specified for Slack destinations.

## Metrics

See `/metrics` endpoint for Prometheus metrics:

| Metric | Type | Labels |
|--------|------|--------|
| `spreader_alerts_received_total` | Counter | - |
| `spreader_alerts_matched_total` | Counter | group |
| `spreader_alerts_sent_total` | Counter | group, destination, status |
| `spreader_alerts_deduplicated_total` | Counter | group |
| `spreader_redis_connected` | Gauge | - |
| `spreader_redis_queue_size` | Gauge | - |

## Related Documentation

For configuration guides and in-depth concept documentation, see:

- [Documentation Overview](README.md) - Complete documentation index
- [Getting Started Guide](tutorials/getting-started.md) - Installation and basic setup
- [Routing and Groups](concepts/routing-and-groups.md) - How OR routing works
- [Deduplication](concepts/deduplication.md) - Fingerprinting and state management
- [Templating](concepts/templating.md) - Customizing notification formats
- [State Management](concepts/state-management.md) - Redis vs in-memory state
- [Guides](tutorials/) - Configuration guides for common scenarios
- [Examples](examples/) - Complete, working configuration examples
