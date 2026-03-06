# Troubleshooting Guide

## Common Issues

### 1. Hermes Won't Start

**Symptoms:** Pod crashes on startup

**Check:**
```bash
kubectl logs -l app=hermes --previous
```

**Common causes:**

| Error | Cause | Solution |
|-------|-------|----------|
| `Config not found` | ConfigMap missing | Apply ConfigMap: `kubectl apply -f k8s/base/configmap.yaml` |
| `Redis connection failed` | Redis unavailable | Check Redis service: `kubectl get svc redis` |
| `Permission denied` | Volume permissions | Check if /data is writable |

### 2. Redis Connection Issues

**Symptoms:** High replay queue size, alerts being queued

**Check:**
```bash
# Check Redis health
kubectl exec -it <redis-pod> -- redis-cli ping

# Check Hermes Redis status
curl http://hermes:8080/health
```

**Solutions:**

1. **Redis not running:**
   ```bash
   kubectl get pods -l app=redis
   kubectl describe pod <redis-pod>
   ```

2. **Network connectivity:**
   ```bash
   kubectl exec -it <hermes-pod> -- nc -zv redis 6379
   ```

3. **Wrong URL:**
   - Check `REDIS_URL` environment variable
   - Verify secret exists: `kubectl get secret hermes-secrets`

### 3. Alerts Not Being Sent

**Symptoms:** Webhooks received but no notifications

**Debug steps:**

1. Check if alerts match any groups:
   ```bash
   # Send test alert
   curl -X POST http://hermes:8080/webhook \
     -H "Content-Type: application/json" \
     -d '{"alerts":[{"status":"firing","labels":{"namespace":"test"},"startsAt":"2024-01-01T00:00:00Z"}]}'
   
   # Check response for matched groups
   ```

2. Verify destination configuration:
   ```bash
   curl http://hermes:8080/destinations
   ```

3. Check webhook URLs:
   ```bash
   kubectl get secret hermes-secrets -o yaml
   ```

4. Test webhook manually:
   ```bash
   curl -X POST "$WEBHOOK_URL" \
     -H "Content-Type: application/json" \
     -d '{"text":"test"}'
   ```

### 4. Duplicate Alerts

**Symptoms:** Same alert sent multiple times

**Check:**
```bash
# Check metrics for deduplication
curl http://hermes:9090/metrics | grep deduplicated
```

**Possible causes:**

1. **Multiple replicas with no Redis:**
   - Ensure Redis is configured
   - Or run with single replica

2. **Fingerprint mismatch:**
   - Check fingerprint strategy
   - Ensure labels are consistent

3. **TTL too short:**
   ```yaml
   settings:
     deduplication_ttl: 300  # Increase if needed
   ```

### 5. Config Changes Not Applied

**Symptoms:** Config reloaded but behavior unchanged

**Check:**
```bash
# View config reload metrics
curl http://hermes:9090/metrics | grep config_reload
```

**Solutions:**

1. **Validation failed:**
    - Check logs for validation errors
    - Ensure YAML syntax is correct

2. **Reload check disabled:**
    ```bash
    # Check ENABLE_RELOAD_CHECK env var
    kubectl describe deployment hermes | grep ENABLE_RELOAD_CHECK
    ```

3. **Reload check disabled:**
    - Check if `ENABLE_RELOAD_CHECK=false`
    - Set to `true` to enable periodic checks

4. **Interval too long:**
    - Reduce `CONFIG_RELOAD_INTERVAL` for faster reloads (default: 30s)
    - Example: `CONFIG_RELOAD_INTERVAL=10` checks every 10 seconds

### 6. High Memory Usage

**Symptoms:** OOMKilled or high memory

**Debug:**
```bash
# Check active alerts
curl http://hermes:9090/metrics | grep active_alerts

# Check queue size
curl http://hermes:8080/health
```

**Solutions:**

1. **Reduce TTL:**
   ```yaml
   settings:
     deduplication_ttl: 180  # Reduce from default 300
   ```

2. **Limit queue size:**
   ```yaml
   settings:
     replay_queue_size: 500  # Reduce from default 1000
   ```

3. **Increase memory limit:**
   ```yaml
   resources:
     limits:
       memory: "512Mi"
   ```

## Debug Mode

Enable verbose logging:

```bash
kubectl set env deployment/hermes LOG_LEVEL=DEBUG
```

Or in deployment:
```yaml
env:
  - name: LOG_LEVEL
    value: "DEBUG"
```

## Health Check Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/health` | Liveness | Basic health status |
| `/ready` | Readiness | Ready to receive traffic |
| `/state` | State info | Queue size, active alerts |
| `/destinations` | Destinations | List of configured destinations |
| `/metrics` | Prometheus | All metrics |

## Useful Commands

```bash
# View all Hermes logs
kubectl logs -l app=hermes -f --tail=100

# Check events
kubectl get events --field-selector involvedObject.name=hermes

# Port forward for local debugging
kubectl port-forward svc/hermes 8080:80

# Check resource usage
kubectl top pods -l app=hermes

# Execute into pod
kubectl exec -it <hermes-pod> -- /bin/sh
```

## Metrics Reference

Key metrics to monitor:

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `spreader_alerts_received_total` | Total alerts received | - |
| `spreader_alerts_deduplicated_total` | Deduplicated alerts | High = working correctly |
| `spreader_redis_queue_size` | Replay queue size | > 100 = Redis issues |
| `spreader_redis_connected` | Redis connection | 0 = disconnected |
| `spreader_send_attempts_total{status="failure"}` | Failed sends | Increasing = webhook issues |