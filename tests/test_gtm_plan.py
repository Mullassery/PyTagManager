"""Tests for the GTM import planner (dry run)."""

from pytagmanager.analytics_api.gtm_plan import plan_import, render_plan


def test_plan_reports_added_existing_and_conflicts():
    generated = {
        "containerVersion": {
            "tag": [
                {"name": "GA4 Purchase", "type": "gaawe"},
                {"name": "Meta Pixel", "type": "html"},
            ],
            "trigger": [{"name": "Purchase", "type": "CUSTOM_EVENT"}],
            "variable": [{"name": "DLV - price", "type": "v"}],
        }
    }
    live = {
        "containerVersion": {
            "tag": [{"name": "GA4 Purchase", "type": "gaawe"}],
            "trigger": [{"name": "Purchase", "type": "PAGEVIEW"}],
            "variable": [],
        }
    }

    plan = plan_import(generated, live)
    assert [t["name"] for t in plan.tags.added] == ["Meta Pixel"]
    assert [t["name"] for t in plan.tags.existing] == ["GA4 Purchase"]
    assert plan.triggers.conflicts[0]["name"] == "Purchase"
    assert plan.variables.added[0]["name"] == "DLV - price"
    assert plan.has_conflicts


def test_plan_with_no_conflicts_renders_cleanly():
    doc = {"containerVersion": {"tag": [], "trigger": [], "variable": []}}
    plan = plan_import(doc, doc)
    assert not plan.has_conflicts
    text = render_plan(plan)
    assert "0 add" in text
    assert "Resolve conflicts" not in text
