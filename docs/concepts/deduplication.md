# Deduplication

This guide explains how Hermes prevents duplicate alert notifications through fingerprinting and state management.

## What is Deduplication?

Deduplication ensures that you don't receive multiple notifications for the same alert. When an alert is firing and continuously reported by Alertmanager, Hermes sends it once, then waits for the alert to resolve before sending it again.

**Without deduplication:** Alertmanager reports a firing alert every 30 seconds → You get a Slack notification every 30 seconds.

**With deduplication:** Alertmanager reports a firing alert every 30 seconds → You get one Slack notification. When the alert resolves, you get one "resolved" notification.

## How Deduplication Works

### The Flow

```
┌────────────────────────────────────────────────────────────────┐
│                       Deduplication Flow                       │
│                                                                │
│  1. Alertmanager sends firing alert → Hermes receives it        │
│  2. Hermes computes fingerprint (alert identity)                │
│  3. Hermes checks if state exists for this fingerprint+group    │
│  4. No state exists? → Save state, send notification           │
│  5. State exists with status="firing"? → Skip (duplicate)      │
│  6. State exists with status="resolved"? → Update state, send  │
│  7. Alertmanager sends resolved alert → Update state, send      │
│  8. State expires after TTL → Forget alert                      │
└────────────────────────────────────────────────────────────────┘
```

### Example Timeline

```
Time 00:00 - Alertmanager: firing (HighMemory, pod=web-1)
         → Hermes: No state, saves state, sends notification
         → You receive: "HighMemory: web-1 is at 85%"

Time 00:30 - Alertmanager: firing (HighMemory, pod=web-1)
         → Hermes: State exists (firing), skips
         → You receive: nothing (duplicate)

Time 01:00 - Alertmanager: firing (HighMemory, pod=web-1)
         → Hermes: State exists (firing), skips
         → You receive: nothing (duplicate)

Time 01:30 - Alertmanager: resolved (HighMemory, pod=web-1)
         → Hermes: Updates state to resolved, sends notification
         → You receive: "HighMemory: web-1 is resolved"

Time 06:00 - State expires (TTL = 300s = 5min)
         → Hermes: Forgets the alert
```

## Fingerprinting

### What is a Fingerprint?

A fingerprint is a unique identifier for an alert. It's computed from the alert's labels and determines whether two alerts are the same.

### How Fingerprints are Computed

Hermes supports three fingerprint strategies:

#### 1. Auto (Recommended)

```yaml
settings:
  fingerprint_strategy: "auto"
```

Behavior:
- If Alertmanager provides a `fingerprint` field, use it
- Otherwise, compute a custom fingerprint from labels

**Pros:**
- Works with Alertmanager automatically
- Falls back to custom fingerprint if needed
- Best compatibility

**Cons:**
- Depends on Alertmanager providing fingerprint (but has fallback)

#### 2. Alertmanager

```yaml
settings:
  fingerprint_strategy: "alertmanager"
```

Behavior:
- Require Alertmanager to provide a `fingerprint` field
- If not present, fail to process alert

**Pros:**
- Ensures consistent fingerprinting across systems
- Uses Alertmanager's proven algorithm

**Cons:**
- Fails if Alertmanager doesn't provide fingerprint
- Less flexible

#### 3. Custom

```yaml
settings:
  fingerprint_strategy: "custom"
```

Behavior:
- Always compute a custom fingerprint from labels
- Ignore Alertmanager's fingerprint

**Pros:**
- Full control over fingerprinting
- Works without Alertmanager

**Cons:**
- May differ from Alertmanager's fingerprint
- Requires label consistency

### Custom Fingerprint Algorithm

When computing a custom fingerprint, Hermes:

1. Sorts alert labels alphabetically
2. Concatenates label names and values
3. Computes SHA-256 hash

**Example:**
```yaml
Labels:
  alertname: HighMemory
  namespace: production
  pod: web-server-1
  severity: warning

Sorted:
  alertname: HighMemory
  namespace: production
  pod: web-server-1
  severity: warning

Concatenated:
  alertname=HighMemorynamespace=productionpod=web-server-1severity=warning

SHA-256:
  a3b2c1d4e5f6...
```

