from __future__ import annotations

import json

import click

from pytagmanager.discovery.crawl import crawl_site
from pytagmanager.export.base import EXPORTERS
from pytagmanager.intent.ollama_classifier import DEFAULT_OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL, OllamaIntentClassifier
from pytagmanager.recommend.heuristics import recommend_for_graph
from pytagmanager.version_control.diff import diff_snapshots, format_diff_report
from pytagmanager.version_control.snapshot import build_snapshot, load_snapshot, save_snapshot


@click.group()
def main() -> None:
    """PyTagManager: AI-native analytics implementation platform (v1: crawl -> DOM graph -> recommend -> export)."""


def _parse_headers(raw_headers: tuple[str, ...]) -> list[tuple[str, str]]:
    """Parse repeated `--header 'Name: Value'` CLI options into (name, value) pairs."""
    parsed = []
    for raw in raw_headers:
        if ":" not in raw:
            raise click.UsageError(f"--header must be in 'Name: Value' format, got: {raw!r}")
        name, _, value = raw.partition(":")
        parsed.append((name.strip(), value.strip()))
    return parsed


@main.command()
@click.argument("url")
@click.option("--max-pages", default=50, show_default=True, type=int)
@click.option("--concurrency", default=10, show_default=True, type=int)
@click.option("--no-robots", is_flag=True, help="Ignore robots.txt")
@click.option(
    "--rate-limit",
    "rate_limit",
    type=float,
    default=None,
    help="Max requests/second. Recommended when crawling a production site you don't control, to avoid tripping a WAF or getting blocked mid-crawl. Unset = no throttling.",
)
@click.option(
    "--header",
    "raw_headers",
    multiple=True,
    metavar="NAME: VALUE",
    help="Custom request header, e.g. for an authenticated crawl. Repeatable. Format: 'Cookie: session=abc123'.",
)
@click.option("--export", "export_format", type=click.Choice(sorted(EXPORTERS)), default=None)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option(
    "--save-snapshot",
    "snapshot_path",
    type=click.Path(),
    default=None,
    help="Save this crawl (pages, DOM elements, recommendations) as a JSON snapshot for later `pytagmanager diff`.",
)
@click.option(
    "--intent",
    "intent_engine",
    type=click.Choice(["heuristic", "ollama"]),
    default="heuristic",
    show_default=True,
    help="Business-intent classification engine. 'ollama' uses a locally running Ollama model "
    "(falls back to the heuristic automatically if Ollama isn't reachable).",
)
@click.option(
    "--ollama-model",
    default=DEFAULT_OLLAMA_MODEL,
    show_default=True,
    help="Ollama model to use when --intent=ollama.",
)
@click.option(
    "--ollama-url",
    default=DEFAULT_OLLAMA_BASE_URL,
    show_default=True,
    help="Ollama base URL to use when --intent=ollama.",
)
def crawl(
    url: str,
    max_pages: int,
    concurrency: int,
    no_robots: bool,
    rate_limit: float | None,
    raw_headers: tuple[str, ...],
    export_format: str | None,
    output_path: str | None,
    snapshot_path: str | None,
    intent_engine: str,
    ollama_model: str,
    ollama_url: str,
) -> None:
    """Crawl URL, generate tracking recommendations, and optionally export them."""
    headers = _parse_headers(raw_headers)
    classifier = OllamaIntentClassifier(model=ollama_model, base_url=ollama_url) if intent_engine == "ollama" else None
    click.echo(f"Crawling {url} (max_pages={max_pages}, concurrency={concurrency})...")
    pages = crawl_site(
        url,
        max_pages=max_pages,
        concurrency=concurrency,
        respect_robots=not no_robots,
        rate_limit=rate_limit,
        headers=headers,
    )
    click.echo(f"Crawled {len(pages)} page(s).")

    all_recs = []
    recs_by_url = {}
    for page in pages:
        recs = recommend_for_graph(page.graph, classifier=classifier)
        all_recs.extend(recs)
        recs_by_url[page.url] = recs
        click.echo(f"  {page.url} [{page.status}] -> {len(recs)} recommendation(s)")

    click.echo(f"\nTotal recommendations: {len(all_recs)}")
    for rec in all_recs[:20]:
        click.echo(f"  - {rec.event_name} ({rec.business_objective}, confidence={rec.confidence}) via {rec.selector}")
    if len(all_recs) > 20:
        click.echo(f"  ... and {len(all_recs) - 20} more")

    if export_format is not None:
        spec = EXPORTERS[export_format]
        config = spec.build(all_recs)
        if output_path:
            with open(output_path, "w") as f:
                json.dump(config, f, indent=2)
            click.echo(f"\nExported {spec.label} to {output_path}")
        else:
            click.echo(json.dumps(config, indent=2))

    if snapshot_path:
        snapshot = build_snapshot(pages, recs_by_url, root_url=url)
        save_snapshot(snapshot, snapshot_path)
        click.echo(f"\nSaved crawl snapshot to {snapshot_path}")


