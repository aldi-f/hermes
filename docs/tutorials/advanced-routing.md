# Advanced Configuration Guide

This guide covers advanced configuration options including complex match patterns, fingerprint strategies, deduplication windows, and production setups.

## Complex Match Patterns

### Regex Patterns

Match alertnames starting with "High":
```yaml
match:
  - type: label_matches
    label: alertname
    pattern: "^High.*"
```

Match alertnames ending with "Error":
```yaml
match:
  - type: label_matches
    label: alertname
    pattern: ".*Error$"
```

Match alertnames containing "Database":
```yaml
match:
  - type: label_matches
    label: alertname
    pattern: ".*Database.*"
```

Match containers ending with "-db-":
```yaml
match:
  - type: label_matches
    label: container
    pattern: ".*-db-.*"
```

Match namespaces with pattern "team-*":
```yaml
match:
  - type: label_matches
    label: namespace
    pattern: "^team-.*"
```

### Multiple Contains Patterns

Match if alertname contains any of the values:
```yaml
match:
  - type: label_contains
    label: alertname
    values: [Database, DB, Postgres, MySQL]
```

### Not Patterns

Exclude specific namespaces:
```yaml
match:
  - type: label_not_equals
    label: namespace
    values: [kube-system, kube-public]
```

Exclude test environments:
```yaml
match:
  - type: label_not_contains
    label: environment
    values: [test, dev]
```

Exclude info severity:
```yaml
match:
  - type: label_not_equals
    label: severity
    values: [info, debug]
```

### Complex OR Patterns

Match if ANY rule matches:
```yaml
match:
  - type: label_equals
    label: namespace
    values: [team-a]

  - type: label_equals
    label: severity
    values: [critical]

  - type: label_contains
    label: alertname
    values: [Database]
```

## Fingerprint Strategies

### Auto (Recommended)

```yaml
settings:
  fingerprint_strategy: "auto"
```

Behavior:
- Uses Alertmanager fingerprint if available
- Falls back to custom fingerprint if not
- Best compatibility with Alertmanager

### Alertmanager

```yaml
settings:
  fingerprint_strategy: "alertmanager"
```

Behavior:
- Requires Alertmanager to provide fingerprint
- Fails if not present
- Ensures consistent fingerprinting across systems

### Custom

```yaml
settings:
  fingerprint_strategy: "custom"
```

Behavior:
- Always computes custom fingerprint from labels
- Independent of Alertmanager
- Full control over fingerprinting

## Deduplication Windows

### Critical Alerts: Remind Every Hour

```yaml
groups:
  - name: critical-alerts
    destinations: [slack-oncall]
    group_by: [alertname, cluster]
    deduplication_window: 3600  # 1 hour
    match:
      - type: label_equals
        label: severity
        values: [critical]
```

**Behavior:**
- First alert: Send notification
- Subsequent alerts (within hour): Deduplicate
- After 1 hour: Send notification again
- Repeat every hour while firing

### Database Alerts: Remind Every 30 Minutes

```yaml
groups:
  - name: database-alerts
    destinations: [slack-db-team]
    group_by: [alertname, database_name]
    deduplication_window: 1800  # 30 minutes
    match:
      - type: label_matches
        label: alertname
        pattern: ".*Database.*"
```

### Warning Alerts: Never Remind

```yaml
groups:
  - name: warning-alerts
    destinations: [slack-alerts]
    group_by: [alertname, cluster]
    deduplication_window: 0  # Never resend
    match:
      - type: label_equals
        label: severity
        values: [warning]
```

**Behavior:**
- Send notification once
- Wait for alert to resolve
- No reminders

## Environment Variables in Config

### Using Environment Variables

Keep secrets out of config files:

```yaml
destinations:
  - name: slack-webhook
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
```

Set variables:
```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

### Multiple Environment Variables

```yaml
destinations:
  - name: slack-team-a
    type: slack
    webhook_url: "${SLACK_TEAM_A_WEBHOOK_URL}"

  - name: discord-oncall
    type: discord
    webhook_url: "${DISCORD_ONCALL_WEBHOOK_URL}"

settings:
  deduplication_ttl: "${DEDUPLICATION_TTL}"  # Converted to int
```

**Important:** If a referenced environment variable is not found, Hermes will fail to start.

## Advanced Templates

### Conditional Rendering

```yaml
template:
  content: |
    {"blocks": [
      {
        "type": "header",
        "text": {
          "type": "plain_text",
          "text": "{% if status == 'firing' %}🚨 {% elif status == 'resolved' %}✅ {% endif %}{{ labels.alertname }}"
        }
      }
    ]}
