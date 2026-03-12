# Multiple Destinations Guide

This guide explains how to configure alert routing to multiple destinations (Slack, Discord, etc.) and implement many-to-many alert routing.

## Configuring Multiple Destinations

### Define Multiple Destinations

```yaml
destinations:
  - name: slack-team-a
    type: slack
    webhook_url: "${SLACK_TEAM_A_WEBHOOK_URL}"
    template:
      content: |
        {"text": "{{ status }}: {{ labels.alertname }}"}

  - name: discord-oncall
    type: discord
    webhook_url: "${DISCORD_ONCALL_WEBHOOK_URL}"
    template:
      content: |
        {"content": "🚨 {{ labels.alertname }}"}

  - name: slack-ops-team
    type: slack
    webhook_url: "${SLACK_OPS_WEBHOOK_URL}"
    template:
      content: |
        {"text": "{{ labels.alertname }}: {{ annotations.summary }}"}
```

### Route to Single Destination

```yaml
groups:
  - name: team-a-alerts
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
```

Alerts from `team-a` namespace go only to `slack-team-a`.

### Route to Multiple Destinations

```yaml
groups:
  - name: critical-alerts
    destinations: [slack-team-a, discord-oncall]
    match:
      - type: label_equals
        label: severity
        values: [critical]
```

Critical alerts go to both `slack-team-a` and `discord-oncall`.

## Many-to-Many Routing

One alert can match multiple groups and be sent to multiple destinations:

```yaml
destinations:
  - name: slack-team-a
    type: slack
    webhook_url: "${SLACK_TEAM_A_WEBHOOK_URL}"

  - name: discord-oncall
    type: discord
    webhook_url: "${DISCORD_ONCALL_WEBHOOK_URL}"

  - name: slack-ops-team
    type: slack
    webhook_url: "${SLACK_OPS_WEBHOOK_URL}"

groups:
  - name: team-a-alerts
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]

  - name: critical-alerts
    destinations: [discord-oncall]
    match:
      - type: label_equals
        label: severity
        values: [critical]

  - name: production-alerts
    destinations: [slack-ops-team]
    match:
      - type: label_equals
        label: environment
        values: [production]
```

**Alert:** `namespace=team-a, severity=critical, environment=production`

**Routing:**
- Matches `team-a-alerts` → `slack-team-a`
- Matches `critical-alerts` → `discord-oncall`
- Matches `production-alerts` → `slack-ops-team`

**Result:** Alert sent to all three destinations.

## Deduplication Across Groups

Deduplication is **per group, per destination**.

```yaml
groups:
  - name: team-a
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]

  - name: critical
    destinations: [slack-team-a, discord-oncall]
    match:
      - type: label_equals
        label: severity
        values: [critical]
```

**Alert:** `namespace=team-a, severity=critical`

**Deduplication:**
- Group `team-a`, destination `slack-team-a`: First alert → send, subsequent → skip
- Group `critical`, destination `slack-team-a`: First alert → send, subsequent → skip
- Group `critical`, destination `discord-oncall`: First alert → send, subsequent → skip

**Result:**
- `slack-team-a`: Receives 2 notifications (one from each group)
- `discord-oncall`: Receives 1 notification

This is expected behavior with overlapping groups.

## Avoiding Duplicate Notifications

### Mutually Exclusive Groups

Make groups mutually exclusive to avoid duplicates:

```yaml
# ❌ Overlapping groups cause duplicates
groups:
  - name: team-a
    destinations: [slack-alerts]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]

  - name: critical
    destinations: [slack-alerts]
    match:
      - type: label_equals
        label: severity
        values: [critical]

# ✅ Mutually exclusive groups
groups:
  - name: team-a-critical
    destinations: [slack-alerts]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
      - type: label_equals
        label: severity
        values: [critical]

  - name: team-a-non-critical
    destinations: [slack-alerts]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
      - type: label_not_equals
        label: severity
        values: [critical]

  - name: other-critical
    destinations: [slack-alerts]
    match:
      - type: label_not_equals
        label: namespace
        values: [team-a]
      - type: label_equals
        label: severity
        values: [critical]
```

## Destination Types

### Slack

Simple text:
```yaml
- name: slack-simple
  type: slack
  webhook_url: "${SLACK_WEBHOOK_URL}"
  template:
    content: |
      {"text": "{{ labels.alertname }}: {{ annotations.summary }}"}
```