@main.command()
@click.argument("old_snapshot_path", type=click.Path(exists=True))
@click.argument("new_snapshot_path", type=click.Path(exists=True))
def diff(old_snapshot_path: str, new_snapshot_path: str) -> None:
    """Compare two saved crawl snapshots (`crawl --save-snapshot`) and report
    added/removed/changed pages, DOM elements, and recommendations."""
    old = load_snapshot(old_snapshot_path)
    new = load_snapshot(new_snapshot_path)
    report = diff_snapshots(old, new)
    click.echo(format_diff_report(report))


@main.command(name="dictionary")
@click.argument("url")
@click.option("--max-pages", default=20, show_default=True, type=int)
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option("--browser", type=click.Choice(["chromium", "firefox", "webkit"]), default="chromium", show_default=True)
@click.option(
    "--capture-storage-values",
    "capture_storage_values",
    is_flag=True,
    help="Capture raw cookie/localStorage/sessionStorage values, not just key names/types. Off by default -- see `diagnose --help`'s equivalent flag for the privacy rationale.",
)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option(
    "--presence-labels",
    "include_presence",
    is_flag=True,
    help="Label each variable's Exists/Exposed/Accessible presence-vs-availability status (docs/VISION.md §4).",
)
@click.option(
    "--purpose-classifier",
    "purpose_engine",
    type=click.Choice(["none", "heuristic", "ollama"]),
    default="none",
    show_default=True,
    help="Classify each cookie/localStorage/sessionStorage variable's likely purpose (docs/VISION.md §6). "
    "'ollama' uses a locally running Ollama model, falling back to the heuristic automatically if unreachable.",
)
@click.option(
    "--compare-to",
    "compare_to_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to a previously saved `dictionary --format json -o old.json` export. Instead of the normal "
    "report, prints a schema-drift report (added/removed fields, type-distribution shifts, possible renames).",
)
def data_dictionary(
    url: str,
    max_pages: int,
    headless: bool,
    browser: str,
    capture_storage_values: bool,
    output_path: str | None,
    output_format: str,
    include_presence: bool,
    purpose_engine: str,
    compare_to_path: str | None,
) -> None:
    """Crawl URL and build a Website Data Dictionary (docs/VISION.md §3):
    every cookie/localStorage/sessionStorage key and dataLayer field
    observed across the crawl, where, and how often. Requires
    `pip install pytagmanager[diagnostics]`.
    """
    from pytagmanager.dictionary.build import build_data_dictionary, data_dictionary_from_json
    from pytagmanager.dictionary.purpose import HeuristicPurposeClassifier, OllamaPurposeClassifier
    from pytagmanager.dictionary.report import build_dictionary_json, render_dictionary_report
    from pytagmanager.dictionary.schema_drift import build_drift_json, diff_dictionaries, render_drift_report
    from pytagmanager.observability.scenario import auto_scenario_from_recommendations
    from pytagmanager.observability.session import ObservationSession

    click.echo(f"Crawling {url} (max_pages={max_pages})...", err=True)
    pages = crawl_site(url, max_pages=max_pages)
    click.echo(f"Crawled {len(pages)} page(s).", err=True)

    snapshots = []
    for page in pages:
        recs = recommend_for_graph(page.graph)
        scenarios = auto_scenario_from_recommendations(recs, page.url)
        with ObservationSession(
            headless=headless, browser_name=browser, capture_storage_values=capture_storage_values
        ) as session:
            session.load(page.url)
            for scenario in scenarios:
                session.run_scenario(scenario)
                session.wait(1.0)
            snapshots.extend(session.state_snapshots)

    result = build_data_dictionary(snapshots)

    if compare_to_path:
        with open(compare_to_path) as f:
            baseline = data_dictionary_from_json(json.load(f))
        drift = diff_dictionaries(baseline, result)
        if output_format == "json":
            report = json.dumps(build_drift_json(drift), indent=2)
        else:
            report = render_drift_report(drift)
        if output_path:
            with open(output_path, "w") as f:
                f.write(report)
            click.echo(f"Wrote schema drift report to {output_path}")
        else:
            click.echo(report)
        return

    purpose_by_key = None
    if purpose_engine != "none":
        classifier = OllamaPurposeClassifier() if purpose_engine == "ollama" else HeuristicPurposeClassifier()
        purpose_by_key = {
            (v.source, v.path): classifier.classify(v)
            for v in result.variables
            if v.source in ("cookie", "local_storage", "session_storage")
        }

    if output_format == "json":
        report = json.dumps(
            build_dictionary_json(result, purpose_by_key=purpose_by_key, include_presence=include_presence),
            indent=2,
        )
    else:
        report = render_dictionary_report(result, purpose_by_key=purpose_by_key, include_presence=include_presence)

    if output_path:
        with open(output_path, "w") as f:
            f.write(report)
        click.echo(f"Wrote data dictionary to {output_path}")
    else:
        click.echo(report)