```

### Severity-Based Coloring

**Slack:**
```jinja2
{% if labels.severity == 'critical' %}
🔴
{% elif labels.severity == 'warning' %}
🟡
{% else %}
🟢
{% endif %}
```

**Discord:**
```jinja2
"color": {% if labels.severity == 'critical' %}16711680{% elif labels.severity == 'warning' %}16776960{% else %}65280{% endif %}
```

### Links to Prometheus

```jinja2
{% if generatorURL %}
[View in Prometheus]({{ generatorURL }})
{% endif %}
```

### Iterate Over Labels

```jinja2
{% for key, value in labels.items() %}
• {{ key }}: {{ value }}
{% endfor %}
```

### Grouped Alert Iteration

```jinja2
{{ alerts | length }} alerts:
{% for alert in alerts %}
• {{ alert.labels.pod | default('unknown') }}: {{ alert.annotations.description | default('No description') }}
{% endfor %}
```

## Production Configuration

### Multi-Replica with Redis

```yaml
settings:
  fingerprint_strategy: "auto"
  deduplication_ttl: 300
  # redis_url: "redis://redis:6379/0"  # Or use REDIS_URL env var

# Set environment variable
export REDIS_URL=redis://redis:6379/0
```

### Production Deployment

```yaml
destinations:
  - name: slack-oncall
    type: slack
    webhook_url: "${SLACK_ONCALL_WEBHOOK_URL}"
    template:
      content: |
        {"blocks": [
          {
            "type": "header",
            "text": {"type": "plain_text", "text": "{{ labels.alertname }}"}
          },
          {
            "type": "section",
            "fields": [
              {"type": "mrkdwn", "text": "*Severity:* {{ labels.severity | upper }}"},
              {"type": "mrkdwn", "text": "*Status:* {{ status | upper }}"},
              {"type": "mrkdwn", "text": "*Namespace:* {{ labels.namespace }}"},
              {"type": "mrkdwn", "text": "*Cluster:* {{ labels.cluster | default('unknown') }}"}
            ]
          },
          {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "{{ annotations.summary }}\n{{ annotations.description | default('') }}"}
          },
          {
            "type": "divider"
          },
          {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "{% if generatorURL %}[View in Prometheus]({{ generatorURL }}){% endif %}"}
          }
        ]}

groups:
  - name: team-a-critical
    destinations: [slack-team-a, slack-oncall]
    group_by: [alertname, cluster]
    deduplication_window: 3600
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
      - type: label_equals
        label: severity
        values: [critical]

  - name: database-critical
    destinations: [slack-db-team, slack-oncall]
    group_by: [alertname, database_name, cluster]
    deduplication_window: 1800
    match:
      - type: label_matches
        label: alertname
        pattern: ".*Database.*"
      - type: label_equals
        label: severity
        values: [critical]

  - name: production-alerts
    destinations: [slack-ops-team]
    group_by: [alertname, cluster]
    match:
      - type: label_equals
        label: environment
        values: [production]

  - name: audit-all-alerts
    destinations: [slack-audit]
    group_by: [alertname]
    match:
      - type: always_match
```

## Configuration Examples

### Regex Pattern Matching

```yaml
groups:
  - name: high-resource-alerts
    destinations: [slack-alerts]
    match:
      - type: label_matches
        label: alertname
        pattern: "^(High|Low).*(CPU|Memory|Disk).*"
```

### Multiple Not Conditions

```yaml
groups:
  - name: exclude-test-and-dev
    destinations: [slack-alerts]
    match:
      - type: label_not_equals
        label: namespace
        values: [test, dev, staging]
      - type: label_not_equals
        label: severity
        values: [info, debug]
```

### Grouped Alerts with Window

```yaml
groups:
  - name: critical-grouped-with-window
    destinations: [slack-critical]
    group_by: [alertname, cluster]
    deduplication_window: 1800
    match:
      - type: label_equals
        label: severity
        values: [critical]
```

## Best Practices

### Use Regex for Pattern Matching

```yaml
# ✅ Good: One regex rule
match:
  - type: label_matches
    label: alertname
    pattern: ".*Database.*"

# ❌ Bad: Multiple equals rules
match:
  - type: label_equals
    label: alertname
    values: [PostgresDatabaseDown, MySQLDatabaseDown, RedisDatabaseDown]
```

### Use Not Operators to Exclude

```yaml
# ✅ Good: Explicit exclusion
match:
  - type: label_not_equals
    label: namespace
    values: [kube-system, kube-public]

# ❌ Bad: List all other namespaces
match:
  - type: label_equals
    label: namespace
    values: [team-a, team-b, team-c, ...]  # Endless list
```

### Use Deduplication Windows for Critical Alerts

```yaml
# ✅ Good: Critical alerts need visibility
groups:
  - name: critical
    deduplication_window: 3600
    match:
      - type: label_equals
        label: severity
        values: [critical]

# ✅ Good: Warning alerts don't need reminders
groups:
  - name: warning
    deduplication_window: 0  # or omit
    match:
      - type: label_equals
        label: severity
        values: [warning]
```

### Use Environment Variables for Secrets

```yaml
# ✅ Good: Secrets in environment
webhook_url: "${SLACK_WEBHOOK_URL}"

# ❌ Bad: Secrets in config
webhook_url: "https://hooks.slack.com/services/T000/B000/XXX"
```

## Next Steps

- [Templating](../concepts/templating.md) - Advanced template customization
- [Deduplication](../concepts/deduplication.md) - Fingerprinting and deduplication details
- [State Management](../concepts/state-management.md) - Redis for multi-replica deployments
- [Examples](../examples/) - Production-ready configuration examples
