# Alert Grouping Guide

This guide explains how to combine similar alerts into single notifications to reduce notification noise.

## Enabling Grouping

Group alerts by configuring `group_by` in a group definition:

```yaml
groups:
  - name: team-a-alerts
    destinations: [slack-alerts]
    group_by: [alertname, cluster]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
```

**Behavior:**
- Alerts with same `alertname` AND `cluster` labels are combined
- One notification instead of multiple
- Reduced notification noise

## Grouping Configuration

### group_by Field

```yaml
groups:
  - name: my-group
    destinations: [slack-alerts]
    group_by: [label1, label2, ...]
    match:
      - type: always_match
```

**Parameters:**
- `group_by`: List of label names to group by
- Alerts with same label values for all labels in `group_by` are combined

### Grouping Logic

Alerts are grouped if they have **identical values** for all labels in `group_by`.

**Example:**
```yaml
group_by: [alertname, cluster]
```

| Alert | alertname | cluster | Group |
|-------|-----------|---------|-------|
| Alert 1 | HighMemory | production | Group A |
| Alert 2 | HighMemory | production | Group A |
| Alert 3 | HighMemory | staging | Group B |
| Alert 4 | HighCPU | production | Group C |

Result:
- Group A: Alerts 1, 2 (same alertname and cluster)
- Group B: Alert 3 (different cluster)
- Group C: Alert 4 (different alertname)

Each group sends **one** notification.

## Grouping Strategies

### Group by Alert Name

```yaml
groups:
  - name: group-by-alertname
    destinations: [slack-alerts]
    group_by: [alertname]
    match:
      - type: label_equals
        label: environment
        values: [production]
```

All alerts with same `alertname` are grouped, regardless of other labels.

### Group by Alert Name and Cluster

```yaml
groups:
  - name: group-by-alertname-and-cluster
    destinations: [slack-alerts]
    group_by: [alertname, cluster]
    match:
      - type: label_equals
        label: environment
        values: [production]
```

Alerts with same `alertname` AND `cluster` are grouped.

### Group by Namespace

```yaml
groups:
  - name: group-by-namespace
    destinations: [slack-alerts]
    group_by: [namespace]
    match:
      - type: label_equals
        label: environment
        values: [production]
```

All alerts from same namespace are grouped together.

### Group by Service

```yaml
groups:
  - name: group-by-service
    destinations: [slack-alerts]
    group_by: [service]
    match:
      - type: always_match
```

All alerts for same service are grouped together.

### Group by Severity

```yaml
groups:
  - name: group-by-severity
    destinations: [slack-alerts]
    group_by: [severity]
    match:
      - type: label_equals
        label: environment
        values: [production]
```

All alerts with same severity are grouped together.

### Group by Multiple Labels

```yaml
groups:
  - name: group-by-multiple
    destinations: [slack-alerts]
    group_by: [alertname, namespace, severity]
    match:
      - type: label_equals
        label: environment
        values: [production]
```

Alerts with same `alertname`, `namespace`, AND `severity` are grouped.

### Multiple Groups with Different Grouping

```yaml
groups:
  - name: alertname-grouping
    destinations: [slack-alerts]
    group_by: [alertname]
    match:
      - type: label_equals
        label: environment
        values: [production]

  - name: cluster-grouping
    destinations: [slack-cluster]
    group_by: [cluster]
    match:
      - type: label_equals
        label: environment
        values: [production]
```

An alert can match multiple groups and be sent with different grouping.

## Grouped Template Variables

When `group_by` is configured, templates have access to additional variables:

### common_labels

Labels shared by **ALL** alerts in the group.

```yaml
Alerts:
  - alertname: HighMemory, cluster: production, pod: web-1, severity: warning
  - alertname: HighMemory, cluster: production, pod: web-2, severity: warning

common_labels:
  alertname: HighMemory
  cluster: production
  severity: warning

# pod is NOT in common_labels (different values)
```

### common_annotations

Annotations shared by **ALL** alerts in the group.

### alerts

List of all alert objects. Use `{% for alert in alerts %}` to iterate.

Each alert has:
- `status`: `firing` or `resolved`
- `labels`: Dict of alert labels
- `annotations`: Dict of alert annotations
- `startsAt`: Alert start timestamp
- `endsAt`: Alert end timestamp (optional)
- `generatorURL`: Link to Alertmanager/Prometheus
- `fingerprint`: Alert fingerprint

### group_labels

Labels used for grouping (from `group_by` configuration).

```yaml
group_by: [alertname, cluster]

group_labels:
  alertname: HighMemory
  cluster: production
```

## Template Examples

### Simple Grouped Template