@main.command()
@click.argument("url")
@click.option("--max-pages", default=20, show_default=True, type=int)
@click.option(
    "--scenario",
    "scenario_path",
    type=click.Path(exists=True),
    default=None,
    help="Hand-authored journey YAML (spec section 12 format). Overrides auto-discovery and tests only URL itself.",
)
@click.option("--gtm-container", default=None, help="GTM public container ID (GTM-XXXXXXX) to cross-check runtime events against.")
@click.option("--gtm-credentials", type=click.Path(exists=True), default=None, help="Service-account JSON key for the GTM Management API.")
@click.option("--ga4-property", default=None, help="GA4 property ID to cross-check config/ingestion against.")
@click.option("--ga4-credentials", type=click.Path(exists=True), default=None, help="Service-account JSON key for the GA4 Admin/Data APIs.")
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option("--browser", type=click.Choice(["chromium", "firefox", "webkit"]), default="chromium", show_default=True)
@click.option(
    "--duration",
    default=2.0,
    show_default=True,
    type=float,
    help="Seconds to wait after each interaction for downstream dataLayer/GTM/network effects to settle.",
)
@click.option("--window", "correlation_window", default=5.0, show_default=True, type=float, help="Correlation window in seconds after an interaction.")
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--verbose", is_flag=True)
@click.option(
    "--site-wide",
    "site_wide",
    is_flag=True,
    help="Group crawled pages into templates and report cross-page consistency + a site health matrix instead of one report per journey. Requires crawling (incompatible with --scenario).",
)
@click.option(
    "--semantic-labels",
    "semantic_labels",
    is_flag=True,
    help="Relabel --site-wide templates using a local Ollama model's page-type classification instead of the URL-segment heuristic (falls back to the heuristic automatically if Ollama isn't running).",
)
@click.option(
    "--history",
    "history_path",
    type=click.Path(),
    default=None,
    help="Append this --site-wide run's health score to a JSON history file and check for a regression vs. the previous run.",
)
@click.option(
    "--alert-webhook",
    "alert_webhook",
    default=None,
    help="POST a message to this webhook URL (e.g. a Slack incoming webhook) if --history detects a regression.",
)
@click.option(
    "--alert-threshold",
    "alert_threshold",
    default=5,
    show_default=True,
    type=int,
    help="Minimum point drop in overall or template health score (vs. the previous --history run) to trigger a regression alert.",
)
@click.option(
    "--capture-storage-values",
    "capture_storage_values",
    is_flag=True,
    help="Capture raw cookie/localStorage/sessionStorage values, not just key names/types/lengths. Off by default: these are live session/credential state, a more sensitive class of data than a dataLayer payload. Values for keys that look sensitive (session/token/auth/csrf/...) are still redacted even with this on.",
)
@click.option(
    "--trace",
    "include_trace",
    is_flag=True,
    help="Include a formalized, drillable Interaction Trace per journey (docs/VISION.md §14): "
    "Finding -> Interaction -> Element -> Timestamp -> JS/dataLayer/GTM/network events -> storage change.",
)
@click.option(
    "--track-scroll-depth",
    "track_scroll_depth",
    is_flag=True,
    help="Treat 25/50/75/90/100% scroll-depth milestones as first-class interactions (docs/VISION.md §14), "
    "each becoming its own journey checked for scroll/dataLayer/GTM/network signals.",
)
@click.option(
    "--detect-duplicate-tags",
    "detect_duplicate_tags",
    is_flag=True,
    help="Flag duplicate/conflicting tag implementations (docs/VISION.md §17): static candidates (multiple "
    "GTM containers, GTM + a hard-coded vendor equivalent, a vendor wired in twice) escalated to a finding "
    "only when a business interaction's network requests corroborate duplicate firing at runtime.",
)
@click.option(
    "--detect-server-side-tagging",
    "detect_server_side_tagging",
    is_flag=True,
    help="Flag hedged server-side GTM/tagging indicators (docs/VISION.md §17): first-party requests shaped "
    "like a GA4 Measurement Protocol hit, and a single interaction fanning out to multiple external vendor "
    "hosts. Every indicator is worded as a possibility ('Likely'/'Possible'), never a confirmed fact -- "
    "server-side relaying isn't observable from the browser.",
)
def diagnose(
    url: str,
    max_pages: int,
    scenario_path: str | None,
    gtm_container: str | None,
    gtm_credentials: str | None,
    ga4_property: str | None,
    ga4_credentials: str | None,
    headless: bool,
    browser: str,
    duration: float,
    correlation_window: float,
    output_path: str | None,
    output_format: str,
    verbose: bool,
    site_wide: bool,
    semantic_labels: bool,
    history_path: str | None,
    alert_webhook: str | None,
    alert_threshold: int,
    capture_storage_values: bool,
    include_trace: bool,
    track_scroll_depth: bool,
    detect_duplicate_tags: bool,
    detect_server_side_tagging: bool,
) -> None:
    """Drive a real browser through URL (or a crawl of it), observe the full
    interaction -> dataLayer -> GTM -> GA4 tracking chain, and diagnose
    where and why it broke. Requires `pip install pytagmanager[diagnostics]`.
    """
    if scenario_path and site_wide:
        raise click.UsageError("--site-wide requires crawling the site; it cannot be combined with --scenario.")
    if history_path and not site_wide:
        raise click.UsageError("--history requires --site-wide (health scores are a site-wide concept).")
    if alert_webhook and not history_path:
        raise click.UsageError("--alert-webhook requires --history (there must be a previous run to compare against).")
    from pytagmanager.analytics_api.ga4_client import Ga4ApiClient
    from pytagmanager.analytics_api.gtm_client import GtmApiClient
    from pytagmanager.correlation.journey import correlate_events
    from pytagmanager.diagnostics.rules import DiagnosticContext, find_duplicate_purchases, find_untested_recommendations
    from pytagmanager.diagnostics.trace import (
        build_interaction_trace_json,
        build_interaction_traces,
        render_interaction_trace,
    )
    from pytagmanager.observability.scenario import auto_scenario_from_recommendations, load_scenario
    from pytagmanager.observability.session import ObservationSession
    from pytagmanager.reporting.json_report import build_json_report
    from pytagmanager.reporting.terminal import diagnose_journeys, render_terminal_report
    from pytagmanager.tagexec.duplicates import analyze_duplicates
    from pytagmanager.tagexec.report import (
        build_duplicate_findings_json,
        build_server_side_indicators_json,
        render_duplicate_findings,
        render_server_side_indicators,
    )
    from pytagmanager.tagexec.server_side import analyze_server_side_indicators
    from pytagmanager.tagexec.static_scan import scan_html

    gtm_triggers = gtm_tags = None
    if gtm_container and gtm_credentials:
        client = GtmApiClient.from_service_account(gtm_credentials)
        container = client.find_container_by_public_id(gtm_container)
        if container is None:
            click.echo(f"Warning: GTM container {gtm_container} not found for the given credentials.", err=True)
        else:
            config = client.get_live_container_config(container["path"])
            gtm_triggers, gtm_tags = config["triggers"], config["tags"]

    ga4_client = Ga4ApiClient.from_service_account(ga4_credentials) if (ga4_property and ga4_credentials) else None

    if scenario_path:
        scenario = load_scenario(scenario_path)
        pages_and_scenarios = [(url, [scenario], [])]
    else:
        click.echo(f"Crawling {url} (max_pages={max_pages})...", err=True)
        pages = crawl_site(url, max_pages=max_pages)
        click.echo(f"Crawled {len(pages)} page(s).", err=True)
        pages_and_scenarios = []
        for page in pages:
            recs = recommend_for_graph(page.graph)
            pages_and_scenarios.append((page.url, auto_scenario_from_recommendations(recs, page.url), recs))

    all_journeys = []
    all_untested = []
    all_state_diffs = []
    all_duplicate_findings = []
    all_server_side_indicators = []
    expectations_by_selector: dict = {}
    needs_page_traces = detect_duplicate_tags or detect_server_side_tagging

    for page_url, scenarios, recs in pages_and_scenarios:
        with ObservationSession(
            headless=headless,
            browser_name=browser,
            capture_storage_values=capture_storage_values,
            track_scroll_depth=track_scroll_depth,
        ) as session:
            session.load(page_url)
            for scenario in scenarios:
                if scenario.steps:
                    expectations_by_selector[scenario.steps[-1].selector] = scenario.expectations
                session.run_scenario(scenario)
                session.wait(duration)
            events = session.events
            all_state_diffs.extend(session.state_diffs)
            page_html = session.capture_html() if detect_duplicate_tags else None
        journeys = correlate_events(events, window_seconds=correlation_window)
        all_journeys.extend(journeys)
        if recs:
            all_untested.extend(find_untested_recommendations(recs, journeys))
        page_traces = build_interaction_traces(journeys) if needs_page_traces else []
        if detect_duplicate_tags and page_html is not None:
            page_scan = scan_html(page_html, page_url)
            all_duplicate_findings.extend(analyze_duplicates(page_scan, page_traces))
        if detect_server_side_tagging:
            all_server_side_indicators.extend(analyze_server_side_indicators(page_traces))

    ga4_ingestion: dict = {}
    if ga4_client and ga4_property:
        for event_name in {j.business_event for j in all_journeys}:
            ga4_ingestion[event_name] = ga4_client.was_event_ingested_realtime(ga4_property, event_name)

    ctx = DiagnosticContext(
        expectations_by_selector=expectations_by_selector,
        gtm_triggers=gtm_triggers,
        gtm_tags=gtm_tags,
        ga4_ingestion=ga4_ingestion,
        state_diffs=all_state_diffs,
    )
    diagnosed = diagnose_journeys(all_journeys, ctx)

    traces = []
    if include_trace:
        state_diffs_by_journey_id = {}
        for journey in diagnosed:
            diff = ctx.state_diff_for_journey(journey)
            if diff is not None:
                state_diffs_by_journey_id[journey.journey_id] = diff
        traces = build_interaction_traces(diagnosed, state_diffs_by_journey_id)

    if site_wide:
        from pytagmanager.sitewide.aggregation import analyze_template_consistency, compute_site_health
        from pytagmanager.sitewide.anomalies import detect_site_anomalies
        from pytagmanager.sitewide.event_map import build_runtime_event_map
        from pytagmanager.sitewide.interaction_consistency import analyze_business_action_consistency
        from pytagmanager.sitewide.report import build_site_health_json, render_site_health_report
        from pytagmanager.sitewide.templates import detect_templates

        journeys_by_page: dict = {}
        for journey in diagnosed:
            page_url = journey.observations[0].page_url if journey.observations else None
            if page_url:
                journeys_by_page.setdefault(page_url, []).append(journey)

        untested_by_page: dict = {}
        for rec in all_untested:
            untested_by_page.setdefault(rec.page_url, []).append(rec)

        recs_by_page = {page_url: recs for page_url, _scenarios, recs in pages_and_scenarios}

        templates = detect_templates(pages)
        if semantic_labels:
            from pytagmanager.sitewide.page_type import OllamaPageTypeClassifier, assign_semantic_labels

            graphs_by_url = {page.url: page.graph for page in pages}
            templates = assign_semantic_labels(templates, graphs_by_url, OllamaPageTypeClassifier())

        site_health = compute_site_health(templates, journeys_by_page, untested_by_page)
        consistency_reports = [analyze_template_consistency(t, journeys_by_page) for t in templates]
        anomalies = detect_site_anomalies(templates, journeys_by_page)
        business_action_reports = analyze_business_action_consistency(recs_by_page, diagnosed)
        event_map = build_runtime_event_map(diagnosed)

        regression = None
        if history_path:
            from pytagmanager.sitewide.history import (
                HealthHistoryEntry,
                append_history_entry,
                detect_regression,
                load_history,
            )

            history = load_history(history_path)
            entry = HealthHistoryEntry.from_site_health(url, site_health)
            regression = detect_regression(history, entry, threshold=alert_threshold)
            append_history_entry(history_path, entry)

            if regression:
                click.echo(f"Regression detected: {regression.message}", err=True)
                if alert_webhook:
                    from pytagmanager.sitewide.notify import WebhookNotifier

                    sent = WebhookNotifier(alert_webhook).send(
                        f"PyTagManager tracking health regression for {url}: {regression.message}"
                    )
                    if not sent:
                        click.echo("Warning: failed to send regression alert to webhook.", err=True)

        if output_format == "json":
            report_dict = build_site_health_json(
                site_health, consistency_reports, anomalies, business_action_reports, event_map
            )
            if regression:
                report_dict["regression"] = {
                    "message": regression.message,
                    "previous_score": regression.previous_score,
                    "current_score": regression.current_score,
                }
            if traces:
                report_dict["interaction_traces"] = [build_interaction_trace_json(t) for t in traces]
            if all_duplicate_findings:
                report_dict["duplicate_tag_findings"] = build_duplicate_findings_json(all_duplicate_findings)
            if all_server_side_indicators:
                report_dict["server_side_tagging_indicators"] = build_server_side_indicators_json(
                    all_server_side_indicators
                )
            report = json.dumps(report_dict, indent=2)
        else:
            report = render_site_health_report(
                site_health, consistency_reports, anomalies, business_action_reports, event_map
            )
            if regression:
                report += f"\n\nREGRESSION: {regression.message}"
            if all_duplicate_findings:
                report += "\n\n" + "\n".join(render_duplicate_findings(all_duplicate_findings))
            if all_server_side_indicators:
                report += "\n\n" + "\n".join(render_server_side_indicators(all_server_side_indicators))
            if traces:
                report += "\n\n" + "\n\n".join(render_interaction_trace(t) for t in traces)
    else:
        extra_findings = find_duplicate_purchases(diagnosed)
        if output_format == "json":
            report_dict = build_json_report(diagnosed, all_untested, extra_findings, all_state_diffs)
            if traces:
                report_dict["interaction_traces"] = [build_interaction_trace_json(t) for t in traces]
            if all_duplicate_findings:
                report_dict["duplicate_tag_findings"] = build_duplicate_findings_json(all_duplicate_findings)
            if all_server_side_indicators:
                report_dict["server_side_tagging_indicators"] = build_server_side_indicators_json(
                    all_server_side_indicators
                )
            report = json.dumps(report_dict, indent=2)
        else:
            report = render_terminal_report(
                diagnosed, all_untested, verbose=verbose, extra_findings=extra_findings, state_diffs=all_state_diffs
            )
            if all_duplicate_findings:
                report += "\n\n" + "\n".join(render_duplicate_findings(all_duplicate_findings))
            if all_server_side_indicators:
                report += "\n\n" + "\n".join(render_server_side_indicators(all_server_side_indicators))
            if traces:
                report += "\n\n" + "\n\n".join(render_interaction_trace(t) for t in traces)

    if output_path:
        with open(output_path, "w") as f:
            f.write(report)
        click.echo(f"Wrote diagnostic report to {output_path}")
    else:
        click.echo(report)