### Fingerprint Comparison

Two alerts have the same fingerprint if they have **the same labels**.

**Same fingerprint (duplicate):**
```yaml
Alert 1: {alertname: HighMemory, pod: web-1, severity: warning}
Alert 2: {alertname: HighMemory, pod: web-1, severity: warning}
```

**Different fingerprints:**
```yaml
Alert 1: {alertname: HighMemory, pod: web-1, severity: warning}
Alert 2: {alertname: HighMemory, pod: web-2, severity: warning}
# Different pod label
```

## Deduplication Scope

Deduplication is **per group**, not global. An alert can be sent multiple times if it matches multiple groups.

### Example: Many-to-Many Routing

```yaml
groups:
  - name: team-a
    destinations: [slack-team-a]
    match:
      - type: label_equals
        label: namespace
        values: [production]

  - name: critical
    destinations: [slack-oncall]
    match:
      - type: label_equals
        label: severity
        values: [critical]
```

Alert: `namespace=production, severity=critical, alertname=DatabaseDown`

**Deduplication behavior:**
- Group "team-a": First alert → send, subsequent alerts → skip (per group)
- Group "critical": First alert → send, subsequent alerts → skip (per group)
- Both groups get the alert independently

Result: Alert sent to Team A and On-call separately, with per-group deduplication.

## Deduplication TTL (Time to Live)

TTL determines how long Hermes remembers an alert's state.

```yaml
settings:
  deduplication_ttl: 300  # 5 minutes
```

### TTL Behavior

- When alert is first received: State is created with TTL
- State is refreshed on each alert receipt (while firing)
- When alert resolves: State is marked resolved
- State is deleted after TTL expires

### TTL vs Alert Lifetime

```
Alert: firing (continuously reported by Alertmanager)

Time 00:00 - First alert: State created, TTL=300s
Time 00:30 - Second alert: State refreshed, TTL=300s (reset)
Time 01:00 - Third alert: State refreshed, TTL=300s (reset)
Time 01:30 - Resolved: State marked resolved
Time 01:30 + 300s = 06:30 - State expires (TTL reached)
```

### Choosing TTL Values

| Scenario | Recommended TTL | Reason |
|---------|----------------|--------|
| Development | 60-120 seconds | Quick feedback, forget old alerts fast |
| Production | 300-600 seconds (5-10 min) | Balance between noise and memory |
| Long-running alerts | 1800-3600 seconds (30-60 min) | For alerts that stay firing for hours |

**Too short:** Alerts may be re-sent unexpectedly if Alertmanager reports slowly.

**Too long:** Higher memory usage, longer state retention.

## Deduplication Window (for Grouped Alerts)

The `deduplication_window` controls how often to resend **grouped** alerts that are continuously firing.

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
```

### Window Behavior

| Value | Behavior |
|-------|----------|
| `0` | Never resend (default) - send once, wait for resolve |
| `> 0` | Resend every N seconds while firing |

### When to Use Deduplication Window

**Use with critical alerts:**
- Critical alerts need ongoing visibility
- People may miss the first notification
- Periodic reminders are helpful

**Example:**
```yaml
groups:
  - name: critical-database-alerts
    destinations: [pagerduty, slack-oncall]
    group_by: [alertname, cluster]
    deduplication_window: 3600  # Remind every hour
    match:
      - type: label_equals
        label: severity
        values: [critical]
```

**Don't use with non-critical alerts:**
- Warning alerts don't need reminders
- Use `deduplication_window: 0` (default)

**Example:**
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

### Window Timeline

```
deduplication_window: 3600 (1 hour)

Time 00:00 - First grouped alert: Send notification
Time 00:30 - Second grouped alert: Skip (duplicate)
Time 01:00 - Third grouped alert: Send notification (window elapsed)
Time 01:30 - Fourth grouped alert: Skip (duplicate)
Time 02:00 - Fifth grouped alert: Send notification (window elapsed)
```

The window resets after each send, ensuring periodic reminders.

## State Management

### In-Memory State (Default)

State is kept in memory, per Hermes instance.

```yaml
settings:
  deduplication_ttl: 300
  # No redis_url configured
