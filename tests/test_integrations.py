from app.growth import PLATFORM_CATALOG, catalog


def test_global_catalog_contains_major_integration_families():
    required = {
        "github", "gmail", "google_calendar", "google_drive", "slack", "notion",
        "dropbox", "salesforce", "hubspot", "stripe", "shopify", "zapier", "n8n",
        "postgresql", "mongodb", "mcp_streamable_http", "mcp_sse", "mcp_stdio",
        "plugin_openapi", "plugin_custom", "rest_api", "webhook",
    }
    assert required.issubset(PLATFORM_CATALOG)


def test_catalog_exposes_category_kind_auth_and_capabilities():
    items = catalog()
    assert len(items) >= 40
    for item in items:
        assert item["id"]
        assert item["label"]
        assert item["category"]
        assert item["kind"] in {"integration", "plugin", "mcp"}
        assert item["auth"]
        assert isinstance(item["capabilities"], list)


def test_mcp_entries_are_explicitly_typed():
    assert PLATFORM_CATALOG["mcp_streamable_http"]["kind"] == "mcp"
    assert PLATFORM_CATALOG["mcp_sse"]["kind"] == "mcp"
    assert PLATFORM_CATALOG["mcp_stdio"]["kind"] == "mcp"
    assert PLATFORM_CATALOG["plugin_openapi"]["kind"] == "plugin"
