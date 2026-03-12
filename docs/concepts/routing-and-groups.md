# Routing and Groups

This guide explains how Hermes routing works, how it differs from Alertmanager, and how to design effective groups.

## The Problem with Alertmanager

Alertmanager routes alerts using a tree structure with AND logic:

```
route:
  receiver: 'default'
  routes:
    - match:
        severity: critical
        namespace: production
      receiver: 'team-a'
```

**Issue:** This route only matches alerts where **both** `severity=critical` **AND** `namespace=production`. You can't easily say "route to team-a if severity is critical OR namespace is production OR it's a database alert".

## Hermes OR-Based Routing

Hermes uses OR logic - an alert matches if **ANY** of the match rules match.

### Alertmanager (AND)

```yaml
route:
  routes:
    - match:
        severity: critical
        namespace: production
      receiver: 'team-a'
```

Matches: `severity=critical` **AND** `namespace=production`

### Hermes (OR)

```yaml
groups:
  - name: team-a
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: severity
        values: [critical]
      - type: label_equals
        label: namespace
        values: [production]
```

Matches: `severity=critical` **OR** `namespace=production`

## Many-to-Many Routing

One of the most powerful features of Hermes is many-to-many routing: one alert can match multiple groups and be sent to multiple destinations.

### Example Scenario

You have:
- Team A responsible for `production` namespace
- Team B responsible for all `database` alerts
- On-call team responsible for all `critical` alerts

An alert with:
- `namespace=production`
- `alertname=PostgreSQLDown`
- `severity=critical`

