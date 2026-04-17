from app.services.domain_action_contracts import validate_domain_actions


def test_validate_bid_contract_accepts_valid_payload():
    actions = validate_domain_actions(
        "bid_optimization",
        [
            {
                "action_type": "set_bid",
                "entity": "keyword",
                "reason": "good ctr",
                "params": {"keyword_id": 11, "bid_rub": 42.5},
            }
        ],
    )
    assert len(actions) == 1
    assert actions[0]["params"]["keyword_id"] == 11


def test_validate_budget_contract_rejects_wrong_action():
    actions = validate_domain_actions(
        "budget_guard",
        [
            {
                "action_type": "set_bid",
                "entity": "keyword",
                "reason": "wrong domain action",
                "params": {"keyword_id": 11, "bid_rub": 42.5},
            }
        ],
    )
    assert actions == []
