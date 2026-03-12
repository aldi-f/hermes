# Alert Routing Guide

This guide explains how to configure alert routing to destinations like Slack and Discord.

## Slack Configuration

### Slack Webhook Setup

1. Go to [Slack incoming webhooks](https://api.slack.com/messaging/webhooks)
2. Create a Slack app and enable incoming webhooks
3. Add a webhook to your channel
4. Copy the webhook URL

### Simple Slack Destination

```yaml
destinations:
  - name: slack-alerts
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
    template:
      content: |
        {"text": "Alert: {{ status }} - {{ labels.alertname }}\n{{ annotations.summary }}"}
```

### Slack Block Kit Format

Block Kit provides rich formatting:

```yaml
destinations:
  - name: slack-blockkit
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
    template:
      content: |
        {"blocks": [
          {
            "type": "header",
            "text": {
              "type": "plain_text",
              "text": "{{ labels.alertname }}"
            }
          },
          {
            "type": "section",
            "fields": [
              {"type": "mrkdwn", "text": "*Severity:* {{ labels.severity | upper }}"},
              {"type": "mrkdwn", "text": "*Status:* {{ status | upper }}"}
            ]
          },
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "{{ annotations.summary }}"
            }
          }
        ]}
```

## Discord Configuration

### Discord Webhook Setup

1. Go to your Discord server settings
2. Go to Integrations → Webhooks
3. Create a new webhook
4. Select a channel
5. Copy the webhook URL

### Simple Discord Destination

```yaml
destinations:
  - name: discord-alerts
    type: discord
    webhook_url: "${DISCORD_WEBHOOK_URL}"
    template:
      content: |
        {"content": "🚨 **{{ status | upper }}** {{ labels.alertname }}\n{{ annotations.summary }}"}
```

### Discord Embed Format

Embeds provide rich formatting:

```yaml
destinations:
  - name: discord-embed
    type: discord
    webhook_url: "${DISCORD_WEBHOOK_URL}"
    template:
      content: |
        {
          "embeds": [{
            "title": "{{ labels.alertname }}",
            "description": "{{ annotations.summary }}",
            "color": 16711680 if status == 'firing' else 65280,
            "fields": [
              {"name": "Severity", "value": "{{ labels.severity | upper }}"},
              {"name": "Status", "value": "{{ status | upper }}"}
            ]
          }]
        }
```

## Routing Configuration

### Group Configuration Structure

```yaml
groups:
  - name: unique-group-name
    destinations: [slack-alerts, discord-oncall]
    match:
      - type: label_equals
        label: namespace
        values: [team-a, team-b]
```

**Group Fields:**
- `name`: Unique identifier
- `destinations`: List of destination names
- `match`: List of match rules (OR logic)

### Match Types

**Label Equals:**
```yaml
match:
  - type: label_equals
    label: namespace
    values: [team-a, team-b]
```
Matches: `namespace == "team-a"` OR `namespace == "team-b"`

**Label Contains:**
```yaml
match:
  - type: label_contains
    label: namespace
    values: [team]
```
Matches: `namespace contains "team"`

**Label Matches (Regex):**
```yaml
match:
  - type: label_matches
    label: container
    pattern: ".*-db-.*"
```
Matches: `container =~ ".*-db-.*"` (e.g., `postgres-db-main`)

**Label Not Equals:**
```yaml
match:
  - type: label_not_equals
    label: namespace
    values: [kube-system, kube-public]
```
Matches: `namespace != "kube-system"` AND `namespace != "kube-public"`

**Label Not Contains:**
```yaml
match:
  - type: label_not_contains
    label: namespace
    values: [test, dev]
```
Matches: `namespace does not contain "test"` AND `namespace does not contain "dev"`

**Label Not Matches:**
```yaml
match:
  - type: label_not_matches
    label: alertname
    pattern: "Test.*"
```
Matches: `alertname !~ "Test.*"`

**Always Match:**
```yaml
match:
  - type: always_match
```
Matches all alerts (catch-all)

### OR Logic in Match Rules

Hermes uses OR logic - an alert matches if **ANY** match rule matches:

```yaml
groups:
  - name: team-a-or-critical
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
      - type: label_equals
        label: severity
        values: [critical]
```

This group matches alerts where:
- `namespace == "team-a"` **OR**
- `severity == "critical"`

## Routing Examples

### Route by Namespace

```yaml
groups:
  - name: team-a
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [team-a, team-production, team-staging]
```

### Route by Severity

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

### Route by Regex Pattern

```yaml
groups:
  - name: database-alerts
    destinations: [slack-db-team]
    match:
      - type: label_matches
        label: alertname
        pattern: ".*Database.*|.*Postgres.*|.*MySQL.*"
```

### Route by Environment

```yaml
groups:
  - name: production-alerts
    destinations: [slack-production]
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

### Route by Multiple Rules

```yaml
groups:
  - name: production-critical
    destinations: [slack-oncall]
    match:
      - type: label_equals
        label: environment
        values: [production]
      - type: label_equals
        label: severity
        values: [critical]
```

Matches production alerts OR critical alerts.

### Exclude Namespaces

```yaml
groups:
  - name: non-kube-system
    destinations: [slack-alerts]
    match:
      - type: label_not_equals
        label: namespace
        values: [kube-system, kube-public]
```

### Multiple Destinations

```yaml
destinations:
  - name: slack-team
    type: slack
    webhook_url: "${SLACK_TEAM_WEBHOOK_URL}"

  - name: discord-oncall
    type: discord
    webhook_url: "${DISCORD_ONCALL_WEBHOOK_URL}"

groups:
  - name: critical-alerts
    destinations: [slack-team, discord-oncall]
    match:
      - type: label_equals
        label: severity
        values: [critical]
```

Critical alerts go to both Slack and Discord.

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
        {"blocks": [
          {
            "type": "header",
            "text": {"type": "plain_text", "text": "{{ labels.alertname }}"}
          },
          {
            "type": "section",
            "fields": [
              {"type": "mrkdwn", "text": "*Severity:* {{ labels.severity | upper }}"},
              {"type": "mrkdwn", "text": "*Namespace:* {{ labels.namespace }}"}
            ]
          },
          {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "{{ annotations.summary }}"}
          }
        ]}

  - name: discord-oncall
    type: discord
    webhook_url: "${DISCORD_ONCALL_WEBHOOK_URL}"
    template:
      content: |
        {"content": "🚨 {{ labels.alertname }}\n{{ annotations.summary }}"}

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

  - name: database-alerts
    destinations: [slack-team-a]
    match:
      - type: label_matches
        label: alertname
        pattern: ".*Database.*"
```

## Next Steps

- [Routing and Groups](../concepts/routing-and-groups.md) - How OR routing works
- [Templating](../concepts/templating.md) - Customizing message formats
- [Examples](../examples/) - Complete configuration examples