```

**Characteristics:**
- Fast (no network calls)
- Simple (no dependencies)
- **State lost on restart**
- **No cross-replica deduplication**

**Use when:**
- Single Hermes replica
- Development/testing
- Can tolerate state loss on restart

**Don't use when:**
- Multiple replicas (duplicates will occur)
- Need state persistence across restarts

### Redis State (Multi-Replica)

State is stored in Redis, shared across replicas.

```yaml
settings:
  deduplication_ttl: 300

# Set environment variable
export REDIS_URL=redis://redis:6379/0
```

**Characteristics:**
- Distributed deduplication across replicas
- State persists across restarts (within TTL)
- **Additional dependency (Redis)**
- **Slightly increased latency**

**Use when:**
- Multiple Hermes replicas
- Production deployment
- Need to avoid duplicate notifications

**Don't use when:**
- Single replica (unnecessary complexity)
- Can tolerate Redis outages

See [State Management](state-management.md) for more details on Redis configuration.

## Troubleshooting

### Duplicate Alerts

**Symptom:** Same alert sent multiple times.

**Possible causes:**

1. **Multiple replicas without Redis:**
   ```bash
   # Check replicas
   kubectl get pods -l app=hermes
   # If > 1, need Redis
   ```

2. **Fingerprint mismatch:**
   ```yaml
   # Check fingerprint strategy
   settings:
     fingerprint_strategy: "auto"  # Try "auto" first
   ```

3. **TTL too short:**
   ```yaml
   settings:
     deduplication_ttl: 300  # Increase if alerts are re-sent too quickly
   ```

### Alerts Not Being Sent

**Symptom:** Expected alerts not arriving.

**Possible causes:**

1. **Labels inconsistent:**
   - Ensure labels are consistent across alert reports
   - Check for changing label values

2. **Fingerprint too aggressive:**
   - If using `custom` strategy, alerts with different labels have different fingerprints
   - Try `auto` strategy

### State Not Clearing

**Symptom:** High memory usage, old alerts remembered.

**Solution:**
```yaml
settings:
  deduplication_ttl: 300  # Reduce from default if needed
```

### Grouped Alerts Not Resending

**Symptom:** Critical grouped alerts not sending periodic reminders.

**Solution:**
```yaml
groups:
  - name: critical-alerts
    deduplication_window: 3600  # Set > 0 to enable
```

## Metrics

Monitor deduplication with Prometheus metrics:

```bash
curl http://hermes:9090/metrics | grep deduplicated
```

**Metrics:**
- `spreader_alerts_deduplicated_total{group}` - Total deduplicated alerts
- `spreader_active_alerts{group}` - Currently active alerts per group

**Alert on:**
- High `deduplicated_total` = Deduplication is working
- `deduplicated_total` not increasing = May have issue
- High `active_alerts` = Many alerts firing (check state size)

## Best Practices

### 1. Use Auto Fingerprint Strategy

```yaml
# ✅ Recommended
settings:
  fingerprint_strategy: "auto"

# ❌ Avoid unless needed
settings:
  fingerprint_strategy: "custom"
```

### 2. Choose Appropriate TTL

```yaml
# Development: Short TTL
settings:
  deduplication_ttl: 60

# Production: Medium TTL
settings:
  deduplication_ttl: 300

# Long-running alerts: Longer TTL
settings:
  deduplication_ttl: 1800
```

### 3. Use Window for Critical Alerts

```yaml
# ✅ Good: Remind about critical alerts
groups:
  - name: critical
    deduplication_window: 3600
    match:
      - type: label_equals
        label: severity
        values: [critical]

# ✅ Good: No reminders for warnings
groups:
  - name: warning
    deduplication_window: 0  # or omit (defaults to 0)
    match:
      - type: label_equals
        label: severity
        values: [warning]
```

### 4. Use Redis for Multi-Replica

```yaml
# ✅ Multi-replica: Use Redis
export REDIS_URL=redis://redis:6379/0

# ❌ Multi-replica without Redis: Duplicates occur
```

## Next Steps

- [State Management](state-management.md) - Redis configuration and deployment
- [Group Alerts Guide](../tutorials/group-alerts.md) - Grouped alerts and deduplication windows
- [Architecture](../architecture.md) - Complete system architecture
