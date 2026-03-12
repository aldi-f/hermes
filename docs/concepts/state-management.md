# State Management

This guide explains Hermes's state management options: in-memory state for single-replica deployments and Redis for multi-replica deployments.

## What is State Management?

Hermes maintains state about alerts to enable deduplication. When an alert is firing and continuously reported by Alertmanager, Hermes remembers it to avoid sending duplicate notifications.

State includes:
- Alert fingerprint (unique identifier)
- Alert status (`firing` or `resolved`)
- Group the alert belongs to
- Timestamp of last update

## State Options

### Option 1: In-Memory State (Default)

State is kept in RAM, per Hermes instance.

```yaml
settings:
  deduplication_ttl: 300
  # No redis_url configured
```

**Architecture:**
```
┌─────────────────────────────────┐
│         Hermes Instance          │
│                                 │
│  ┌──────────────────────────┐   │
│  │  In-Memory State Store   │   │
│  │  (RAM)                   │   │
│  └──────────────────────────┘   │
└─────────────────────────────────┘
```

**Pros:**
- ✅ Fast (no network calls)
- ✅ Simple (no external dependencies)
- ✅ Easy to set up and debug
- ✅ No additional infrastructure

**Cons:**
- ❌ State lost on restart (may resend "firing" alerts)
- ❌ No cross-replica deduplication (may send duplicates in multi-replica)
- ❌ State not persistent (lost if pod crashes)

**Use when:**
- Single Hermes replica
- Development/testing environments
- Can tolerate state loss on restart
- Don't need distributed deduplication

### Option 2: Redis State (Multi-Replica)

State is stored in Redis, shared across replicas.

```yaml
settings:
  deduplication_ttl: 300

# Set environment variable
export REDIS_URL=redis://redis:6379/0
```

**Architecture:**
```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Hermes 1   │  │   Hermes 2   │  │   Hermes 3   │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       └─────────────────┼─────────────────┘
                         │
                         ▼
                  ┌─────────────┐
                  │    Redis    │
                  │             │
                  │ State Store │
                  └─────────────┘
```

**Pros:**
- ✅ Distributed deduplication across replicas
- ✅ State persists across restarts (within TTL)
- ✅ Shared state across all replicas
- ✅ Better for production multi-replica

**Cons:**
- ❌ Additional dependency (Redis)
- ❌ Slightly increased latency (network calls)
- ❌ More complex deployment
- ❌ Need to manage Redis HA if required

**Use when:**
- Multiple Hermes replicas
- Production deployment
- Need to avoid duplicate notifications
- Want state persistence across restarts

## Choosing the Right Option

### Decision Tree

```
Need multi-replica?
├─ No → Use in-memory state (default)
└─ Yes → Use Redis state
```

**Detailed decision:**

| Scenario | Recommended State | Reason |
|----------|------------------|--------|
| Development | In-memory | Simple, no dependencies |
| Single replica production | In-memory (or Redis if you prefer) | Either works |
| Multi-replica production | Redis | Required for cross-replica deduplication |
| Can tolerate restart duplicates | In-memory | Simpler |
| Cannot tolerate restart duplicates | Redis | State persists |
| Want alert persistence | Redis | State kept in Redis |

## In-Memory State Details

### How It Works

1. Alert received → State created in RAM
2. State refreshed on each alert receipt
3. State marked resolved when alert resolves
4. State deleted after TTL expires

### State Lifecycle

```
Time 00:00 - Alert: firing → State created in RAM
Time 00:30 - Alert: firing → State refreshed (TTL reset to 300s)
Time 01:00 - Alert: firing → State refreshed (TTL reset to 300s)
Time 01:30 - Alert: resolved → State marked resolved
Time 01:35 - Alert: firing → State updated to firing
Time 06:35 - State expires (TTL reached) → State deleted
```

### Memory Usage

Memory usage depends on:
- Number of active alerts
- Size of alert fingerprints
- TTL (longer TTL = more state in memory)

**Estimate:**
- Each state entry: ~100 bytes
- 10,000 active alerts: ~1 MB
- 100,000 active alerts: ~10 MB

### Restart Behavior

When Hermes restarts:
- All in-memory state is lost
- Active "firing" alerts may be resent
- This is expected behavior

**To minimize restart impact:**
- Reduce `deduplication_ttl` (alerts forgotten faster)
- Use Redis state (persists across restarts)

## Redis State Details

### Configuration

