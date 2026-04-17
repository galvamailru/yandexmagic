# YandexMagic Agent Operations

## Domain Execution Model

Each run executes exactly one action domain:

- `anomaly_watchdog`
- `budget_guard`
- `bid_optimization`
- `keyword_hygiene`
- `ad_rotation`
- `retargeting_tuning`

Protective domains run first in schedule and in priority chain.

## Default Schedule

- Every 2-4 hours: `anomaly_watchdog`, `budget_guard`
- Daily: `bid_optimization`, `keyword_hygiene`
- 3 times a week: `ad_rotation`
- Weekly: `retargeting_tuning`

Configured in `backend/app/celery_app.py`.

## Production Safety

- One domain per job run.
- Tenant conflict lock via `job_locks` (`tenant-domain-lock:<tenant_id>`).
- Global + domain limits (`agent_settings.max_changes_per_cycle` and `domain_settings.max_changes_per_run`).
- Idempotency via `idempotency_keys`.
- Dry-run mode support from `agent_settings.autopilot_dry_run`.
- Post-check with automatic rollback on severe KPI degradation.

## Operational SQL Checks

Inspect recent domain runs:

```sql
SELECT name, status, started_at, finished_at, details
FROM job_runs
WHERE name LIKE 'domain_cycle:%'
ORDER BY started_at DESC
LIMIT 50;
```

Inspect idempotency hits:

```sql
SELECT COUNT(*) FROM tenant_x.idempotency_keys;
```

## Rollout Recommendation

1. Enable all domains in dry-run mode first.
2. Compare previews with manual PPC decisions for 7-14 days.
3. Enable real execution only for `anomaly_watchdog` and `budget_guard`.
4. Gradually enable optimization domains with low limits.
