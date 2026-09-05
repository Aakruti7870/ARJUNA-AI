from app.growth import condition_matches, recommend_automation, score_lead
from app.storage import Storage


def make_storage():
    return Storage("sqlite+pysqlite:///:memory:", "h" * 40, "v" * 40)


def test_high_intent_lead_scores_and_recommends_followup():
    lead = {"source": "meta lead ad", "name": "Buyer", "email": "b@example.com", "phone": "9999999999", "company": "Acme", "message": "Urgent: please send pricing, quote and arrange a demo today."}
    score, reasons, next_action = score_lead(lead)
    assert score >= 70
    assert next_action == "contact_now"
    lead["score"] = score
    actions = recommend_automation(lead)
    assert any(a["type"] == "create_followup" for a in actions)
    assert any(a["type"] == "set_lead_status" for a in actions)
    assert reasons


def test_condition_engine_supports_nested_values():
    assert condition_matches({"field": "lead.score", "op": "gte", "value": 70}, {"lead": {"score": 82}})
    assert not condition_matches({"field": "lead.score", "op": "gte", "value": 70}, {"lead": {"score": 25}})


def test_connector_credentials_are_encrypted_and_not_returned():
    s = make_storage()
    s.upsert_growth_connector(platform="meta_ads", account_label="Main", account_id="123", credentials={"access_token": "secret-value"}, config={"page_id": "p1"}, enabled=True)
    public = s.list_growth_connectors()[0]
    assert public["configured"] is True
    assert "credentials" not in public
    with s.engine.begin() as conn:
        row = conn.execute(s.growth_connectors.select()).fetchone()
        assert "secret-value" not in row.credentials_ciphertext


def test_proposal_share_token_is_one_way_and_expiring():
    s = make_storage()
    proposal, token = s.create_proposal({"lead_id": None, "title": "Offer", "body": "Terms", "amount": 1000, "currency": "INR", "expires_in_days": 7})
    assert token.startswith("apr_")
    assert "share_hash" not in proposal
    shared = s.shared_proposal(token)
    assert shared and shared["title"] == "Offer"
    assert s.shared_proposal(token + "x") is None


def test_automation_and_outbox_lifecycle():
    s = make_storage()
    rule = s.create_automation({"name": "Hot lead", "trigger_event": "lead.created", "condition": {"field": "lead.score", "op": "gte", "value": 70}, "actions": [{"type": "notify"}], "enabled": True})
    assert s.list_automations("lead.created")[0]["id"] == rule["id"]
    queued = s.enqueue_outbox(kind="notify", channel="internal", recipient=None, payload={"lead_id": "x"})
    assert queued["status"] == "queued"
    assert s.list_outbox()[0]["id"] == queued["id"]
