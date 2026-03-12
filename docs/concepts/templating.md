# Templating

This guide explains how to customize alert notifications using Jinja2 templates for Slack, Discord, and other destinations.

## Jinja2 Templates

Hermes uses [Jinja2](https://jinja.palletsprojects.com/) templating engine to format alert notifications. Templates give you full control over how alerts appear in Slack, Discord, or other destinations.

## Template Variables

### Individual Alert Templates (default)

When sending individual alerts (no `group_by` configured), templates have access to:

| Variable | Type | Description |
|----------|------|-------------|
| `status` | string | `firing` or `resolved` |
| `labels` | dict | Alert labels (e.g., `{alertname: HighCPU, namespace: production}`) |
| `annotations` | dict | Alert annotations (e.g., `{summary: CPU is high, description: CPU at 90%}`) |
| `startsAt` | string | Alert start timestamp (ISO 8601) |
| `endsAt` | string | Alert end timestamp (ISO 8601, optional) |
| `generatorURL` | string | Link to Alertmanager/Prometheus graph |
| `fingerprint` | string | Alert fingerprint (unique identifier) |
| `group_name` | string | Name of the matching group |
| `destination_name` | string | Name of the destination |

### Grouped Alert Templates (when `group_by` is configured)

When using grouped alerts, templates have access to additional variables:

| Variable | Type | Description |
|----------|------|-------------|
| `alerts` | list | List of alert objects (iterate with `{% for alert in alerts %}`) |
| `group_labels` | dict | Labels used for grouping (from `group_by` config) |
| `common_labels` | dict | Labels shared by ALL alerts in the group |
| `common_annotations` | dict | Annotations shared by ALL alerts in the group |
| `status` | string | `firing` or `resolved` |
| `group_name` | string | Name of the matching group |
| `destination_name` | string | Name of the destination |

Within `alerts` iteration, each alert object has:
- `status`, `labels`, `annotations`, `startsAt`, `endsAt`, `generatorURL`, `fingerprint`

## Template Syntax

### Basic Variables

```jinja2
{{ status }}
{{ labels.alertname }}
{{ annotations.summary }}
{{ startsAt }}
```

### Conditional Rendering

```jinja2
{% if status == 'firing' %}
🚨 Alert Firing
{% elif status == 'resolved' %}
✅ Alert Resolved
{% endif %}
```

### Loops

```jinja2
{% for label_name, label_value in labels.items() %}
• {{ label_name }}: {{ label_value }}
{% endfor %}

{% for alert in alerts %}
• {{ alert.labels.pod }}: {{ alert.annotations.description }}
{% endfor %}
```

### Filters

```jinja2
{{ labels.severity | upper }}
{{ annotations.summary | default('No description') }}
{{ labels.pod | default('unknown') }}
{{ startsAt | default('N/A') }}
```

### Complex Logic

```jinja2
{% if labels.severity == 'critical' %}
🚨 CRITICAL
{% elif labels.severity == 'warning' %}
⚠️ WARNING
{% else %}
ℹ️ INFO
{% endif %}
```

## Slack Templates

### Simple Text Format

```yaml
destinations:
  - name: slack-simple
    type: slack
    webhook_url: "${SLACK_WEBHOOK_URL}"
    template:
      content: |
        {"text": "{{ status | upper }}: {{ labels.alertname }}\n{{ annotations.summary }}"}
```

Output:
```
FIRING: HighCPU
CPU is at 90%
```

### Block Kit Format (Recommended)

Slack Block Kit provides rich formatting with multiple elements:

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
              "text": "{% if status == 'firing' %}🚨 {% elif status == 'resolved' %}✅ {% endif %}{{ labels.alertname }}"
            }
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
            "text": {
              "type": "mrkdwn",
              "text": "{{ annotations.summary }}\n{{ annotations.description | default('') }}"
            }
          }
        ]}