```yaml
# Config file
settings:
  deduplication_ttl: 300
  redis_url: "redis://redis:6379/0"  # Optional: can also use env var

# Or use environment variable
export REDIS_URL=redis://redis:6379/0
```

### Redis URL Format

```
redis://[username:password@]host:port/database
```

**Examples:**
```bash
# Basic
redis://redis:6379/0

# With authentication
redis://user:password@redis:6379/0

# With database number
redis://redis:6379/1

# Sentinel
redis+sentinel://sentinel:26379/mymaster/0

# Cluster
redis+cluster://node1:6379,node2:6379/0
```

### How It Works

1. Alert received → State created in Redis
2. State read/written to Redis on each alert
3. State marked resolved when alert resolves
4. State expires after TTL (Redis TTL)
5. State shared across all Hermes replicas

### State Lifecycle

```
Time 00:00 - Alert: firing → State written to Redis (TTL=300s)
Time 00:30 - Alert: firing → State updated in Redis (TTL refreshed)
Time 01:00 - Alert: firing → State updated in Redis (TTL refreshed)
Time 01:30 - Alert: resolved → State updated in Redis (status=resolved)
Time 01:35 - Alert: firing → State updated in Redis (status=firing)
Time 06:35 - Redis expires state (TTL reached) → State deleted
```

### Redis Commands Used

Hermes uses these Redis commands:
- `SET` - Create/update alert state
- `GET` - Read alert state
- `SETEX` - Set with TTL
- `DEL` - Delete state
- `TTL` - Check remaining TTL

**State key format:**
```
hermes:alert:{fingerprint}:{group}
```

**State value (JSON):**
```json
{
  "status": "firing",
  "last_updated": "2024-01-01T00:00:00Z"
}
```

### Performance Considerations

**Latency:**
- In-memory: ~0.1ms
- Redis: ~1-10ms (depending on network)

**Throughput:**
- In-memory: ~100k alerts/second
- Redis: ~10k-50k alerts/second (depending on Redis performance)

**Optimization:**
- Use Redis in same network as Hermes (same Kubernetes cluster)
- Use Redis Sentinel for HA
- Monitor Redis metrics (latency, memory, connections)

### Redis High Availability

**Single Redis Instance:**
- Simple setup
- Single point of failure
- Hermes continues if Redis down (uses in-memory fallback)

**Redis Sentinel:**
- Automatic failover
- Master-slave replication
- Slightly more complex

**Redis Cluster:**
- Horizontal scaling
- Automatic sharding
- Most complex

**Recommended:**
- Production: Redis Sentinel
- Large scale: Redis Cluster
- Small scale: Single instance (if you can tolerate brief outages)

### Fallback Behavior

When Redis is unavailable:

1. Hermes detects Redis unavailability
2. Falls back to in-memory state
3. Queues writes to replay queue
4. When Redis recovers, replays queued writes

**Circuit Breaker:**
- After 3 consecutive failures → OPEN state (stop trying Redis)
- After 60 seconds → HALF_OPEN state (test Redis)
- On success → CLOSED state (use Redis again)

**Replay Queue:**
- In-memory queue of writes
- Max size: 1000 (configurable)
- When full: oldest writes dropped
- When Redis recovers: replay all writes

## Migration: In-Memory to Redis

### Step 1: Deploy Redis

```bash
# Kubernetes (Helm)
helm install redis oci://ghcr.io/bitnami/redis --version 18.1.0 \
  --set architecture=standalone \
  --set auth.enabled=false
```

### Step 2: Update Hermes Deployment

```bash
# Add Redis URL environment variable
kubectl set env deployment/hermes REDIS_URL=redis://redis:6379/0

# Or update deployment yaml
env:
  - name: REDIS_URL
    value: "redis://redis:6379/0"
```

### Step 3: Rollout Restart

```bash
# Rollout Hermes pods
kubectl rollout restart deployment/hermes

# Verify
kubectl logs -l app=hermes --tail=50
```

### Step 4: Verify Redis Connection

```bash
# Check Hermes health
curl http://hermes:8080/health

# Expected response:
{
  "status": "ok",
  "config_loaded": true,
  "redis": "connected",
  "queue_size": 0
}
```

### Step 5: Monitor

```bash
# Check Redis metrics
curl http://hermes:9090/metrics | grep redis

# Expected:
spreader_redis_connected 1
spreader_redis_queue_size 0
```