```yaml
destinations:
  - name: slack-grouped
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
    template:
      content: |
        {"text": "{{ alerts | length }} alerts: {{ common_labels.alertname }} in {{ common_labels.cluster }}"}
```

Output:
```
3 alerts: HighMemory in production
```

### Detailed Grouped Template

```yaml
template:
  content: |
    {"blocks": [
      {
        "type": "section",
        "text": {
          "type": "mrkdwn",
          "text": "*{{ common_labels.alertname }}*\n*Cluster:* {{ common_labels.cluster }}\n*Severity:* {{ common_labels.severity }}\n\n*Alerts ({{ alerts | length }}):*\n{% for alert in alerts %}• {{ alert.labels.pod }}: {{ alert.annotations.description }}\n{% endfor %}"
        }
      }
    ]}
```

### Discord Grouped Template

```yaml
destinations:
  - name: discord-grouped
    type: discord
    webhook_url: "${DISCORD_WEBHOOK_URL}"
    template:
      content: |
        {
          "content": "{{ alerts | length }} alerts",
          "embeds": [{
            "title": "{{ common_labels.alertname }}",
            "description": "Cluster: {{ common_labels.cluster }}",
            "fields": [
              {
                "name": "Affected Pods",
                "value": "{% for alert in alerts %}{{ alert.labels.pod | default('unknown') }}\n{% endfor %}"
              }
            ]
          }]
        }
```

## Grouping Best Practices

### Choose Meaningful Grouping Labels

```yaml
# Good: Group by alert type and environment
group_by: [alertname, environment]

# Good: Group by service
group_by: [service]

# Avoid: Too many grouping labels
group_by: [alertname, cluster, namespace, severity, pod]  # Too specific
```

### Use Common Labels for Context

```yaml
# Good: Show what's common
{"text": "{{ common_labels.severity }} alert: {{ common_labels.alertname }}"}

# Avoid: Only show individual alerts without context
{"text": "{% for alert in alerts %}{{ alert.alertname }}\n{% endfor %}"}
```

### Include Alert Count

Always show how many alerts are in the group:

```yaml
{"text": "{{ alerts | length }} alerts: ..."}
```

### Check for Label Presence

Don't assume labels exist:

```yaml
# Good: Use default values
{% for alert in alerts %}
• Pod: {{ alert.labels.pod | default('unknown') }}
{% endfor %}

# Avoid: Assume label exists
{{ alerts[0].labels.pod }}  # May not exist
```

## Deduplication Window

Configure `deduplication_window` to resend grouped alerts periodically:

```yaml
groups:
  - name: critical-alerts
    destinations: [slack-alerts]
    group_by: [alertname, cluster]
    deduplication_window: 3600  # Resend every hour
    match:
      - type: label_equals
        label: severity
        values: [critical]

  - name: warning-alerts
    destinations: [slack-alerts]
    group_by: [alertname, cluster]
    deduplication_window: 0  # Never resend
    match:
      - type: label_equals
        label: severity
        values: [warning]
```

**Window Values:**
- `0`: Never resend (default)
- `> 0`: Resend every N seconds while firing

**Use Cases:**
- Critical alerts: Remind periodically (e.g., every hour)
- Warning alerts: Send once, wait for resolve
- Long-running alerts: Ensure ongoing visibility

## Complete Example

```yaml
settings:
  fingerprint_strategy: "auto"
  deduplication_ttl: 300

destinations:
  - name: slack-grouped
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
    template:
      content: |
        {"blocks": [
          {
            "type": "header",
            "text": {"type": "plain_text", "text": "{{ alerts | length }} {{ common_labels.alertname }} alerts"}
          },
          {
            "type": "section",
            "fields": [
              {"type": "mrkdwn", "text": "*Cluster:* {{ common_labels.cluster }}"},
              {"type": "mrkdwn", "text": "*Severity:* {{ common_labels.severity | upper }}"}
            ]
          },
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "{% for alert in alerts %}• {{ alert.labels.pod | default('unknown') }}: {{ alert.annotations.description | default('No description') }}\n{% endfor %}"
            }
          }
        ]}

groups:
  - name: production-alerts
    destinations: [slack-grouped]
    group_by: [alertname, cluster]
    deduplication_window: 0
    match:
      - type: label_equals
        label: environment
        values: [production]

  - name: critical-alerts
    destinations: [slack-grouped]
    group_by: [alertname, cluster]
    deduplication_window: 3600
    match:
      - type: label_equals
        label: severity
        values: [critical]
```

## Next Steps

- [Deduplication](../concepts/deduplication.md) - Deduplication windows explained
- [Templating](../concepts/templating.md) - Advanced template customization
- [Examples](../examples/) - Grouped alert configuration examples