Block Kit:
```yaml
- name: slack-blockkit
  type: slack
  webhook_url: "${SLACK_WEBHOOK_URL}"
  template:
    content: |
      {"blocks": [
        {
          "type": "section",
          "text": {"type": "mrkdwn", "text": "*{{ labels.alertname }}*"}
        }
      ]}
```

### Discord

Simple:
```yaml
- name: discord-simple
  type: discord
  webhook_url: "${DISCORD_WEBHOOK_URL}"
  template:
    content: |
      {"content": "🚨 {{ labels.alertname }}"}
```

Embed:
```yaml
- name: discord-embed
  type: discord
  webhook_url: "${DISCORD_WEBHOOK_URL}"
  template:
    content: |
      {
        "embeds": [{
          "title": "{{ labels.alertname }}",
          "description": "{{ annotations.summary }}",
          "color": 16711680
        }]
      }
```

## Routing Patterns

### Team-Specific Routing

```yaml
groups:
  - name: team-a
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]

  - name: team-b
    destinations: [slack-team-b]
    match:
      - type: label_equals
        label: namespace
        values: [team-b]
```

### Severity-Based Routing

```yaml
groups:
  - name: critical-alerts
    destinations: [slack-critical, discord-oncall]
    match:
      - type: label_equals
        label: severity
        values: [critical]

  - name: warning-alerts
    destinations: [slack-warning]
    match:
      - type: label_equals
        label: severity
        values: [warning]
```

### Environment-Specific Routing

```yaml
groups:
  - name: production-alerts
    destinations: [slack-production-oncall, slack-production-team]
    match:
      - type: label_equals
        label: environment
        values: [production]

  - name: staging-alerts
    destinations: [slack-staging]
    match:
      - type: label_equals
        label: environment
        values: [staging]
```

### Service-Specific Routing

```yaml
groups:
  - name: database-alerts
    destinations: [slack-db-team, discord-db-oncall]
    match:
      - type: label_matches
        label: alertname
        pattern: ".*Database.*"

  - name: cache-alerts
    destinations: [slack-cache-team]
    match:
      - type: label_matches
        label: alertname
        pattern: ".*Cache.*"
```

### Audit Routing

```yaml
groups:
  - name: audit-all-alerts
    destinations: [slack-audit]
    match:
      - type: always_match
```

All alerts go to audit channel for logging.

### Combined Routing

```yaml
groups:
  # Team A alerts
  - name: team-a-alerts
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]

  # Critical alerts go to team + on-call
  - name: team-a-critical
    destinations: [slack-team-a, discord-oncall]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
      - type: label_equals
        label: severity
        values: [critical]

  # Production alerts go to ops team
  - name: production-alerts
    destinations: [slack-ops-team]
    match:
      - type: label_equals
        label: environment
        values: [production]

  # All alerts go to audit
  - name: audit-all-alerts
    destinations: [slack-audit]
    match:
      - type: always_match
```

## Complete Example

```yaml
settings:
  fingerprint_strategy: "auto"
  deduplication_ttl: 300

destinations:
  - name: slack-team-a
    type: slack
    webhook_url: "${SLACK_TEAM_A_WEBHOOK_URL}"
    template:
      content: |
        {"text": "Team A: {{ labels.alertname }} - {{ annotations.summary }}"}

  - name: discord-oncall
    type: discord
    webhook_url: "${DISCORD_ONCALL_WEBHOOK_URL}"
    template:
      content: |
        {"content": "🚨 {{ labels.alertname }}\n{{ annotations.summary }}"}

  - name: slack-ops-team
    type: slack
    webhook_url: "${SLACK_OPS_WEBHOOK_URL}"
    template:
      content: |
        {"text": "Ops: {{ labels.alertname }} - {{ annotations.summary }}"}

  - name: slack-audit
    type: slack
    webhook_url: "${SLACK_AUDIT_WEBHOOK_URL}"
    template:
      content: |
        {"text": "[{{ status }}] {{ labels.alertname }} | {{ labels.namespace }}"}

groups:
  - name: team-a-alerts
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]

  - name: critical-alerts
    destinations: [slack-team-a, discord-oncall]
    match:
      - type: label_equals
        label: severity
        values: [critical]

  - name: production-alerts
    destinations: [slack-ops-team]
    match:
      - type: label_equals
        label: environment
        values: [production]

  - name: audit-all-alerts
    destinations: [slack-audit]
    match:
      - type: always_match
```

## Next Steps

- [Templating](../concepts/templating.md) - Customize messages per destination
- [Routing and Groups](../concepts/routing-and-groups.md) - How OR routing works
- [Examples](../examples/) - Complete multi-destination configuration examples