```

**Block Kit Blocks:**

**Header:**
```jinja2
{
  "type": "header",
  "text": {
    "type": "plain_text",
    "text": "Alert Title"
  }
}
```

**Section with Text:**
```jinja2
{
  "type": "section",
  "text": {
    "type": "mrkdwn",
    "text": "Markdown text here"
  }
}
```

**Section with Fields:**
```jinja2
{
  "type": "section",
  "fields": [
    {"type": "mrkdwn", "text": "*Key:* Value"},
    {"type": "mrkdwn", "text": "*Key:* Value"}
  ]
}
```

**Divider:**
```jinja2
{
  "type": "divider"
}
```

### Grouped Alert Template (Slack)

```yaml
groups:
  - name: grouped-alerts
    destinations: [slack-alerts]
    group_by: [alertname, cluster]
    template:
      content: |
        {"blocks": [
          {
            "type": "header",
            "text": {
              "type": "plain_text",
              "text": "{{ alerts | length }} {{ common_labels.alertname }} alerts in {{ common_labels.cluster }}"
            }
          },
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "{% for alert in alerts %}• {{ alert.labels.pod | default('unknown') }}: {{ alert.annotations.description | default('No description') }}\n{% endfor %}"
            }
          }
        ]}
```

## Discord Templates

### Simple Format

```yaml
destinations:
  - name: discord-simple
    type: discord
    webhook_url: "${DISCORD_WEBHOOK_URL}"
    template:
      content: |
        {"content": "🚨 **{{ status | upper }}** {{ labels.alertname }}\n{{ annotations.summary }}"}
```

Output:
```
🚨 **FIRING** HighCPU
CPU is at 90%
```

### Embed Format (Rich Formatting)

```yaml
destinations:
  - name: discord-embed
    type: discord
    webhook_url: "${DISCORD_WEBHOOK_URL}"
    template:
      content: |
        {
          "content": "{% if status == 'firing' %}🚨 {% elif status == 'resolved' %}✅ {% endif %}{{ labels.alertname }}",
          "embeds": [{
            "title": "{{ labels.alertname }}",
            "description": "{{ annotations.summary }}",
            "color": 16711680 if status == 'firing' else 65280,
            "fields": [
              {"name": "Severity", "value": "{{ labels.severity | upper }}"},
              {"name": "Status", "value": "{{ status | upper }}"},
              {"name": "Namespace", "value": "{{ labels.namespace }}"},
              {"name": "Cluster", "value": "{{ labels.cluster | default('unknown') }}"}
            ],
            "timestamp": "{{ startsAt }}"
          }]
        }
```

**Discord Embed Fields:**

- `title`: Embed title
- `description`: Embed description
- `color`: Embed color (decimal RGB)
- `fields`: Array of field objects
- `timestamp`: ISO 8601 timestamp
- `url`: Embed URL
- `footer`: Footer object
- `image`: Image object
- `thumbnail`: Thumbnail object

**Color Values:**
- Red: `16711680` (0xFF0000)
- Green: `65280` (0x00FF00)
- Yellow: `16776960` (0xFFFF00)
- Blue: `255` (0x0000FF)

### Grouped Alert Template (Discord)

```yaml
template:
  content: |
    {
      "content": "{{ alerts | length }} alerts grouped",
      "embeds": [{
        "title": "{{ common_labels.alertname }}",
        "description": "Cluster: {{ common_labels.cluster }}",
        "color": 16711680 if status == 'firing' else 65280,
        "fields": [
          {
            "name": "Affected Pods",
            "value": "{% for alert in alerts %}{{ alert.labels.pod | default('unknown') }}\n{% endfor %}"
          }
        ]
      }]
    }
```

## Template Best Practices

### 1. Use Default Values

```jinja2
# ✅ Good: Use default for optional labels
{{ labels.pod | default('unknown') }}

# ❌ Bad: May fail if label doesn't exist
{{ labels.pod }}
```

### 2. Conditionally Render Sections

```jinja2
# ✅ Good: Only show if value exists
{% if generatorURL %}
[View in Prometheus]({{ generatorURL }})
{% endif %}

