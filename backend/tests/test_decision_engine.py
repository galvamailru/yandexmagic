from app.services.decision_engine import (
    actions_for_bid_optimization,
    actions_for_budget_guard,
    actions_for_keyword_hygiene,
)


def test_keyword_hygiene_generates_suspend():
    rows = [{"Id": 11, "Ctr": 0.2, "Cost": 900.0, "Status": "ON", "Keyword": "cheap click"}]
    actions = actions_for_keyword_hygiene(
        campaign_local_id="c1",
        rows=rows,
        ctr_low_threshold=1.0,
        cost_threshold_rub=500.0,
    )
    assert len(actions) == 1
    assert actions[0].action_type == "suspend_keyword"
    assert actions[0].payload_after["status"] == "SUSPENDED"


def test_bid_optimization_supports_up_and_down():
    rows = [
        {"Id": 21, "Ctr": 8.0, "Bid": 40.0},
        {"Id": 22, "Ctr": 0.2, "Bid": 50.0},
    ]
    actions = actions_for_bid_optimization(
        campaign_local_id="c2",
        rows=rows,
        ctr_high_threshold=5.0,
        ctr_low_threshold=1.0,
        bid_up_factor=1.1,
    )
    kinds = {a.payload_after["keyword_id"]: a.payload_after["bid_rub"] for a in actions}
    assert kinds[21] > 40.0
    assert kinds[22] < 50.0


def test_budget_guard_emergency_suspend():
    actions = actions_for_budget_guard(
        campaign_local_id="c3",
        yandex_campaign_id=7001,
        name="x",
        spend_7d=12000.0,
        clicks_7d=0,
        hard_weekly_limit_rub=7000.0,
    )
    assert len(actions) == 1
    assert actions[0].action_type == "suspend_campaign"