## Monitoring

### Health Endpoint

```bash
curl http://hermes:8080/health
```

**Response:**
```json
{
  "status": "ok",
  "config_loaded": true,
  "redis": "connected",  # or "disconnected" or "not_configured"
  "queue_size": 0  # Replay queue size
}
```

### Metrics

```bash
curl http://hermes:9090/metrics | grep -E "(redis|queue)"
```

**Key metrics:**
- `spreader_redis_connected` - Redis connection status (0/1)
- `spreader_redis_queue_size` - Replay queue size
- `spreader_redis_write_attempts_total` - Total Redis write attempts
- `spreader_redis_write_failures_total` - Total Redis write failures

### Alerts

Prometheus alerts for Redis:

```yaml
- alert: HermesRedisDisconnected
  expr: spreader_redis_connected == 0
  for: 5m
  annotations:
    summary: "Hermes Redis is disconnected"

- alert: HermesRedisQueueBackingUp
  expr: spreader_redis_queue_size > 100
  for: 5m
  annotations:
    summary: "Hermes Redis replay queue is backing up"
```

## Best Practices

### 1. Use Redis for Multi-Replica

```bash
# ✅ Good: Multi-replica with Redis
kubectl scale deployment/hermes --replicas=3
export REDIS_URL=redis://redis:6379/0

# ❌ Bad: Multi-replica without Redis (duplicates)
kubectl scale deployment/hermes --replicas=3
# No REDIS_URL configured
```

### 2. Configure Redis Sentinel for Production

```bash
# ✅ Good: Sentinel for HA
export REDIS_URL=redis+sentinel://sentinel:26379/mymaster/0

# ❌ Bad: Single Redis in production
export REDIS_URL=redis://redis:6379/0
```

### 3. Monitor Redis Connection

```yaml
# Prometheus alert
- alert: HermesRedisDisconnected
  expr: spreader_redis_connected == 0
  for: 5m
```

### 4. Use Appropriate TTL

```yaml
# Development: Short TTL (state forgotten faster)
settings:
  deduplication_ttl: 60

# Production: Medium TTL
settings:
  deduplication_ttl: 300

# Long-running alerts: Longer TTL
settings:
  deduplication_ttl: 1800
```

### 5. Plan for Redis Outages

- Hermes continues if Redis down (uses in-memory)
- Monitor `queue_size` metric
- Alert on queue size > threshold
- Investigate Redis outages quickly

## Troubleshooting

### Hermes Can't Connect to Redis

**Check:**
```bash
# Verify Redis is running
kubectl get pods -l app=redis

# Check Redis logs
kubectl logs -l app=redis

# Test connectivity from Hermes pod
kubectl exec -it <hermes-pod> -- nc -zv redis 6379

# Check REDIS_URL
kubectl get deployment hermes -o yaml | grep REDIS_URL
```

**Solution:**
- Verify Redis service is accessible
- Check network policies
- Verify REDIS_URL format
- Check Redis logs for errors

### Queue Size Growing

**Check:**
```bash
curl http://hermes:8080/health
curl http://hermes:9090/metrics | grep queue_size
```

**Possible causes:**
- Redis is down or slow
- Network latency to Redis
- High alert volume

**Solution:**
- Check Redis health
- Increase Redis capacity
- Reduce alert volume
- Increase queue size (in config)

### Duplicates After Restart

**Check:**
```bash
# Check if Redis is configured
kubectl get deployment hermes -o yaml | grep REDIS_URL

# Check Redis connection
curl http://hermes:8080/health
```

**Possible causes:**
- Using in-memory state (no Redis)
- Redis not configured correctly
- Redis not connected

**Solution:**
- Configure REDIS_URL
- Verify Redis connection
- Check Redis logs

### High Memory Usage

**Check:**
```bash
kubectl top pods -l app=hermes

curl http://hermes:9090/metrics | grep active_alerts
```

**Possible causes:**
- Many active alerts
- Long TTL
- State not expiring

**Solution:**
- Reduce `deduplication_ttl`
- Check for stuck alerts
- Increase memory limits
- Review alert volume

## Next Steps

- [Deduplication](deduplication.md) - How deduplication works
- [Kubernetes Deployment](../README.md#kubernetes) - Deploy Hermes with Redis
- [Advanced Configuration Guide](../tutorials/advanced-routing.md) - Production configuration
- [Architecture](../architecture.md) - Complete system architecture