# ✅ Good: Only show if label exists
{% if labels.cluster %}
*Cluster:* {{ labels.cluster }}
{% endif %}
```

### 3. Use Filters for Formatting

```jinja2
{{ labels.severity | upper }}
{{ startsAt | default('N/A') }}
{{ annotations.summary | default('No description') }}
```

### 4. Escape Special Characters

In Slack Block Kit and Discord embeds, text is automatically escaped for markdown. If you need literal text, use plain text types.

### 5. Group Related Fields

```yaml
# ✅ Good: Group severity and status together
fields: [
  {"type": "mrkdwn", "text": "*Severity:* {{ labels.severity | upper }}"},
  {"type": "mrkdwn", "text": "*Status:* {{ status | upper }}"}
]
```

### 6. Use Emojis for Visual Cues

```jinja2
{% if status == 'firing' %}🚨{% elif status == 'resolved' %}✅{% endif %}
{% if labels.severity == 'critical' %}🔴{% elif labels.severity == 'warning' %}🟡{% else %}🟢{% endif %}
```

## Common Patterns

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

### Conditional Sections

```jinja2
{% if labels.namespace %}
*Namespace:* {{ labels.namespace }}
{% endif %}

{% if labels.cluster %}
*Cluster:* {{ labels.cluster }}
{% endif %}
```

## Template Examples

### Simple Alert Template

```yaml
template:
  content: |
    {"text": "{{ status | upper }}: {{ labels.alertname }} - {{ annotations.summary }}"}
```

### Detailed Alert Template (Slack Block Kit)

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
          "text": "{{ annotations.summary }}\n{{ annotations.description | default('') }}"
        }
      },
      {
        "type": "divider"
      },
      {
        "type": "section",
        "text": {
          "type": "mrkdwn",
          "text": "{% if generatorURL %}[View in Prometheus]({{ generatorURL }}){% endif %}"
        }
      }
    ]}
```

### Grouped Alert Template (Slack)

```yaml
template:
  content: |
    {"blocks": [
      {
        "type": "header",
        "text": {
          "type": "plain_text",
          "text": "{{ alerts | length }} {{ common_labels.alertname }} alerts"
        }
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
```

### Discord Embed Template

```yaml
template:
  content: |
    {
      "content": "{% if status == 'firing' %}🚨 {% elif status == 'resolved' %}✅ {% endif %}{{ labels.alertname }}",
      "embeds": [{
        "title": "{{ labels.alertname }}",
        "description": "{{ annotations.summary }}",
        "color": 16711680 if status == 'firing' else 65280,
        "fields": [
          {"name": "Severity", "value": "{{ labels.severity | upper }}"},
          {"name": "Status", "value": "{{ status | upper }}"},
          {"name": "Namespace", "value": "{{ labels.namespace }}"},
          {"name": "Cluster", "value": "{{ labels.cluster | default('unknown') }}"},
          {"name": "Pod", "value": "{{ labels.pod | default('unknown') }}"}
        ],
        "timestamp": "{{ startsAt }}",
        "url": "{{ generatorURL | default('') }}"
      }]
    }
```

## Testing Templates

### Test with Curl

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "TestAlert",
        "namespace": "production",
        "severity": "warning"
      },
      "annotations": {
        "summary": "Test summary",
        "description": "Test description"
      },
      "startsAt": "2024-01-01T00:00:00Z",
      "generatorURL": "http://prometheus/graph?g0.expr=..."
    }]
  }'
```

Check the destination (Slack/Discord) to see the rendered template.

## Troubleshooting

### Template Not Rendering

1. Check for Jinja2 syntax errors (braces, quotes)
2. Verify template is valid JSON/YAML
3. Check that variables exist (use `| default()`)
4. Check Hermes logs for template errors

### Variables Not Showing

```jinja2
# ❌ May not exist
{{ labels.pod }}

# ✅ Use default
{{ labels.pod | default('unknown') }}
```

### Invalid JSON Output

Jinja2 templates must produce valid JSON:

```jinja2
# ❌ Invalid JSON (unescaped quotes)
{"text": "{{ annotations.summary }}"}

# ✅ Valid JSON (summary should be escaped automatically, but be careful)
{"text": "{{ annotations.summary | default('') }}"}
```

### Slack Block Kit Not Showing

1. Verify Block Kit JSON structure
2. Check Slack API documentation for block types
3. Test template in Slack Block Kit Builder

## Next Steps

- [Slack Block Kit Builder](https://app.slack.com/block-kit-builder/) - Visual builder for Slack templates
- [Discord Webhook Documentation](https://discord.com/developers/docs/resources/webhook) - Discord webhook reference
- [Jinja2 Documentation](https://jinja.palletsprojects.com/) - Jinja2 template language
- [Group Alerts Guide](../tutorials/group-alerts.md) - Grouped alert templates
