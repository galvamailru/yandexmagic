import asyncio
import types
import uuid

from app.services.agent_domains import AgentAction, DOMAIN_BID_OPTIMIZATION
from app.services import agent_runner as ar


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDB:
    def __init__(self, lock_row=("ok",)):
        self.lock_row = lock_row
        self.executed = 0

    def execute(self, *_args, **_kwargs):
        self.executed += 1
        return _FakeResult(self.lock_row)

    def commit(self):
        return None


def test_apply_action_respects_idempotency(monkeypatch):
    db = _FakeDB()
    tenant = types.SimpleNamespace(schema_name="tenant_x", name="x")
    action = AgentAction(
        domain="keyword_hygiene",
        action_type="suspend_keyword",
        campaign_local_id=str(uuid.uuid4()),
        payload_before={"keyword_id": 1, "status": "ON"},
        payload_after={"keyword_id": 1, "status": "SUSPENDED"},
        idempotency_key="k1",
    )

    monkeypatch.setattr(ar.tq, "mark_idempotency_seen", lambda *_a, **_k: False)
    called = {"hist": 0}
    monkeypatch.setattr(ar.tq, "insert_action_history", lambda *_a, **_k: called.__setitem__("hist", called["hist"] + 1))
    monkeypatch.setattr(ar.tq, "insert_agent_log", lambda *_a, **_k: None)

    ok = asyncio.run(ar._apply_action(db, tenant, "tkn", None, action, dry_run=False))
    assert ok is False
    assert called["hist"] == 0


def test_run_domain_conflict_lock(monkeypatch):
    db = _FakeDB(lock_row=None)
    tenant = types.SimpleNamespace(id=uuid.uuid4(), is_blocked=False, schema_name="tenant_x", name="x")

    async def _token(*_a, **_k):
        return "token"

    monkeypatch.setattr(ar, "ensure_valid_access_token", _token)
    out = asyncio.run(ar.run_domain_for_tenant(db, tenant, domain=DOMAIN_BID_OPTIMIZATION))
    assert out == 0


def test_run_domain_triggers_rollback(monkeypatch):
    db = _FakeDB(lock_row=("locked",))
    local_id = uuid.uuid4()
    tenant = types.SimpleNamespace(id=uuid.uuid4(), is_blocked=False, schema_name="tenant_x", name="x")

    async def _token(*_a, **_k):
        return "token"

    monkeypatch.setattr(ar, "ensure_valid_access_token", _token)
    monkeypatch.setattr(ar, "get_client_login_for_tenant", lambda *_a, **_k: None)
    monkeypatch.setattr(
        ar.tq,
        "get_agent_settings",
        lambda *_a, **_k: {
            "ctr_low_threshold": 1.0,
            "ctr_high_threshold": 5.0,
            "cost_threshold_rub": 500.0,
            "bid_up_factor": 1.1,
            "autopilot_dry_run": False,
            "max_changes_per_cycle": 5,
        },
    )
    monkeypatch.setattr(ar.tq, "list_all_campaign_modes", lambda *_a, **_k: [(local_id, "autopilot", 1001)])
    monkeypatch.setattr(
        ar.tq,
        "get_domain_settings",
        lambda *_a, **_k: {
            "domain": DOMAIN_BID_OPTIMIZATION,
            "enabled": True,
            "max_changes_per_run": 5,
            "hard_weekly_limit_rub": 0.0,
            "schedule_hint": "daily",
        },
    )
    async def _kw(*_a, **_k):
        return [{"CampaignId": 1001, "Id": 777, "Bid": 40, "Ctr": 6.0}]

    monkeypatch.setattr(ar.yandex_direct, "keyword_performance_rows", _kw)
    monkeypatch.setattr(
        ar,
        "actions_for_bid_optimization",
        lambda **_k: [
            AgentAction(
                domain=DOMAIN_BID_OPTIMIZATION,
                action_type="set_bid",
                campaign_local_id=str(local_id),
                payload_before={"keyword_id": 777, "bid_rub": 40},
                payload_after={"keyword_id": 777, "bid_rub": 44},
                idempotency_key="x",
            )
        ],
    )
    async def _apply(*_a, **_k):
        return True

    monkeypatch.setattr(ar, "_apply_action", _apply)
    monkeypatch.setattr(
        ar.tq,
        "recent_campaign_stats",
        lambda *_a, **_k: [
            {"cost_rub": 1000.0, "ctr": 0.1, "clicks": 1},
            {"cost_rub": 400.0, "ctr": 1.0, "clicks": 10},
        ],
    )
    monkeypatch.setattr(
        ar.tq,
        "recent_action_history",
        lambda *_a, **_k: [{"action_type": "set_bid", "payload_before": {"keyword_id": 777, "bid_rub": 40}, "id": str(uuid.uuid4())}],
    )
    monkeypatch.setattr(ar.tq, "insert_agent_log", lambda *_a, **_k: None)
    called = {"rollback": 0}

    async def _set_bids(*_a, **_k):
        called["rollback"] += 1
        return True

    monkeypatch.setattr(ar.yandex_direct, "keywords_set_bids", _set_bids)
    monkeypatch.setattr(ar, "send_alert", _token)

    applied = asyncio.run(ar.run_domain_for_tenant(db, tenant, domain=DOMAIN_BID_OPTIMIZATION))
    assert applied == 1
    assert called["rollback"] == 1