Should go to:
- Team A (because `namespace=production`)
- Team B (because `alertname=PostgreSQLDown` - it's a database)
- On-call (because `severity=critical`)

### Hermes Configuration

```yaml
destinations:
  - name: slack-team-a
    type: slack
    webhook_url: "${TEAM_A_WEBHOOK_URL}"

  - name: slack-team-b
    type: slack
    webhook_url: "${TEAM_B_WEBHOOK_URL}"

  - name: slack-oncall
    type: slack
    webhook_url: "${ONCALL_WEBHOOK_URL}"

groups:
  - name: team-a
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [production]

  - name: team-b
    destinations: [slack-team-b]
    match:
      - type: label_matches
        label: alertname
        pattern: ".*Database.*|.*Postgres.*|.*MySQL.*"

  - name: oncall
    destinations: [slack-oncall]
    match:
      - type: label_equals
        label: severity
        values: [critical]
```

### Routing Flow

```
Alert: namespace=production, alertname=PostgreSQLDown, severity=critical

                    │
                    ▼
        ┌─────────────────────────┐
        │   Check all groups      │
        └────────────┬────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │Team A   │ │Team B   │ │On-call  │
   │namespace│ │Database │ │critical │
   │production?│ │pattern? │ │severity?│
   └────┬────┘ └────┬────┘ └────┬────┘
        │YES        │YES        │YES
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │Send to  │ │Send to  │ │Send to  │
   │Team A   │ │Team B   │ │On-call  │
   └─────────┘ └─────────┘ └─────────┘

Result: Alert sent to all 3 destinations
```

This is impossible with Alertmanager's tree-based routing.

## Match Rule Types

Hermes supports several match types:

### Label Equals

```yaml
- type: label_equals
  label: namespace
  values: [team-a, team-b]
```

Matches: `namespace == "team-a"` **OR** `namespace == "team-b"`

### Label Contains

```yaml
- type: label_contains
  label: namespace
  values: [team]
```

Matches: `namespace contains "team"` (e.g., `team-a`, `team-production`, `my-team`)

### Label Matches (Regex)

```yaml
- type: label_matches
  label: container
  pattern: ".*-db-.*"
```

Matches: `container =~ ".*-db-.*"` (e.g., `postgres-db-main`, `mysql-db-slave`)

### Label Not Equals

```yaml
- type: label_not_equals
  label: namespace
  values: [kube-system, kube-public]
```

Matches: `namespace != "kube-system"` **AND** `namespace != "kube-public"`

### Label Not Contains

```yaml
- type: label_not_contains
  label: namespace
  values: [test, dev]
```

Matches: `namespace does not contain "test"` **AND** `namespace does not contain "dev"`

### Label Not Matches

```yaml
- type: label_not_matches
  label: alertname
  pattern: "Test.*"
```

Matches: `alertname !~ "Test.*"`

### Annotation Match Types

Same as label types but for annotations:

- `annotation_equals`
- `annotation_contains`
- `annotation_matches`

```yaml
- type: annotation_contains
  label: description
  values: [database, postgres]
```

### Always Match

```yaml
- type: always_match
```

Matches all alerts (useful for catch-all groups).

## Group Configuration Structure

```yaml
groups:
  - name: unique-group-name          # Required: unique identifier
    destinations: [slack-alerts]       # Required: list of destination names
    match:                             # Required: list of match rules
      - type: label_equals
        label: namespace
        values: [team-a]
    group_by: [alertname, cluster]     # Optional: group alerts by labels
    deduplication_window: 3600        # Optional: resend every N seconds
```

### Group Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier for the group |
| `destinations` | Yes | List of destination names to send alerts to |
| `match` | Yes | List of match rules (OR logic) |
| `group_by` | No | Labels to group alerts by (see [Alert Grouping Guide](../tutorials/group-alerts.md)) |
| `deduplication_window` | No | Resend grouped alerts every N seconds (0 = never) |

## Group Matching Logic

An alert matches a group if:

1. The alert's status is `firing` or `resolved`
2. **ANY** of the match rules in the group match the alert

### Example

```yaml
groups:
  - name: critical-or-db-alerts
    match:
      - type: label_equals
        label: severity
        values: [critical]
      - type: label_matches
        label: container
        pattern: ".*-db-.*"
```

This group matches alerts where:
- `severity == "critical"` **OR**
- `container =~ ".*-db-.*"`

### Alert Examples

| Alert Labels | Matches? | Why |
|--------------|----------|-----|
| `severity=critical` | ✅ Yes | First match rule |
| `container=postgres-db-main` | ✅ Yes | Second match rule |
| `severity=warning, container=app-server` | ❌ No | No match rule matches |
| `severity=critical, container=mysql-db` | ✅ Yes | First rule matches (second also matches) |

## Alertmanager vs Hermes Comparison

| Feature | Alertmanager | Hermes |
|---------|--------------|--------|
| **Routing Logic** | AND (all rules must match) | OR (any rule can match) |
| **Many-to-Many** | ❌ No (tree-based) | ✅ Yes (flat groups) |
| **Group Matching** | Hierarchical tree | Flat list |
| **Overlap** | Difficult (complex tree) | Easy (multiple groups) |
| **Match Complexity** | Nested routes | Simple match rules |

### Alertmanager Example

```yaml
route:
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: 'critical'
      routes:
        - match:
            namespace: production
          receiver: 'team-a'
        - match:
            namespace: staging
          receiver: 'team-b'
```

This creates a nested tree. To add database alerts, you need to add more nesting.

### Hermes Example

```yaml
groups:
  - name: critical
    match:
      - type: label_equals
        label: severity
        values: [critical]

  - name: team-a
    match:
      - type: label_equals
        label: namespace
        values: [production]

  - name: database
    match:
      - type: label_matches
        label: container
        pattern: ".*-db-.*"
```

Add as many groups as you want. No nesting required.

## Best Practices for Group Design

### 1. Use Descriptive Group Names

```yaml
- name: team-a-production
  # Better than:
- name: group-1
```

### 2. Group by Responsibility

Organize groups by who should receive alerts, not by what the alert is about:

```yaml
groups:
  - name: team-a
    match:
      - type: label_equals
        label: namespace
        values: [team-a, team-production]

  - name: team-b
    match:
      - type: label_equals
        label: namespace
        values: [team-b]

  - name: database-team
    match:
      - type: label_matches
        label: container
        pattern: ".*-db-.*"
```

### 3. Use Multiple Match Rules

Don't create multiple groups when one will do:

```yaml
# ❌ Bad: Multiple similar groups
- name: team-a-production
  match:
    - type: label_equals
      label: namespace
      values: [production]

- name: team-a-staging
  match:
    - type: label_equals
      label: namespace
      values: [staging]

# ✅ Good: Single group with multiple values
- name: team-a
  match:
    - type: label_equals
      label: namespace
      values: [production, staging]
```

### 4. Use Regex for Patterns

```yaml
# ❌ Bad: Hardcoded values
- name: db-alerts
  match:
    - type: label_equals
      label: container
      values: [postgres-db-main, postgres-db-slave, mysql-db-main]

# ✅ Good: Regex pattern
- name: db-alerts
  match:
    - type: label_matches
      label: container
      pattern: ".*-db-.*"
```

### 5. Use Destinations for Routing, Not Groups

Groups determine **what** matches, destinations determine **where** it goes:

```yaml
destinations:
  - name: slack-team-a
    type: slack
    webhook_url: "${TEAM_A_WEBHOOK_URL}"

  - name: slack-team-b
    type: slack
    webhook_url: "${TEAM_B_WEBHOOK_URL}"

groups:
  - name: production
    destinations: [slack-team-a, slack-team-b]
    match:
      - type: label_equals
        label: namespace
        values: [production]

  - name: staging
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [staging]
```

Production alerts go to both teams, staging alerts go to Team A only.

### 6. Use Catch-All Groups for Visibility

```yaml
groups:
  - name: catch-all
    destinations: [slack-alerts-audit]
    match:
      - type: always_match

  - name: team-a
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
```

The catch-all group ensures you see all alerts even if they don't match specific groups.

## Common Patterns

### Route by Severity

```yaml
destinations:
  - name: slack-critical
    type: slack
    webhook_url: "${CRITICAL_WEBHOOK_URL}"

  - name: slack-warning
    type: slack
    webhook_url: "${WARNING_WEBHOOK_URL}"

  - name: slack-info
    type: slack
    webhook_url: "${INFO_WEBHOOK_URL}"

groups:
  - name: critical
    destinations: [slack-critical]
    match:
      - type: label_equals
        label: severity
        values: [critical]

  - name: warning
    destinations: [slack-warning]
    match:
      - type: label_equals
        label: severity
        values: [warning]

  - name: info
    destinations: [slack-info]
    match:
      - type: label_equals
        label: severity
        values: [info]
```

### Route by Team

```yaml
groups:
  - name: team-a
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [team-a, team-production, team-staging]

  - name: team-b
    destinations: [slack-team-b]
    match:
      - type: label_equals
        label: namespace
        values: [team-b]
```

### Route by Service Type

```yaml
groups:
  - name: database
    destinations: [slack-db-team]
    match:
      - type: label_matches
        label: container
        pattern: ".*-db-.*"

  - name: cache
    destinations: [slack-cache-team]
    match:
      - type: label_matches
        label: container
        pattern: ".*-cache-.*"

  - name: app
    destinations: [slack-app-team]
    match:
      - type: label_matches
        label: container
        pattern: ".*-app-.*"
```

### Route by Environment

```yaml
groups:
  - name: production
    destinations: [slack-production]
    match:
      - type: label_equals
        label: environment
        values: [production]

  - name: staging
    destinations: [slack-staging]
    match:
      - type: label_equals
        label: environment
        values: [staging]

  - name: development
    destinations: [slack-dev]
    match:
      - type: label_equals
        label: environment
        values: [development]
```

## Troubleshooting

### Alert Not Matching Any Group

1. Check the alert labels match the match rules
2. Verify the match type (equals, contains, matches)
3. Check for typos in label names or values
4. Use a catch-all group to debug:

```yaml
groups:
  - name: debug-catch-all
    destinations: [slack-debug]
    match:
      - type: always_match
```

### Alert Matching Multiple Groups

This is expected behavior! Hermes supports many-to-many routing. If you don't want this, make your groups more specific.

### Alerts Going to Wrong Destination

Check the group's `destinations` field:

```yaml
groups:
  - name: team-a
    destinations: [slack-team-a, slack-team-b]  # Both get alerts
    match:
      - type: label_equals
        label: namespace
        values: [team-a]
```

## Next Steps

- [Alert Routing Guide](../tutorials/basic-alert-routing.md) - Configuring routing to Slack/Discord
- [Deduplication](deduplication.md) - How alert fingerprinting works
- [Templating](templating.md) - Customize notification formats
- [Alert Grouping Guide](../tutorials/group-alerts.md) - Reduce notification noise with grouping