@main.command(name="scan-tags")
@click.argument("url")
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option("--browser", type=click.Choice(["chromium", "firefox", "webkit"]), default="chromium", show_default=True)
@click.option(
    "--wait",
    "wait_seconds",
    default=3.0,
    show_default=True,
    type=float,
    help="Seconds to wait after page load before a second snapshot, to catch GTM containers/vendor "
    "scripts that load asynchronously (consent-gated, interaction-gated, or just slow).",
)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def scan_tags(
    url: str,
    headless: bool,
    browser: str,
    wait_seconds: float,
    output_path: str | None,
    output_format: str,
) -> None:
    """Static code intelligence (docs/VISION.md §17): detect GTM containers
    and hard-coded vendor tracking implementations (GA4, Meta Pixel, Adobe
    Analytics, and others) on URL, including ones that load after a delay.
    Requires `pip install pytagmanager[diagnostics]`.
    """
    from pytagmanager.observability.session import ObservationSession
    from pytagmanager.tagexec.report import build_static_scan_json, render_static_scan_report
    from pytagmanager.tagexec.static_scan import detect_delayed_containers, scan_html

    click.echo(f"Loading {url}...", err=True)
    with ObservationSession(headless=headless, browser_name=browser) as session:
        session.load(url)
        baseline_html = session.capture_html()
        session.wait(wait_seconds)
        later_html = session.capture_html()

    baseline = scan_html(baseline_html, url)
    result = scan_html(later_html, url)
    delayed = detect_delayed_containers(baseline, result)

    if output_format == "json":
        report = json.dumps(build_static_scan_json(result, delayed_container_ids=delayed), indent=2)
    else:
        report = render_static_scan_report(result, delayed_container_ids=delayed)

    if output_path:
        with open(output_path, "w") as f:
            f.write(report)
        click.echo(f"Wrote static scan report to {output_path}")
    else:
        click.echo(report)


if __name__ == "__main__":
    main()
