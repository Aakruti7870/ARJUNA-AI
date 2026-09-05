from app.preview import analyze_preview


def test_preview_detects_html_and_active_content():
    result = analyze_preview("<html><body><script>alert(1)</script><button onclick='x()'>Go</button></body></html>")
    assert result["kind"] == "html"
    assert result["riskScore"] >= 20
    assert result["riskLevel"] in {"medium", "high"}
    assert any(r["code"] == "script" for r in result["risks"])
    assert result["execution"] == "none"
    assert result["stored"] is False


def test_preview_extracts_fenced_json():
    result = analyze_preview('```json\n{"ok": true, "items": [1,2]}\n```')
    assert result["kind"] == "json"
    assert result["fenceLanguage"] == "json"
    assert result["completenessScore"] > 0
    assert any("Valid JSON object" in x for x in result["insights"])


def test_preview_fingerprint_changes_with_content():
    assert analyze_preview("alpha")["fingerprint"] != analyze_preview("beta")["fingerprint"]
