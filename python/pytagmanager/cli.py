from __future__ import annotations

import functools
import json
import os
from pathlib import Path

import click

from pytagmanager.control import (
    ControlError,
    ControlPlaneService,
    FileStore,
    resolve_secret_ref,
    validate_with_pytagshield,
)
from pytagmanager.discovery.crawl import crawl_site, crawl_site_rendered
from pytagmanager.distribution import FilesystemCDN
from pytagmanager.distribution.publisher import write_static_server_config
from pytagmanager.export.base import EXPORTERS
from pytagmanager.gtm import (
    analyze_container,
    gtm_to_payload,
    load_container,
    payload_to_gtm,
    write_container,
)
from pytagmanager.intent.ollama_classifier import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    OllamaIntentClassifier,
)
from pytagmanager.recommend.heuristics import recommend_for_graph
from pytagmanager.version_control.diff import diff_snapshots, format_diff_report
from pytagmanager.version_control.snapshot import (
    build_snapshot,
    load_snapshot,
    save_snapshot,
)


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
@click.option(
    "--render",
    "render_mode",
    is_flag=True,
    help="Render each page in a real Playwright browser session before building its DOM graph, "
    "capturing console logs/network/dataLayer along the way -- not just the raw HTTP response "
    "body. Slower (one extra browser fetch per page); requires pytagmanager[diagnostics]. Takes "
    "priority over --browser if both are given.",
)
@click.option(
    "--browser",
    "browser_mode",
    type=click.Choice(["off", "auto", "always"]),
    default="off",
    show_default=True,
    help="Lighter-weight per-page rendering built into the crawl itself (via Mudfish's browser "
    "engine): 'auto' renders only pages that look like a near-empty client-rendered shell; "
    "'always' renders every HTML page. Ignored if --render is also given.",
)
@click.option(
    "--screenshots-dir",
    "screenshot_dir",
    type=click.Path(),
    default=None,
    help="With --render: save desktop/mobile, above-fold/full-page PNG screenshots per page to this directory.",
)
@click.option(
    "--sniff-analytics",
    "sniff_analytics",
    is_flag=True,
    help="With --render: report already-firing analytics vendors and window.dataLayer presence per page.",
)
@click.option(
    "--simulate-interactions",
    "simulate_interactions_flag",
    is_flag=True,
    help="With --render: click each page's top-N recommended elements and report DOM mutations / "
    "network requests observed -- a real runtime check, not just a static selector guess.",
)
@click.option(
    "--interaction-top-n",
    default=5,
    show_default=True,
    type=int,
    help="With --simulate-interactions: how many top-confidence recommended elements to interact with per page.",
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
    render_mode: bool,
    browser_mode: str,
    screenshot_dir: str | None,
    sniff_analytics: bool,
    simulate_interactions_flag: bool,
    interaction_top_n: int,
) -> None:
    """Crawl URL, generate tracking recommendations, and optionally export them."""
    headers = _parse_headers(raw_headers)
    classifier = (
        OllamaIntentClassifier(model=ollama_model, base_url=ollama_url)
        if intent_engine == "ollama"
        else None
    )

    if render_mode:
        click.echo(
            f"Crawling {url} in render mode (max_pages={max_pages}, concurrency={concurrency})..."
        )
        pages = crawl_site_rendered(
            url,
            max_pages=max_pages,
            concurrency=concurrency,
            respect_robots=not no_robots,
            rate_limit=rate_limit,
            headers=headers,
            screenshot_dir=screenshot_dir,
            sniff_analytics=sniff_analytics,
            simulate_interactions=simulate_interactions_flag,
            interaction_top_n=interaction_top_n,
        )
    else:
        click.echo(f"Crawling {url} (max_pages={max_pages}, concurrency={concurrency})...")
        pages = crawl_site(
            url,
            max_pages=max_pages,
            concurrency=concurrency,
            respect_robots=not no_robots,
            rate_limit=rate_limit,
            headers=headers,
            browser_mode=browser_mode,
        )
    click.echo(f"Crawled {len(pages)} page(s).")

    if not render_mode:
        issue_counts: dict[str, int] = {}
        for page in pages:
            if page.crawl_status != "success":
                issue_counts[page.crawl_status] = issue_counts.get(page.crawl_status, 0) + 1
        if issue_counts:
            issues = ", ".join(
                f"{count} {status}" for status, count in sorted(issue_counts.items())
            )
            click.echo(f"Crawl issues: {issues}")

    if render_mode:
        for page in pages:
            if page.sniff is not None:
                vendor_names = ", ".join(page.sniff.vendors) or "none"
                click.echo(
                    f"  {page.url}: vendors observed firing = [{vendor_names}], "
                    f"dataLayer present = {page.sniff.data_layer_present}"
                )
            if page.screenshots is not None:
                click.echo(
                    f"  {page.url}: screenshots saved under {screenshot_dir} (id={page.screenshots.page_id})"
                )
            for obs in page.interactions:
                status = f"error: {obs.error}" if obs.error else f"{obs.mutation_count} mutation(s)"
                click.echo(
                    f"  {page.url}: {obs.action} {obs.selector} -> {status}, "
                    f"{len(obs.network_requests_fired)} new request(s)"
                )

    all_recs = []
    recs_by_url = {}
    for page in pages:
        recs = recommend_for_graph(page.graph, classifier=classifier)
        all_recs.extend(recs)
        recs_by_url[page.url] = recs
        click.echo(f"  {page.url} [{page.status}] -> {len(recs)} recommendation(s)")

    click.echo(f"\nTotal recommendations: {len(all_recs)}")
    for rec in all_recs[:20]:
        click.echo(
            f"  - {rec.event_name} ({rec.business_objective}, confidence={rec.confidence}) via {rec.selector}"
        )
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
@click.option(
    "--browser",
    type=click.Choice(["chromium", "firefox", "webkit"]),
    default="chromium",
    show_default=True,
)
@click.option(
    "--capture-storage-values",
    "capture_storage_values",
    is_flag=True,
    help="Capture raw cookie/localStorage/sessionStorage values, not just key names/types. Off by default -- see `diagnose --help`'s equivalent flag for the privacy rationale.",
)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
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
@click.option(
    "--test-candidates",
    "test_candidates",
    is_flag=True,
    help="With --compare-to, also generate regression-category Test Candidates (docs/VISION.md §15) for "
    "any dataLayer field that flipped from present to absent, each paired with a draft Playwright script.",
)
@click.option(
    "--gtm-config",
    "gtm_config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to a GTM container export (JSON). Cross-references dataLayer fields with the GTM tags, "
    "triggers, and variables that consume them; with --compare-to, reports GTM blast radius too.",
)
@click.option(
    "--gtm-container",
    "gtm_container_id",
    default=None,
    help="GTM public container ID (GTM-XXXXXXX) to fetch live config from. Requires --gtm-credentials.",
)
@click.option(
    "--gtm-credentials",
    "gtm_credentials_path",
    type=click.Path(exists=True),
    default=None,
    help="Service-account JSON key for the GTM Management API (read-only scope).",
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
    test_candidates: bool,
    gtm_config_path: str | None,
    gtm_container_id: str | None,
    gtm_credentials_path: str | None,
) -> None:
    """Crawl URL and build a Website Data Dictionary (docs/VISION.md §3):
    every cookie/localStorage/sessionStorage key and dataLayer field
    observed across the crawl, where, and how often. Requires
    `pip install pytagmanager[diagnostics]`.
    """
    from pytagmanager.dictionary.build import (
        build_data_dictionary,
        data_dictionary_from_json,
    )
    from pytagmanager.dictionary.gtm_usage import (
        build_gtm_usage_index,
        load_gtm_container,
    )
    from pytagmanager.dictionary.purpose import (
        HeuristicPurposeClassifier,
        OllamaPurposeClassifier,
    )
    from pytagmanager.dictionary.report import (
        build_dictionary_json,
        render_dictionary_report,
    )
    from pytagmanager.dictionary.schema_drift import (
        build_drift_json,
        diff_dictionaries,
        render_drift_report,
    )
    from pytagmanager.observability.scenario import auto_scenario_from_recommendations
    from pytagmanager.observability.session import ObservationSession
    from pytagmanager.testintel.regression import generate_regression_candidates
    from pytagmanager.testintel.report import (
        build_test_candidates_json,
        render_test_candidates,
    )

    gtm_usage = None
    if gtm_config_path:
        gtm_usage = build_gtm_usage_index(load_gtm_container(gtm_config_path))
    elif gtm_container_id:
        if not gtm_credentials_path:
            raise click.UsageError("--gtm-container requires --gtm-credentials")
        from pytagmanager.analytics_api.gtm_client import GtmApiClient

        client = GtmApiClient.from_service_account(gtm_credentials_path)
        container = client.find_container_by_public_id(gtm_container_id)
        if container is None:
            raise click.ClickException(
                f"GTM container {gtm_container_id!r} was not visible to the supplied credentials"
            )
        gtm_usage = build_gtm_usage_index(client.get_live_container_document(container["path"]))

    click.echo(f"Crawling {url} (max_pages={max_pages})...", err=True)
    pages = crawl_site(url, max_pages=max_pages)
    click.echo(f"Crawled {len(pages)} page(s).", err=True)

    snapshots = []
    for page in pages:
        recs = recommend_for_graph(page.graph)
        scenarios = auto_scenario_from_recommendations(recs, page.url)
        with ObservationSession(
            headless=headless,
            browser_name=browser,
            capture_storage_values=capture_storage_values,
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
        regression_candidates = (
            generate_regression_candidates(drift, compare_to_path, url) if test_candidates else []
        )
        if output_format == "json":
            report_dict = build_drift_json(drift, gtm_usage=gtm_usage)
            if regression_candidates:
                report_dict["test_candidates"] = build_test_candidates_json(regression_candidates)
            report = json.dumps(report_dict, indent=2)
        else:
            report = render_drift_report(drift, gtm_usage=gtm_usage)
            if regression_candidates:
                report += "\n\n" + "\n".join(render_test_candidates(regression_candidates))
        if output_path:
            with open(output_path, "w") as f:
                f.write(report)
            click.echo(f"Wrote schema drift report to {output_path}")
        else:
            click.echo(report)
        return

    purpose_by_key = None
    if purpose_engine != "none":
        classifier = (
            OllamaPurposeClassifier()
            if purpose_engine == "ollama"
            else HeuristicPurposeClassifier()
        )
        purpose_by_key = {
            (v.source, v.path): classifier.classify(v)
            for v in result.variables
            if v.source in ("cookie", "local_storage", "session_storage")
        }

    if output_format == "json":
        report = json.dumps(
            build_dictionary_json(
                result,
                purpose_by_key=purpose_by_key,
                include_presence=include_presence,
                gtm_usage=gtm_usage,
            ),
            indent=2,
        )
    else:
        report = render_dictionary_report(
            result,
            purpose_by_key=purpose_by_key,
            include_presence=include_presence,
            gtm_usage=gtm_usage,
        )

    if output_path:
        with open(output_path, "w") as f:
            f.write(report)
        click.echo(f"Wrote data dictionary to {output_path}")
    else:
        click.echo(report)


@main.command(name="gtm-plan")
@click.option(
    "--generated",
    "generated_path",
    required=True,
    type=click.Path(exists=True),
    help="Generated container JSON (e.g. `pytagmanager crawl ... --export gtm -o out.json`).",
)
@click.option(
    "--container",
    "container_id",
    required=True,
    help="GTM public container ID (GTM-XXXXXXX).",
)
@click.option(
    "--credentials",
    "credentials_path",
    required=True,
    type=click.Path(exists=True),
    help="Service-account JSON key for the GTM Management API (read-only is enough).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def gtm_plan(
    generated_path: str, container_id: str, credentials_path: str, output_format: str
) -> None:
    """Dry-run: compare a generated GTM container with the live container.

    Reports resources that would be added, already exist, or conflict by
    name/type. This command never writes to GTM.
    """
    import json as _json

    from pytagmanager.analytics_api.gtm_client import GtmApiClient
    from pytagmanager.analytics_api.gtm_plan import plan_import, render_plan

    with open(generated_path, encoding="utf-8") as handle:
        generated = _json.load(handle)

    client = GtmApiClient.from_service_account(credentials_path)
    container = client.find_container_by_public_id(container_id)
    if container is None:
        raise click.ClickException(
            f"GTM container {container_id!r} was not visible to the credentials"
        )
    live = client.get_live_container_document(container["path"])
    plan = plan_import(generated, live)

    if output_format == "json":
        click.echo(_json.dumps(plan.to_dict(), indent=2))
    else:
        click.echo(render_plan(plan))
    if plan.has_conflicts:
        raise click.exceptions.Exit(1)


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
@click.option(
    "--sdr",
    "sdr_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Solution Design Reference (.json or .csv) to validate against observed dataLayer events and fields.",
)
@click.option(
    "--fail-on-sdr-mismatch",
    is_flag=True,
    help="Exit 1 when SDR validation has at least one failed check.",
)
@click.option(
    "--gtm-container",
    default=None,
    help="GTM public container ID (GTM-XXXXXXX) to cross-check runtime events against.",
)
@click.option(
    "--gtm-credentials",
    type=click.Path(exists=True),
    default=None,
    help="Service-account JSON key for the GTM Management API.",
)
@click.option(
    "--ga4-property",
    default=None,
    help="GA4 property ID to cross-check config/ingestion against.",
)
@click.option(
    "--ga4-credentials",
    type=click.Path(exists=True),
    default=None,
    help="Service-account JSON key for the GA4 Admin/Data APIs.",
)
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option(
    "--browser",
    type=click.Choice(["chromium", "firefox", "webkit"]),
    default="chromium",
    show_default=True,
)
@click.option(
    "--duration",
    default=2.0,
    show_default=True,
    type=float,
    help="Seconds to wait after each interaction for downstream dataLayer/GTM/network effects to settle.",
)
@click.option(
    "--window",
    "correlation_window",
    default=5.0,
    show_default=True,
    type=float,
    help="Correlation window in seconds after an interaction.",
)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
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
    "--fail-on-regression",
    "fail_on_regression",
    is_flag=True,
    help="Exit non-zero when --history detects a regression (for scheduled CI jobs).",
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
@click.option(
    "--tag-graph",
    "tag_graph",
    is_flag=True,
    help="Assemble the Tag Execution Graph (docs/VISION.md §17): static-scan nodes + Interaction Trace "
    "steps + duplicate findings + server-side indicators, with every edge labeled by evidence strength "
    "(Observed/Inferred/Suspected). JSON output only (--format json) -- the full graph isn't meant to be "
    "read as flat text.",
)
@click.option(
    "--tag-graph-html",
    "tag_graph_html",
    default=None,
    type=click.Path(dir_okay=False),
    help="Also write the Tag Execution Graph as a standalone interactive HTML/SVG file to this path "
    "(implies --tag-graph). Open it directly in a browser -- no server, no external assets.",
)
@click.option(
    "--test-candidates",
    "test_candidates",
    is_flag=True,
    help="Generate evidence-backed Test Candidates (docs/VISION.md §15) from this run's findings, each "
    "paired with a draft Playwright script -- discovery, not a verified test; review before formalizing. "
    "Severity never reaches 'Confirmed defect' -- only a human/Playwright run confirms a defect. With "
    "--site-wide, also includes cross-page business-action naming-consistency candidates.",
)
def diagnose(
    url: str,
    max_pages: int,
    scenario_path: str | None,
    sdr_path: str | None,
    fail_on_sdr_mismatch: bool,
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
    fail_on_regression: bool,
    capture_storage_values: bool,
    include_trace: bool,
    track_scroll_depth: bool,
    detect_duplicate_tags: bool,
    detect_server_side_tagging: bool,
    tag_graph: bool,
    tag_graph_html: str | None,
    test_candidates: bool,
) -> None:
    """Drive a real browser through URL (or a crawl of it), observe the full
    interaction -> dataLayer -> GTM -> GA4 tracking chain, and diagnose
    where and why it broke. Requires `pip install pytagmanager[diagnostics]`.
    """
    if scenario_path and site_wide:
        raise click.UsageError(
            "--site-wide requires crawling the site; it cannot be combined with --scenario."
        )
    if history_path and not site_wide:
        raise click.UsageError(
            "--history requires --site-wide (health scores are a site-wide concept)."
        )
    if alert_webhook and not history_path:
        raise click.UsageError(
            "--alert-webhook requires --history (there must be a previous run to compare against)."
        )
    if fail_on_regression and not history_path:
        raise click.UsageError("--fail-on-regression requires --history.")
    if tag_graph_html:
        tag_graph = True
    if fail_on_sdr_mismatch and not sdr_path:
        raise click.UsageError("--fail-on-sdr-mismatch requires --sdr.")
    sdr_schema = None
    if sdr_path:
        from pytagmanager.sdr import SdrFormatError, load_sdr

        try:
            sdr_schema = load_sdr(sdr_path)
        except SdrFormatError as exc:
            raise click.ClickException(str(exc)) from exc
    from pytagmanager.analytics_api.ga4_client import Ga4ApiClient
    from pytagmanager.analytics_api.gtm_client import GtmApiClient
    from pytagmanager.correlation.journey import correlate_events
    from pytagmanager.diagnostics.rules import (
        DiagnosticContext,
        find_duplicate_purchases,
        find_untested_recommendations,
    )
    from pytagmanager.diagnostics.trace import (
        build_interaction_trace_json,
        build_interaction_traces,
        render_interaction_trace,
    )
    from pytagmanager.observability.scenario import (
        auto_scenario_from_recommendations,
        load_scenario,
    )
    from pytagmanager.observability.session import ObservationSession
    from pytagmanager.reporting.json_report import build_json_report
    from pytagmanager.reporting.terminal import (
        diagnose_journeys,
        render_terminal_report,
    )
    from pytagmanager.tagexec.duplicates import analyze_duplicates
    from pytagmanager.tagexec.graph import (
        build_graph_html,
        build_graph_json,
        build_tag_execution_graph,
    )
    from pytagmanager.tagexec.report import (
        build_duplicate_findings_json,
        build_server_side_indicators_json,
        render_duplicate_findings,
        render_server_side_indicators,
    )
    from pytagmanager.tagexec.server_side import analyze_server_side_indicators
    from pytagmanager.tagexec.static_scan import scan_html
    from pytagmanager.testintel.candidates import (
        generate_consistency_candidates,
        generate_diagnosis_candidates,
    )
    from pytagmanager.testintel.report import (
        build_test_candidates_json,
        render_test_candidates,
    )

    gtm_triggers = gtm_tags = None
    if gtm_container and gtm_credentials:
        client = GtmApiClient.from_service_account(gtm_credentials)
        container = client.find_container_by_public_id(gtm_container)
        if container is None:
            click.echo(
                f"Warning: GTM container {gtm_container} not found for the given credentials.",
                err=True,
            )
        else:
            config = client.get_live_container_config(container["path"])
            gtm_triggers, gtm_tags = config["triggers"], config["tags"]

    ga4_client = (
        Ga4ApiClient.from_service_account(ga4_credentials)
        if (ga4_property and ga4_credentials)
        else None
    )

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
            pages_and_scenarios.append(
                (page.url, auto_scenario_from_recommendations(recs, page.url), recs)
            )

    all_journeys = []
    all_untested = []
    all_state_diffs = []
    all_duplicate_findings = []
    all_server_side_indicators = []
    all_scans = []
    expectations_by_selector: dict = {}
    needs_page_html = detect_duplicate_tags or tag_graph
    needs_page_traces = detect_duplicate_tags or detect_server_side_tagging or tag_graph

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
            page_html = session.capture_html() if needs_page_html else None
        journeys = correlate_events(events, window_seconds=correlation_window)
        all_journeys.extend(journeys)
        if recs:
            all_untested.extend(find_untested_recommendations(recs, journeys))
        page_traces = build_interaction_traces(journeys) if needs_page_traces else []
        page_scan = scan_html(page_html, page_url) if page_html is not None else None
        if page_scan is not None:
            all_scans.append(page_scan)
        if detect_duplicate_tags and page_scan is not None:
            all_duplicate_findings.extend(analyze_duplicates(page_scan, page_traces))
        if detect_server_side_tagging:
            all_server_side_indicators.extend(analyze_server_side_indicators(page_traces))

    ga4_ingestion: dict = {}
    if ga4_client and ga4_property:
        for event_name in {j.business_event for j in all_journeys}:
            ga4_ingestion[event_name] = ga4_client.was_event_ingested_realtime(
                ga4_property, event_name
            )

    ctx = DiagnosticContext(
        expectations_by_selector=expectations_by_selector,
        gtm_triggers=gtm_triggers,
        gtm_tags=gtm_tags,
        ga4_ingestion=ga4_ingestion,
        state_diffs=all_state_diffs,
    )
    diagnosed = diagnose_journeys(all_journeys, ctx)
    sdr_validation = None
    if sdr_schema is not None:
        from pytagmanager.sdr import validate_sdr

        sdr_validation = validate_sdr(sdr_schema, diagnosed)

    traces = []
    if include_trace or tag_graph:
        state_diffs_by_journey_id = {}
        for journey in diagnosed:
            diff = ctx.state_diff_for_journey(journey)
            if diff is not None:
                state_diffs_by_journey_id[journey.journey_id] = diff
        traces = build_interaction_traces(diagnosed, state_diffs_by_journey_id)

    tag_execution_graph_json = None
    if tag_graph:
        graph = build_tag_execution_graph(
            all_scans, traces, all_duplicate_findings, all_server_side_indicators
        )
        tag_execution_graph_json = build_graph_json(graph)
        if tag_graph_html:
            import pathlib

            html_path = pathlib.Path(tag_graph_html)
            if html_path.parent and str(html_path.parent):
                html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(build_graph_html(graph), encoding="utf-8")

    all_test_candidates = generate_diagnosis_candidates(diagnosed) if test_candidates else []
    regression = None

    if site_wide:
        from pytagmanager.sitewide.aggregation import (
            analyze_template_consistency,
            compute_site_health,
        )
        from pytagmanager.sitewide.anomalies import detect_site_anomalies
        from pytagmanager.sitewide.event_map import build_runtime_event_map
        from pytagmanager.sitewide.interaction_consistency import (
            analyze_business_action_consistency,
        )
        from pytagmanager.sitewide.report import (
            build_site_health_json,
            render_site_health_report,
        )
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
            from pytagmanager.sitewide.page_type import (
                OllamaPageTypeClassifier,
                assign_semantic_labels,
            )

            graphs_by_url = {page.url: page.graph for page in pages}
            templates = assign_semantic_labels(templates, graphs_by_url, OllamaPageTypeClassifier())

        site_health = compute_site_health(templates, journeys_by_page, untested_by_page)
        consistency_reports = [analyze_template_consistency(t, journeys_by_page) for t in templates]
        anomalies = detect_site_anomalies(templates, journeys_by_page)
        business_action_reports = analyze_business_action_consistency(recs_by_page, diagnosed)
        event_map = build_runtime_event_map(diagnosed)
        if test_candidates:
            all_test_candidates += generate_consistency_candidates(business_action_reports)

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
                        click.echo(
                            "Warning: failed to send regression alert to webhook.",
                            err=True,
                        )

        if output_format == "json":
            report_dict = build_site_health_json(
                site_health,
                consistency_reports,
                anomalies,
                business_action_reports,
                event_map,
            )
            if regression:
                report_dict["regression"] = {
                    "message": regression.message,
                    "previous_score": regression.previous_score,
                    "current_score": regression.current_score,
                }
            if traces:
                report_dict["interaction_traces"] = [
                    build_interaction_trace_json(t) for t in traces
                ]
            if all_duplicate_findings:
                report_dict["duplicate_tag_findings"] = build_duplicate_findings_json(
                    all_duplicate_findings
                )
            if all_server_side_indicators:
                report_dict["server_side_tagging_indicators"] = build_server_side_indicators_json(
                    all_server_side_indicators
                )
            if tag_execution_graph_json is not None:
                report_dict["tag_execution_graph"] = tag_execution_graph_json
            if all_test_candidates:
                report_dict["test_candidates"] = build_test_candidates_json(all_test_candidates)
            if sdr_validation is not None:
                report_dict["sdr_alignment"] = sdr_validation.to_dict()
            report = json.dumps(report_dict, indent=2)
        else:
            report = render_site_health_report(
                site_health,
                consistency_reports,
                anomalies,
                business_action_reports,
                event_map,
            )
            if regression:
                report += f"\n\nREGRESSION: {regression.message}"
            if all_duplicate_findings:
                report += "\n\n" + "\n".join(render_duplicate_findings(all_duplicate_findings))
            if all_server_side_indicators:
                report += "\n\n" + "\n".join(
                    render_server_side_indicators(all_server_side_indicators)
                )
            if tag_execution_graph_json is not None:
                report += (
                    f"\n\nTag Execution Graph: {len(tag_execution_graph_json['nodes'])} nodes, "
                    f"{len(tag_execution_graph_json['edges'])} edges (use --format json for the full graph)."
                )
            if all_test_candidates:
                report += "\n\n" + "\n".join(render_test_candidates(all_test_candidates))
            if sdr_validation is not None:
                from pytagmanager.sdr import render_sdr_report

                report += "\n\n" + render_sdr_report(sdr_validation)
            if traces:
                report += "\n\n" + "\n\n".join(render_interaction_trace(t) for t in traces)
    else:
        extra_findings = find_duplicate_purchases(diagnosed)
        if output_format == "json":
            report_dict = build_json_report(
                diagnosed, all_untested, extra_findings, all_state_diffs
            )
            if traces:
                report_dict["interaction_traces"] = [
                    build_interaction_trace_json(t) for t in traces
                ]
            if all_duplicate_findings:
                report_dict["duplicate_tag_findings"] = build_duplicate_findings_json(
                    all_duplicate_findings
                )
            if all_server_side_indicators:
                report_dict["server_side_tagging_indicators"] = build_server_side_indicators_json(
                    all_server_side_indicators
                )
            if tag_execution_graph_json is not None:
                report_dict["tag_execution_graph"] = tag_execution_graph_json
            if all_test_candidates:
                report_dict["test_candidates"] = build_test_candidates_json(all_test_candidates)
            if sdr_validation is not None:
                report_dict["sdr_alignment"] = sdr_validation.to_dict()
            report = json.dumps(report_dict, indent=2)
        else:
            report = render_terminal_report(
                diagnosed,
                all_untested,
                verbose=verbose,
                extra_findings=extra_findings,
                state_diffs=all_state_diffs,
            )
            if all_duplicate_findings:
                report += "\n\n" + "\n".join(render_duplicate_findings(all_duplicate_findings))
            if all_server_side_indicators:
                report += "\n\n" + "\n".join(
                    render_server_side_indicators(all_server_side_indicators)
                )
            if tag_execution_graph_json is not None:
                report += (
                    f"\n\nTag Execution Graph: {len(tag_execution_graph_json['nodes'])} nodes, "
                    f"{len(tag_execution_graph_json['edges'])} edges (use --format json for the full graph)."
                )
            if all_test_candidates:
                report += "\n\n" + "\n".join(render_test_candidates(all_test_candidates))
            if sdr_validation is not None:
                from pytagmanager.sdr import render_sdr_report

                report += "\n\n" + render_sdr_report(sdr_validation)
            if traces:
                report += "\n\n" + "\n\n".join(render_interaction_trace(t) for t in traces)

    if output_path:
        with open(output_path, "w") as f:
            f.write(report)
        click.echo(f"Wrote diagnostic report to {output_path}")
    else:
        click.echo(report)
    if fail_on_sdr_mismatch and sdr_validation is not None and not sdr_validation.is_aligned:
        raise click.exceptions.Exit(1)


@main.command(name="scan-tags")
@click.argument("url")
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option(
    "--browser",
    type=click.Choice(["chromium", "firefox", "webkit"]),
    default="chromium",
    show_default=True,
)
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
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
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
    from pytagmanager.tagexec.report import (
        build_static_scan_json,
        render_static_scan_report,
    )
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


@main.command(name="perf")
@click.argument("url")
@click.option(
    "--runs",
    default=3,
    show_default=True,
    type=int,
    help="Page loads to aggregate (median). Never trust a single-run number.",
)
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option(
    "--browser",
    type=click.Choice(["chromium", "firefox", "webkit"]),
    default="chromium",
    show_default=True,
)
@click.option(
    "--isolate",
    "isolate_script_url",
    default=None,
    help="Isolate one script by exact URL and measure its impact.",
)
@click.option(
    "--isolate-group",
    "isolate_group_name",
    default=None,
    help="Isolate one script group (e.g. 'ads', 'analytics', 'heatmap', 'tag_management' -- see "
    "docs/ROADMAP.md Phase 1.95 item 4 for the full, disclosed-as-partial list) and measure its impact.",
)
@click.option(
    "--all-off",
    "all_non_essential",
    is_flag=True,
    help="Isolate every classifiable (tagging/marketing-adjacent) script at once. Never blocks an "
    "unclassified first-party script.",
)
@click.option(
    "--cpu-throttling",
    "cpu_throttling_rate",
    default=None,
    type=float,
    help="Real CDP CPU throttling rate (e.g. 4 == CPU is 4x slower), applied before every run.",
)
@click.option(
    "--history",
    "history_path",
    type=click.Path(),
    default=None,
    help="Append this run's metrics to a JSON history file and check for an LCP/TBT regression vs. the previous run.",
)
@click.option(
    "--test-candidates",
    "include_test_candidates",
    is_flag=True,
    help="Generate evidence-backed Test Candidates (docs/VISION.md §15) for budget-exceeding isolated "
    "scripts and detected regressions, reusing Phase 1.9's TestCandidate model.",
)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def perf(
    url: str,
    runs: int,
    headless: bool,
    browser: str,
    isolate_script_url: str | None,
    isolate_group_name: str | None,
    all_non_essential: bool,
    cpu_throttling_rate: float | None,
    history_path: str | None,
    include_test_candidates: bool,
    output_path: str | None,
    output_format: str,
) -> None:
    """Automated Script Impact & Web Performance Intelligence
    (docs/VISION.md §16): real LCP/CLS/TBT/INP measurement, a script
    inventory, and -- with --isolate/--isolate-group/--all-off -- a
    controlled isolation experiment reporting the observed performance
    impact of blocking a script/group. Requires
    `pip install pytagmanager[diagnostics]`.
    """
    isolate_targets = [t for t in (isolate_script_url, isolate_group_name, all_non_essential) if t]
    if len(isolate_targets) > 1:
        raise click.UsageError(
            "--isolate, --isolate-group, and --all-off are mutually exclusive; pass only one."
        )

    from pytagmanager.perf.experiments import (
        isolate_all_non_essential,
        isolate_group,
        isolate_script,
    )
    from pytagmanager.perf.history import (
        PerformanceHistoryEntry,
        append_performance_history_entry,
        detect_performance_regression,
        load_performance_history,
    )
    from pytagmanager.perf.measure import (
        TestEnvironmentConfig,
        measure_page_performance,
    )
    from pytagmanager.perf.report import (
        build_performance_report_json,
        render_performance_report,
    )
    from pytagmanager.perf.scripts import build_script_inventory
    from pytagmanager.perf.tagging_join import build_tagging_performance_tradeoffs
    from pytagmanager.perf.test_candidates import (
        generate_performance_budget_candidates,
        generate_performance_regression_candidates,
    )
    from pytagmanager.testintel.report import (
        build_test_candidates_json,
        render_test_candidates,
    )

    click.echo(f"Building script inventory for {url}...", err=True)
    inventory = build_script_inventory(url, headless=headless, browser_name=browser)

    environment = TestEnvironmentConfig(
        browser_name=browser,
        headless=headless,
        run_count=runs,
        cpu_throttling_rate=cpu_throttling_rate,
    )

    click.echo(f"Measuring baseline performance ({runs} run(s))...", err=True)
    baseline = measure_page_performance(
        url, runs=runs, headless=headless, browser_name=browser, environment=environment
    )

    experiment_results = []
    if isolate_script_url:
        click.echo(f"Isolating script {isolate_script_url}...", err=True)
        experiment_results.append(
            isolate_script(
                url,
                isolate_script_url,
                inventory=inventory,
                baseline=baseline,
                runs=runs,
                headless=headless,
                browser_name=browser,
            )
        )
    elif isolate_group_name:
        click.echo(f"Isolating group '{isolate_group_name}'...", err=True)
        experiment_results.append(
            isolate_group(
                url,
                isolate_group_name,
                inventory=inventory,
                baseline=baseline,
                runs=runs,
                headless=headless,
                browser_name=browser,
            )
        )
    elif all_non_essential:
        click.echo("Isolating all non-essential (classified) scripts...", err=True)
        experiment_results.append(
            isolate_all_non_essential(
                url,
                inventory=inventory,
                baseline=baseline,
                runs=runs,
                headless=headless,
                browser_name=browser,
            )
        )

    tradeoffs = build_tagging_performance_tradeoffs(inventory, experiment_results)

    regression_alerts = []
    if history_path:
        history = load_performance_history(history_path)
        entry = PerformanceHistoryEntry.from_baseline(
            baseline, script_urls=[s.url for s in inventory.scripts]
        )
        regression_alerts = detect_performance_regression(history, entry)
        append_performance_history_entry(history_path, entry)
        for alert in regression_alerts:
            click.echo(f"Regression detected: {alert.message}", err=True)

    all_test_candidates = []
    if include_test_candidates:
        all_test_candidates.extend(generate_performance_budget_candidates(experiment_results))
        all_test_candidates.extend(generate_performance_regression_candidates(regression_alerts))

    if output_format == "json":
        report_dict = build_performance_report_json(baseline, tradeoffs)
        if experiment_results:
            report_dict["isolation_experiments"] = [
                {
                    "target_description": r.target_description,
                    "blocked_urls": list(r.blocked_urls),
                    "lcp_delta_ms": r.lcp_delta_ms,
                    "tbt_delta_ms": r.tbt_delta_ms,
                    "cls_delta": r.cls_delta,
                    "inp_delta_ms": r.inp_delta_ms,
                    "message": r.message,
                }
                for r in experiment_results
            ]
        if regression_alerts:
            report_dict["regression_alerts"] = [
                {
                    "message": a.message,
                    "metric": a.metric,
                    "previous_value": a.previous_value,
                    "current_value": a.current_value,
                    "new_scripts": list(a.new_scripts),
                }
                for a in regression_alerts
            ]
        if all_test_candidates:
            report_dict["test_candidates"] = build_test_candidates_json(all_test_candidates)
        report = json.dumps(report_dict, indent=2)
    else:
        lines = render_performance_report(baseline, tradeoffs)
        for r in experiment_results:
            lines.append(f"ISOLATION EXPERIMENT: {r.message}")
            lines.append("")
        for alert in regression_alerts:
            lines.append(f"REGRESSION: {alert.message}")
        if regression_alerts:
            lines.append("")
        if all_test_candidates:
            lines.extend(render_test_candidates(all_test_candidates))
        report = "\n".join(lines)

    if output_path:
        with open(output_path, "w") as f:
            f.write(report)
        click.echo(f"Wrote performance report to {output_path}")
    else:
        click.echo(report)


@main.command("lighthouse")
@click.argument("url")
@click.option("--output", "output_path", type=click.Path(), default=None)
@click.option("--lighthouse-path", default="lighthouse", show_default=True)
@click.option("--chrome-path", default=None)
@click.option("--timeout", default=120, show_default=True, type=int)
@click.option("--json", "as_json", is_flag=True, help="Emit the normalized report as JSON")
def lighthouse_command(url, output_path, lighthouse_path, chrome_path, timeout, as_json):
    """Run a Lighthouse audit and normalize scores/Core Web Vitals."""
    from pytagmanager.audit.lighthouse import LighthouseRunner, LighthouseUnavailable

    try:
        report = LighthouseRunner(
            lighthouse_path=lighthouse_path, chrome_path=chrome_path, timeout=timeout
        ).run(url)
    except LighthouseUnavailable as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        text = json.dumps(report.to_dict(), indent=2)
    else:
        lines = [f"Lighthouse: {url}"]
        for name, score in sorted(report.categories.items()):
            lines.append(f"  {name}: {score * 100:.0f}")
        for name, value in sorted(report.metrics.items()):
            lines.append(f"  {name}: {value:.1f}")
        if report.audits:
            lines.append("  opportunities/failures:")
            for audit in report.audits[:10]:
                lines.append(
                    f"    - {audit['title']} ({audit['score']:.2f})"
                    + (f" — {audit['displayValue']}" if audit.get("displayValue") else "")
                )
        text = "\n".join(lines)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        click.echo(f"Wrote Lighthouse report to {output_path}")
    else:
        click.echo(text)


@main.command(name="lighthouse-ci")
@click.argument("url")
@click.option(
    "--runs",
    default=3,
    show_default=True,
    type=click.IntRange(1, 20),
    help="Number of independent Lighthouse runs to aggregate. One run is an anecdote; use at least 3.",
)
@click.option(
    "--min-runs",
    default=2,
    show_default=True,
    type=click.IntRange(1, 20),
    help="Minimum successful runs required before any assessment is made.",
)
@click.option(
    "--budget",
    "budget_specs",
    multiple=True,
    metavar="METRIC=VALUE",
    help="Performance budget evaluated against the median, e.g. lcp_ms=2500, tbt_ms=200, "
    "cls=0.1, performance=0.9. Repeatable. Allowed keys: lcp_ms, tbt_ms, cls, inp_ms, "
    "fcp_ms, speed_index_ms, performance, accessibility, best-practices, seo.",
)
@click.option(
    "--fail-on-budget",
    "fail_on_budget",
    is_flag=True,
    help="Exit 1 when any supplied budget is exceeded (or its metric is unavailable).",
)
@click.option(
    "--allow-partial",
    "allow_partial",
    is_flag=True,
    help="Do not exit 2 merely because some requested runs failed, as long as --min-runs completed. "
    "Insufficient data still always returns a failure exit code.",
)
@click.option("--lighthouse-path", default="lighthouse", show_default=True)
@click.option("--chrome-path", default=None)
@click.option(
    "--timeout",
    default=120,
    show_default=True,
    type=int,
    help="Per-run timeout in seconds.",
)
@click.option(
    "--max-output-mb",
    "max_output_mb",
    default=25,
    show_default=True,
    type=click.IntRange(1, 200),
    help="Reject a single Lighthouse JSON report larger than this many MiB.",
)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def lighthouse_ci(
    url: str,
    runs: int,
    min_runs: int,
    budget_specs: tuple[str, ...],
    fail_on_budget: bool,
    allow_partial: bool,
    lighthouse_path: str,
    chrome_path: str | None,
    timeout: int,
    max_output_mb: int,
    output_path: str | None,
    output_format: str,
) -> None:
    """Run repeated Lighthouse audits and report an honest assessment.

    Unlike `lighthouse`, this command never treats one run as a verdict: it
    reports medians and observed ranges across independent runs, records failed
    runs rather than dropping them, and only makes a pass/fail judgement when
    explicit budgets are supplied.
    """
    from pytagmanager.audit.lighthouse import (
        LighthouseRunner,
        LighthouseUnavailable,
        parse_budgets,
        render_lighthouse_ci_report,
    )

    if min_runs > runs:
        raise click.UsageError("--min-runs cannot exceed --runs")
    try:
        budgets = parse_budgets(budget_specs)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc

    try:
        report = LighthouseRunner(
            lighthouse_path=lighthouse_path,
            chrome_path=chrome_path,
            timeout=timeout,
            max_output_bytes=max_output_mb * 1024 * 1024,
        ).run_repeated(url, runs=runs, min_runs=min_runs, budgets=budgets)
    except LighthouseUnavailable as exc:
        raise click.ClickException(str(exc)) from exc
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    text = (
        json.dumps(report.to_dict(), indent=2)
        if output_format == "json"
        else render_lighthouse_ci_report(report)
    )
    if output_path:
        with open(output_path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        click.echo(f"Wrote Lighthouse CI report to {output_path}")
    else:
        click.echo(text)

    if report.insufficient_data:
        raise click.exceptions.Exit(2)
    if report.failed_runs and not allow_partial:
        raise click.exceptions.Exit(2)
    if fail_on_budget and report.budget_failed:
        raise click.exceptions.Exit(1)


def _control_command(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ControlError as exc:
            raise click.ClickException(str(exc)) from exc

    return wrapper


def _control_service(home: str | None) -> ControlPlaneService:
    return ControlPlaneService(FileStore(home) if home else FileStore())


def _print_json(value) -> None:
    click.echo(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def _parse_external_refs(raw_refs: tuple[str, ...]) -> list[dict[str, str]]:
    refs = []
    for raw in raw_refs:
        system, separator, ref_id = raw.partition(":")
        if not separator or not system.strip() or not ref_id.strip():
            raise click.UsageError(f"--external-ref must be 'SYSTEM:ID', got: {raw!r}")
        refs.append({"system": system.strip(), "id": ref_id.strip()})
    return refs


def _load_json_object(path: str, label: str) -> dict:
    if path == "-":
        raw = click.get_text_stream("stdin").read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise click.ClickException(f"{label} must be a JSON object")
    return value


def _load_payload(path: str | None) -> dict:
    return {} if path is None else _load_json_object(path, "payload")


def _parse_consent(raw_values: tuple[str, ...]) -> dict[str, bool]:
    consent = {}
    for raw in raw_values:
        purpose, separator, value = raw.partition("=")
        if not separator or not purpose.strip():
            raise click.UsageError(f"--consent must be 'PURPOSE=true|false', got: {raw!r}")
        lowered = value.strip().lower()
        if lowered not in {"true", "false"}:
            raise click.UsageError(f"--consent value must be true or false, got: {value!r}")
        consent[purpose.strip()] = lowered == "true"
    return consent


def _flatten_snapshot_recommendations(document: dict, path: str) -> list[dict]:
    pages = document.get("pages")
    if not isinstance(pages, list):
        raise click.ClickException(f"snapshot {path} has no pages list")
    recommendations = []
    for page in pages:
        if not isinstance(page, dict):
            raise click.ClickException(f"snapshot {path} contains a non-object page")
        page_url = page.get("url", "")
        raw_recommendations = page.get("recommendations", [])
        if not isinstance(raw_recommendations, list):
            raise click.ClickException(f"snapshot page {page_url!r} has invalid recommendations")
        for raw in raw_recommendations:
            if not isinstance(raw, dict):
                raise click.ClickException(
                    f"snapshot page {page_url!r} has a non-object recommendation"
                )
            item = dict(raw)
            item.setdefault("page_url", page_url)
            recommendations.append(item)
    if not recommendations:
        raise click.ClickException("snapshot contains no recommendations")
    return recommendations


@main.group()
def container() -> None:
    """Manage self-hosted tag containers."""


@container.command("create")
@click.option("--id", "container_id", required=True, help="User-supplied immutable container ID.")
@click.option("--name", default=None, help="Display name (defaults to the container ID).")
@click.option("--description", default="", show_default=True)
@click.option("--site-url", "site_urls", multiple=True, help="Repeatable site URL.")
@click.option(
    "--external-ref",
    "external_refs",
    multiple=True,
    metavar="SYSTEM:ID",
    help="Repeatable external relation, e.g. gtm:GTM-ABC1234. Never implies ownership.",
)
@click.option(
    "--org",
    "org_id",
    default=None,
    help="Organization UUID (default scope if omitted).",
)
@click.option("--workspace", "workspace_id", default=None, help="Workspace UUID.")
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def container_create(
    container_id,
    name,
    description,
    site_urls,
    external_refs,
    org_id,
    workspace_id,
    home,
    as_json,
):
    """Create a container with a user-specified ID."""
    created = _control_service(str(home) if home else None).create_container(
        container_id,
        name=name,
        org_id=org_id,
        workspace_id=workspace_id,
        description=description,
        site_urls=site_urls,
        external_refs=_parse_external_refs(external_refs),
    )
    if as_json:
        _print_json(created.to_dict())
    else:
        click.echo(f"Created container {created.container_id} ({created.name}).")


@container.command("list")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def container_list(org_id, home, as_json):
    """List containers in an organization."""
    containers = _control_service(str(home) if home else None).list_containers(org_id=org_id)
    if as_json:
        _print_json([item.to_dict() for item in containers])
        return
    if not containers:
        click.echo("No containers.")
        return
    for item in containers:
        click.echo(f"{item.container_id}\t{item.name}\t{item.workspace_id}\t{item.status}")


@container.command("show")
@click.option("--id", "container_id", required=True)
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def container_show(container_id, org_id, home, as_json):
    """Show one container."""
    item = _control_service(str(home) if home else None).get_container(container_id, org_id=org_id)
    if as_json:
        _print_json(item.to_dict())
        return
    click.echo(f"Container: {item.container_id}")
    click.echo(f"Name: {item.name}")
    click.echo(f"Organization: {item.org_id}")
    click.echo(f"Workspace: {item.workspace_id}")
    click.echo(f"Status: {item.status}")
    click.echo(f"Created: {item.created_at}")
    if item.site_urls:
        click.echo("Site URLs: " + ", ".join(item.site_urls))
    if item.external_refs:
        refs = ", ".join(f"{ref['system']}:{ref['id']}" for ref in item.external_refs)
        click.echo(f"External refs: {refs}")


@container.command("clone")
@click.option("--id", "source_container_id", required=True, help="Source container ID.")
@click.option("--as", "new_container_id", required=True, help="New immutable container ID.")
@click.option("--name", default=None)
@click.option("--org", "org_id", default=None)
@click.option("--workspace", "workspace_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def container_clone(
    source_container_id,
    new_container_id,
    name,
    org_id,
    workspace_id,
    home,
    as_json,
):
    """Clone a container under a new container ID."""
    result = _control_service(str(home) if home else None).clone_container(
        source_container_id,
        new_container_id,
        name=name,
        org_id=org_id,
        workspace_id=workspace_id,
    )
    if as_json:
        _print_json(result.container.to_dict())
    else:
        click.echo(
            f"Cloned {source_container_id} to {result.container.container_id} "
            f"with {result.revision_count} revision(s)."
        )


@container.command("validate")
@click.option("--id", "container_id", required=True)
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def container_validate(container_id, org_id, home, as_json):
    """Validate stored revision envelopes and checksums."""
    report = _control_service(str(home) if home else None).validate_container(
        container_id, org_id=org_id
    )
    if as_json:
        _print_json(report.to_dict())
        return
    click.echo(f"Container {report.container_id} is valid.")
    click.echo(f"Revisions: {report.revision_count}")
    click.echo(f"Schema: {report.schema_version}")
    if report.latest_config_version:
        click.echo(f"Latest config version: {report.latest_config_version}")
        click.echo(f"Latest checksum: {report.latest_checksum}")


@container.command("audit")
@click.option("--id", "container_id", required=True)
@click.option("--limit", type=int, default=None, help="Return only the newest N events.")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def container_audit(container_id, limit, org_id, home, as_json):
    """Show the append-only local audit trail for a container."""
    events = _control_service(str(home) if home else None).list_audit_events(
        container_id, limit=limit, org_id=org_id
    )
    if as_json:
        _print_json([event.to_dict() for event in events])
        return
    if not events:
        click.echo("No audit events.")
        return
    for event in events:
        target = event.config_version or "-"
        click.echo(f"{event.created_at}\t{event.action}\t{event.result}\t{event.actor}\t{target}")
        if event.details:
            click.echo(
                "  " + ", ".join(f"{key}={value}" for key, value in sorted(event.details.items()))
            )


@main.group()
def environment() -> None:
    """Manage deployment targets and explicit activation."""


@environment.command("create")
@click.argument("container_id")
@click.option("--name", required=True)
@click.option("--protected", is_flag=True, help="Require explicit approval before activation.")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def environment_create(container_id, name, protected, org_id, home, as_json):
    """Create a named deployment target."""
    created = _control_service(str(home) if home else None).create_environment(
        container_id, name, protected=protected, org_id=org_id
    )
    if as_json:
        _print_json(created.to_dict())
    else:
        click.echo(
            f"Created environment {created.name} ({created.environment_id})"
            + (" [protected]" if created.protected else "")
        )


@environment.command("list")
@click.argument("container_id")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def environment_list(container_id, org_id, home, as_json):
    """List deployment targets in a container."""
    environments = _control_service(str(home) if home else None).list_environments(
        container_id, org_id=org_id
    )
    if as_json:
        _print_json([item.to_dict() for item in environments])
        return
    if not environments:
        click.echo("No environments.")
        return
    for item in environments:
        click.echo(
            f"{item.name}\t{item.environment_id}\t"
            f"{item.current_config_version or '-'}\t"
            f"{'protected' if item.protected else 'open'}"
        )


@environment.command("activate")
@click.argument("container_id")
@click.argument("environment_ref")
@click.option("--config-version", default=None, help="Defaults to the latest revision.")
@click.option("--expected-current", default=None, help="Guard against stale activation.")
@click.option("--allow-protected", is_flag=True, help="Approve activation of a protected target.")
@click.option("--actor", default="local", show_default=True)
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def environment_activate(
    container_id,
    environment_ref,
    config_version,
    expected_current,
    allow_protected,
    actor,
    org_id,
    home,
    as_json,
):
    """Point an environment at a validated immutable revision."""
    result = _control_service(str(home) if home else None).activate_environment(
        container_id,
        environment_ref,
        config_version=config_version,
        expected_current=expected_current,
        allow_protected=allow_protected,
        org_id=org_id,
        activated_by=actor,
    )
    if as_json:
        _print_json(result.to_dict())
        return
    if not result.changed:
        click.echo(
            f"Environment {result.environment.name} already active at "
            f"{result.environment.current_config_version}."
        )
        return
    click.echo(
        f"Activated {result.environment.name} at "
        f"{result.environment.current_config_version} "
        f"(previous: {result.previous_config_version or '-'})."
    )
    click.echo("No external deployment was performed.")


@environment.command("rollback")
@click.argument("container_id")
@click.argument("environment_ref")
@click.option("--expected-current", default=None, help="Guard against stale rollback.")
@click.option("--allow-protected", is_flag=True, help="Approve rollback of a protected target.")
@click.option("--actor", default="local", show_default=True)
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def environment_rollback(
    container_id,
    environment_ref,
    expected_current,
    allow_protected,
    actor,
    org_id,
    home,
    as_json,
):
    """Return an environment to its previous validated revision."""
    result = _control_service(str(home) if home else None).rollback_environment(
        container_id,
        environment_ref,
        expected_current=expected_current,
        allow_protected=allow_protected,
        org_id=org_id,
        rolled_back_by=actor,
    )
    if as_json:
        _print_json(result.to_dict())
        return
    click.echo(
        f"Rolled back {result.environment.name} to "
        f"{result.environment.current_config_version} "
        f"(previous: {result.previous_config_version or '-'})."
    )
    click.echo("No external deployment was performed.")


@main.group()
def config() -> None:
    """Manage immutable configuration revisions and exports."""


@config.command("revision-create")
@click.argument("container_id")
@click.option("--payload", "payload_path", type=click.Path(), default=None)
@click.option("--expected-parent", default=None)
@click.option("--notes", default="")
@click.option(
    "--status",
    type=click.Choice(["draft", "validated", "published", "archived"]),
    default="draft",
    show_default=True,
)
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def config_revision_create(
    container_id,
    payload_path,
    expected_parent,
    notes,
    status,
    org_id,
    home,
    as_json,
):
    """Create an immutable configuration revision."""
    revision = _control_service(str(home) if home else None).create_revision(
        container_id,
        _load_payload(payload_path),
        org_id=org_id,
        expected_parent=expected_parent,
        notes=notes,
        status=status,
    )
    if as_json:
        _print_json(revision.to_dict())
    else:
        click.echo(f"Created config revision {revision.config_version}.")
        click.echo(f"Revision number: {revision.revision_number}")
        click.echo(f"Checksum: {revision.checksum}")


@config.command("revision-list")
@click.argument("container_id")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def config_revision_list(container_id, org_id, home, as_json):
    """List immutable configuration revisions."""
    revisions = _control_service(str(home) if home else None).list_revisions(
        container_id, org_id=org_id
    )
    if as_json:
        _print_json([revision.to_dict() for revision in revisions])
        return
    if not revisions:
        click.echo("No revisions.")
        return
    for revision in revisions:
        click.echo(
            f"{revision.revision_number}\t{revision.config_version}\t"
            f"{revision.status}\t{revision.checksum}"
        )


@config.command("revision-show")
@click.argument("container_id")
@click.argument("config_version")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def config_revision_show(container_id, config_version, org_id, home, as_json):
    """Show one configuration revision."""
    revision = _control_service(str(home) if home else None).get_revision(
        container_id, config_version, org_id=org_id
    )
    if as_json:
        _print_json(revision.to_dict())
        return
    click.echo(f"Config version: {revision.config_version}")
    click.echo(f"Container: {revision.container_id}")
    click.echo(f"Revision: {revision.revision_number}")
    click.echo(f"Status: {revision.status}")
    click.echo(f"Checksum: {revision.checksum}")
    click.echo(f"Parent: {revision.parent_config_version or '-'}")
    click.echo(f"Objects: {revision.payload.object_count()}")


@config.command("diff")
@click.argument("container_id")
@click.option("--from", "from_version", default=None, help="Base revision (defaults to parent).")
@click.option("--to", "to_version", default=None, help="Target revision (defaults to latest).")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def config_diff(container_id, from_version, to_version, org_id, home, as_json):
    """Diff two immutable revisions by object identity."""
    diff = _control_service(str(home) if home else None).diff_revisions(
        container_id,
        from_version=from_version,
        to_version=to_version,
        org_id=org_id,
    )
    if as_json:
        _print_json(diff.to_dict())
        return
    click.echo(
        f"Revision {diff.from_revision_number} -> {diff.to_revision_number} "
        f"({diff.from_config_version} -> {diff.to_config_version})"
    )
    if diff.identical:
        click.echo("No object changes.")
        return
    click.echo("Summary: " + ", ".join(f"{key}={value}" for key, value in diff.summary.items()))
    markers = {"added": "+", "removed": "-", "changed": "~"}
    for change in diff.changes:
        suffix = f" ({', '.join(change.fields)})" if change.fields else ""
        click.echo(f"{markers[change.change]} {change.object_type} {change.object_id}{suffix}")


@config.command("export")
@click.argument("container_id")
@click.option("--org", "org_id", default=None)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@_control_command
def config_export(container_id, org_id, output_path, home):
    """Export a container and its immutable revisions as JSON."""
    document = _control_service(str(home) if home else None).export_container(
        container_id, org_id=org_id
    )
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")
        click.echo(f"Wrote container export to {output_path}")
    else:
        click.echo(text, nl=False)


@config.command("import")
@click.argument("export_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--as", "as_container_id", default=None, help="Import under a new container ID.")
@click.option("--name", default=None)
@click.option("--org", "org_id", default=None)
@click.option("--workspace", "workspace_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def config_import(
    export_path,
    as_container_id,
    name,
    org_id,
    workspace_id,
    home,
    as_json,
):
    """Import a previously exported container."""
    try:
        document = json.loads(export_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"export is not valid JSON: {exc}") from exc
    result = _control_service(str(home) if home else None).import_container(
        document,
        as_container_id=as_container_id,
        name=name,
        org_id=org_id,
        workspace_id=workspace_id,
    )
    if as_json:
        _print_json(
            {
                "container": result.container.to_dict(),
                "created": result.created,
                "revision_count": result.revision_count,
                "renamed_from": result.renamed_from,
            }
        )
    else:
        action = "Imported" if result.created else "Already present:"
        click.echo(
            f"{action} container {result.container.container_id} "
            f"with {result.revision_count} revision(s)."
        )


@config.command("validate")
@click.argument("container_id")
@click.option("--config-version", default=None)
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
@_control_command
def config_validate(ctx, container_id, config_version, org_id, home, as_json):
    """Validate references, adapters, conditions, and draft warnings."""
    report = _control_service(str(home) if home else None).validate_config(
        container_id, config_version=config_version, org_id=org_id
    )
    if as_json:
        _print_json(report.to_dict())
    else:
        click.echo("Configuration is valid." if report.valid else "Configuration is invalid.")
        for issue in report.errors:
            click.echo(f"ERROR {issue.code}: {issue.message}")
        for issue in report.warnings:
            click.echo(f"WARNING {issue.code}: {issue.message}")
        click.echo(
            "Objects: " + ", ".join(f"{key}={value}" for key, value in report.counts.items())
        )
    ctx.exit(0 if report.valid else 1)


@config.command("preview")
@click.argument("container_id")
@click.option("--event", "event_path", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--config-version", default=None)
@click.option("--consent", "consent_values", multiple=True, metavar="PURPOSE=BOOL")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def config_preview(
    container_id,
    event_path,
    config_version,
    consent_values,
    org_id,
    home,
    as_json,
):
    """Simulate one event through a revision. No traffic is sent."""
    event = _load_json_object(event_path, "event")
    trace = _control_service(str(home) if home else None).preview(
        container_id,
        event,
        config_version=config_version,
        org_id=org_id,
        consent=_parse_consent(consent_values),
    )
    if as_json:
        _print_json(trace)
        return
    click.echo("SIMULATION: no tag was executed and no traffic was sent.")
    click.echo(f"Event: {trace['event']['type']} / {trace['event']['name']}")
    click.echo(f"Variables resolved: {len(trace['variables'])}")
    click.echo(
        "Triggers matched: "
        + ", ".join(item["name"] for item in trace["triggers"] if item["matched"])
    )
    for tag in trace["tags"]:
        if tag["selected"]:
            click.echo(f"SELECTED {tag['name']} ({tag['type']})")
        else:
            click.echo(f"BLOCKED  {tag['name']}: {tag['blocked_reason']}")
    for error in trace["errors"]:
        click.echo(f"ERROR {error['tag_id']}: {error['error']}")


@config.command("draft-from-recommendations")
@click.argument("container_id")
@click.option(
    "--snapshot",
    "snapshot_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option("--adapter", "adapter_key", default="ga4_event", show_default=True)
@click.option("--destination-id", "destination_ids", multiple=True)
@click.option("--consent-purpose", default=None)
@click.option("--expected-parent", default=None)
@click.option("--notes", default="")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def config_draft_from_recommendations(
    container_id,
    snapshot_path,
    adapter_key,
    destination_ids,
    consent_purpose,
    expected_parent,
    notes,
    org_id,
    home,
    as_json,
):
    """Create an explicit draft revision from crawl recommendations."""
    document = _load_json_object(snapshot_path, "snapshot")
    recommendations = _flatten_snapshot_recommendations(document, snapshot_path)
    result = _control_service(str(home) if home else None).create_draft_from_recommendations(
        container_id,
        recommendations,
        adapter_key=adapter_key,
        destination_ids=destination_ids,
        consent_purpose=consent_purpose,
        expected_parent=expected_parent,
        notes=notes,
        org_id=org_id,
    )
    if as_json:
        _print_json(result.to_dict())
        return
    click.echo(f"Created draft revision {result.revision.config_version}.")
    click.echo(f"Tags: {result.tag_count}; triggers: {result.trigger_count}")
    for warning in result.warnings:
        click.echo(f"WARNING: {warning}")


def _write_private_text(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    except Exception:
        os.close(descriptor)
        raise
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


@config.command("pytagshield-export")
@click.argument("container_id")
@click.option("--config-version", default=None)
@click.option(
    "--pseudonymize-salt",
    envvar="PYTAGSHIELD_PSEUDONYMIZE_SALT",
    required=True,
    help="Required by PyTagShield when pseudonymize_ids is enabled (default). "
    "Use the PYTAGSHIELD_PSEUDONYMIZE_SALT environment variable to avoid shell history.",
)
@click.option(
    "--default-policy",
    type=click.Choice(["deny", "allow"]),
    default="deny",
    show_default=True,
)
@click.option(
    "--validate/--no-validate",
    "validate",
    default=True,
    show_default=True,
    help="Validate the generated document with PyTagShield when the package is installed.",
)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.pass_context
@_control_command
def config_pytagshield_export(
    ctx,
    container_id,
    config_version,
    pseudonymize_salt,
    default_policy,
    validate,
    output_path,
    org_id,
    home,
):
    """Project a revision into a PyTagShield-compatible YAML/JSON document.

    Only event-name routing is projected. Unsupported triggers, destinations,
    and tag parameters are reported instead of being silently dropped.
    """
    home_path = str(home) if home else None

    def resolver(reference: str) -> str:
        return resolve_secret_ref(reference, home=home_path)

    result = _control_service(home_path).export_pytagshield(
        container_id,
        pseudonymize_salt=pseudonymize_salt,
        config_version=config_version,
        default_policy=default_policy,
        secret_resolver=resolver,
        org_id=org_id,
    )
    for issue in result.warnings:
        click.echo(f"WARNING {issue.code}: {issue.message}", err=True)
    for issue in result.errors:
        click.echo(f"ERROR {issue.code}: {issue.message}", err=True)
    if not result.exportable:
        ctx.exit(1)

    text = result.to_yaml_compatible_json()
    if validate:
        valid, messages = validate_with_pytagshield(result.config)
        if valid is False:
            click.echo("ERROR pytagshield_validation_failed: " + "; ".join(messages), err=True)
            ctx.exit(1)
        if valid is True:
            click.echo("PyTagShield validated the generated configuration.", err=True)
        else:
            click.echo(
                "PyTagShield is not installed here; skipped native validation.",
                err=True,
            )

    if output_path:
        _write_private_text(Path(output_path), text)
        click.echo(
            f"Wrote PyTagShield configuration to {output_path} "
            "(mode 0600; contains resolved credentials).",
            err=True,
        )
    else:
        click.echo(text, nl=False)
        click.echo(
            "Configuration may contain resolved credentials; write it to a protected file.",
            err=True,
        )


def _cdn_root(home: str | None, root: str | None) -> Path:
    if root:
        return Path(root).expanduser()
    base = Path(home).expanduser() if home else FileStore().root
    return base / "cdn"


def _cdn_publish(
    service,
    root: Path,
    container_id,
    environment_ref,
    *,
    org_id,
    base_url,
    sdk_version,
    sdk_asset,
    default_consent,
    allow_protected,
):
    publisher = FilesystemCDN(
        root,
        base_url=base_url,
        sdk_version=sdk_version,
        sdk_asset=sdk_asset,
    )
    return publisher.publish_environment(
        service,
        container_id,
        environment_ref,
        org_id=org_id,
        default_consent=default_consent,
        allow_protected=allow_protected,
    )


@main.group()
def cdn() -> None:
    """Publish immutable container configuration and SDK assets for a CDN."""


@cdn.command("publish")
@click.argument("container_id")
@click.argument("environment_ref")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option(
    "--root",
    "root_path",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="CDN output directory (default: HOME/cdn).",
)
@click.option("--base-url", default=None, help="Public base URL used in generated links.")
@click.option("--sdk-version", default="0.1.0", show_default=True)
@click.option("--sdk-asset", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--default-consent", "default_consent", multiple=True, metavar="PURPOSE=true|false")
@click.option(
    "--allow-protected",
    is_flag=True,
    help="Explicitly approve publishing a protected environment.",
)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def cdn_publish(
    container_id,
    environment_ref,
    org_id,
    home,
    root_path,
    base_url,
    sdk_version,
    sdk_asset,
    default_consent,
    allow_protected,
    as_json,
):
    """Publish the environment's active revision as immutable CDN artifacts."""
    home_path = str(home) if home else None
    result = _cdn_publish(
        _control_service(home_path),
        _cdn_root(home_path, str(root_path) if root_path else None),
        container_id,
        environment_ref,
        org_id=org_id,
        base_url=base_url,
        sdk_version=sdk_version,
        sdk_asset=sdk_asset,
        default_consent=_parse_consent(default_consent) or None,
        allow_protected=allow_protected,
    )
    if as_json:
        _print_json(result.to_dict())
        return
    click.echo(
        f"Published {result.container_id} / {result.environment} at {result.config_version}."
    )
    click.echo(f"Config: {result.config_url}")
    click.echo(f"Latest pointer: {result.latest_url}")
    click.echo(f"Manifest: {result.manifest_path}")
    click.echo(f"Integrity: sha256:{result.integrity_digest}")
    click.echo("No external CDN or vendor account was modified.")


@cdn.command("verify")
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option(
    "--root",
    "root_path",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def cdn_verify(home, root_path, as_json):
    """Verify published file hashes, config integrity, and latest pointers."""
    publisher = FilesystemCDN(
        _cdn_root(str(home) if home else None, str(root_path) if root_path else None)
    )
    issues = publisher.verify()
    if as_json:
        _print_json({"valid": not issues, "issues": issues})
    elif issues:
        for problem in issues:
            click.echo(f"{problem['path']}: {problem['message']}", err=True)
    else:
        click.echo("CDN publication tree is valid.")
    if issues:
        raise click.ClickException(f"{len(issues)} CDN verification failure(s)")


@cdn.command("status")
@click.argument("container_id")
@click.argument("environment_ref")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option(
    "--root",
    "root_path",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def cdn_status(container_id, environment_ref, org_id, home, root_path, as_json):
    """Show the locally published state of one environment."""
    home_path = str(home) if home else None
    service = _control_service(home_path)
    container = service.get_container(container_id, org_id=org_id)
    publisher = FilesystemCDN(_cdn_root(home_path, str(root_path) if root_path else None))
    manifest = publisher.read_manifest(container_id, environment_ref, org_id=container.org_id)
    if as_json:
        _print_json(manifest)
        return
    environment = manifest.get("environment", {})
    click.echo(f"Container: {manifest.get('container_id')}")
    click.echo(f"Environment: {environment.get('name')} ({environment.get('slug')})")
    click.echo(f"Current config: {manifest.get('current_config_version')}")
    click.echo(f"Published at: {manifest.get('published_at')}")
    for revision in manifest.get("revisions", []):
        click.echo(
            f"{revision.get('revision_number')}\t{revision.get('config_version')}\t"
            f"{revision.get('file_sha256')}"
        )


@cdn.command("rollback")
@click.argument("container_id")
@click.argument("environment_ref")
@click.option("--expected-current", default=None)
@click.option("--allow-protected", is_flag=True)
@click.option("--actor", default="local", show_default=True)
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option(
    "--root",
    "root_path",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
)
@click.option("--base-url", default=None)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def cdn_rollback(
    container_id,
    environment_ref,
    expected_current,
    allow_protected,
    actor,
    org_id,
    home,
    root_path,
    base_url,
    as_json,
):
    """Roll an environment back and publish the prior revision.

    The control-plane rollback and CDN publication are separate writes; if
    publication fails, re-run ``cdn publish`` after resolving the error.
    """
    home_path = str(home) if home else None
    service = _control_service(home_path)
    activation = service.rollback_environment(
        container_id,
        environment_ref,
        expected_current=expected_current,
        allow_protected=allow_protected,
        org_id=org_id,
        rolled_back_by=actor,
    )
    result = _cdn_publish(
        service,
        _cdn_root(home_path, str(root_path) if root_path else None),
        container_id,
        environment_ref,
        org_id=org_id,
        base_url=base_url,
        sdk_version="0.1.0",
        sdk_asset=None,
        default_consent=None,
        allow_protected=allow_protected,
    )
    if as_json:
        _print_json({"activation": activation.to_dict(), "publication": result.to_dict()})
        return
    click.echo(
        f"Rolled back {result.environment} to {result.config_version} and republished "
        f"{result.latest_url}."
    )
    click.echo("No external CDN or vendor account was modified.")


@cdn.command("write-cache-policy")
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option(
    "--root",
    "root_path",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
)
def cdn_write_cache_policy(home, root_path):
    """Write a self-hosting cache-policy note into the CDN tree."""
    path = write_static_server_config(
        _cdn_root(str(home) if home else None, str(root_path) if root_path else None)
    )
    click.echo(f"Wrote {path}")


@main.command("serve-ingest")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", type=click.IntRange(0, 65535), default=8080, show_default=True)
@click.option(
    "--container",
    "containers",
    multiple=True,
    help="Allowed public container ID (repeatable).",
)
@click.option(
    "--pytagshield-url",
    default=None,
    help="Forward accepted events to this PyTagShield base URL.",
)
@click.option(
    "--pytagshield-token-ref",
    default=None,
    help="Secret reference for PyTagShield bearer auth (env:NAME or file:PATH).",
)
@click.option(
    "--allow-private-pytagshield",
    is_flag=True,
    help="Allow a private/loopback PyTagShield URL; use only for intentional self-hosting.",
)
@click.option("--pytagshield-timeout", type=float, default=5.0, show_default=True)
@click.option(
    "--rate-limit-per-minute",
    type=click.IntRange(1, 1_000_000),
    default=120,
    show_default=True,
)
@click.option(
    "--max-body-bytes",
    type=click.IntRange(1, 10_000_000),
    default=65_536,
    show_default=True,
)
@click.option("--max-batch-events", type=click.IntRange(1, 100), default=100, show_default=True)
@click.option(
    "--dedupe-ttl-seconds",
    type=click.IntRange(1, 31_536_000),
    default=86_400,
    show_default=True,
)
@click.option(
    "--dedupe-claim-ttl-seconds",
    type=click.IntRange(1, 3_600),
    default=60,
    show_default=True,
    help="How long an in-flight claim blocks retries before it can be reclaimed.",
)
@click.option(
    "--dedupe-db",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Persist event-id claims in this SQLite file for restart/cross-process dedupe.",
)
@click.option(
    "--api-token-ref",
    default=None,
    help="Optional server-to-server API token secret reference; not for browser SDKs.",
)
@click.option(
    "--allow-origin",
    "origins",
    multiple=True,
    help="Allowed CORS origin (repeatable; default *).",
)
@click.option(
    "--trusted-proxy-cidr",
    "trusted_proxy_cidrs",
    multiple=True,
    help="Trust forwarding headers only from this proxy CIDR (repeatable).",
)
@click.option(
    "--real-ip-header",
    default="X-Forwarded-For",
    show_default=True,
    help="Header used for rate-limit identity when the direct peer is a trusted proxy.",
)
@click.option(
    "--path",
    "collection_path",
    default="/api/v1/events",
    show_default=True,
    help="Public collection path, e.g. /collect for same-origin routing.",
)
@click.option("--tls-cert", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--tls-key", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@_control_command
def serve_ingest(
    host,
    port,
    containers,
    pytagshield_url,
    pytagshield_token_ref,
    allow_private_pytagshield,
    pytagshield_timeout,
    rate_limit_per_minute,
    max_body_bytes,
    max_batch_events,
    dedupe_ttl_seconds,
    dedupe_claim_ttl_seconds,
    dedupe_db,
    api_token_ref,
    origins,
    trusted_proxy_cidrs,
    real_ip_header,
    collection_path,
    tls_cert,
    tls_key,
    home,
):
    """Run a self-hosted event collection endpoint.

    Accepted events are validated and deduplicated here. Destination policy
    remains in PyTagShield; without --pytagshield-url this endpoint only
    acknowledges validated events and does not forward them.
    """
    from pytagmanager.ingest import (
        IngestConfig,
        IngestService,
        PyTagShieldClient,
        make_ssl_context,
        serve,
    )

    if (tls_cert is None) != (tls_key is None):
        raise click.ClickException("--tls-cert and --tls-key must be supplied together")
    if host not in {"127.0.0.1", "::1", "localhost"} and tls_cert is None:
        click.echo(
            "WARNING: listening beyond loopback without TLS; terminate HTTPS at a "
            "reverse proxy and never expose this endpoint over plaintext.",
            err=True,
        )
    home_path = str(home) if home else None
    forwarder = None
    if pytagshield_url:
        forwarder = PyTagShieldClient(
            pytagshield_url,
            token_ref=pytagshield_token_ref,
            home=home_path,
            timeout_seconds=pytagshield_timeout,
            allow_private_networks=allow_private_pytagshield,
        )
    try:
        config = IngestConfig(
            allowed_containers=frozenset(containers) if containers else None,
            max_body_bytes=max_body_bytes,
            max_batch_events=max_batch_events,
            dedupe_ttl_seconds=dedupe_ttl_seconds,
            dedupe_claim_ttl_seconds=dedupe_claim_ttl_seconds,
            dedupe_store_path=str(dedupe_db) if dedupe_db else None,
            rate_limit_per_minute=rate_limit_per_minute,
            api_token_ref=api_token_ref,
            cors_origins=tuple(origins) if origins else ("*",),
            trusted_proxy_cidrs=trusted_proxy_cidrs,
            real_ip_header=real_ip_header,
            path=collection_path,
            home=home_path,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    try:
        service = IngestService(config, forwarder=forwarder)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    ssl_context = make_ssl_context(str(tls_cert), str(tls_key)) if tls_cert else None
    scheme = "https" if ssl_context else "http"
    click.echo(f"Collection endpoint listening at {scheme}://{host}:{port}{collection_path}")
    click.echo(f"Dedupe backend: {service.dedupe.backend}")
    click.echo(
        "Forwarding to PyTagShield."
        if forwarder
        else "No forwarder configured; validated events are acknowledged but not delivered."
    )
    click.echo("Press Ctrl-C to stop.", err=True)
    try:
        serve(service, host=host, port=port, ssl_context=ssl_context)
    except KeyboardInterrupt:
        click.echo("Stopped.")


@main.group()
def squid() -> None:
    """Emit the proposed Squid-CRM findings contract and write plan."""


@squid.command("manifest")
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
)
def squid_manifest(output_path):
    """Print the versioned tagManagerFinding object/field manifest."""
    from pytagmanager.squid import build_finding_manifest

    text = json.dumps(build_finding_manifest(), indent=2, sort_keys=True, ensure_ascii=False)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
        click.echo(f"Wrote Squid finding manifest to {output_path}")
    else:
        click.echo(text)


@squid.command("findings")
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="A diagnose --format json report.",
)
@click.option(
    "--workspace-id",
    default=None,
    help="Optional Squid workspace UUID for the plan metadata.",
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
)
def squid_findings(input_path, workspace_id, output_path):
    """Map a diagnose JSON report to Squid finding records and a write plan.

    This emits data only. It does not call Squid, create metadata or write records.
    """
    from pytagmanager.squid import SquidContractError, build_findings_plan

    try:
        report = json.loads(input_path.read_text(encoding="utf-8"))
        plan = build_findings_plan(report, workspace_id=workspace_id)
    except (OSError, json.JSONDecodeError, SquidContractError) as exc:
        raise click.ClickException(str(exc)) from exc
    text = json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
        click.echo(f"Wrote Squid finding plan to {output_path}")
    else:
        click.echo(text)


@main.group()
def cmp() -> None:
    """Audit consent-management evidence without claiming legal compliance."""


@cmp.command("audit")
@click.argument("url")
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option(
    "--browser",
    type=click.Choice(["chromium", "firefox", "webkit"]),
    default="chromium",
    show_default=True,
)
@click.option(
    "--adapter-file",
    "adapter_files",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    metavar="PATH",
    help="Declarative JSON adapter file for an unsupported CMP. Repeatable; does not execute code.",
)
@click.option(
    "--consent-action",
    type=click.Choice(["none", "accept", "reject"]),
    default="none",
    show_default=True,
    help="Optionally exercise one consent control. Requires --authorize-consent-interaction.",
)
@click.option(
    "--accept-selector",
    multiple=True,
    help="Explicit selector for the accept control. Repeatable; overrides adapter defaults.",
)
@click.option(
    "--reject-selector",
    multiple=True,
    help="Explicit selector for the reject control. Repeatable; overrides adapter defaults.",
)
@click.option(
    "--authorize-consent-interaction",
    is_flag=True,
    help="Explicitly authorize clicking one consent control in a test environment you control. "
    "Without this flag, PyTagManager never submits a consent choice.",
)
@click.option(
    "--wait",
    "wait_seconds",
    default=1.0,
    show_default=True,
    type=float,
    help="Seconds to wait after a consent interaction before reading state/network evidence.",
)
@click.option("--selector-timeout-ms", default=5000, show_default=True, type=int)
@click.option(
    "--reload-after-consent",
    is_flag=True,
    help="Reload after the consent action to test whether the choice persisted.",
)
@click.option("--max-network-events", default=500, show_default=True, type=click.IntRange(1, 5000))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option(
    "-o",
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
)
def cmp_audit(
    url,
    headless,
    browser,
    adapter_files,
    consent_action,
    accept_selector,
    reject_selector,
    authorize_consent_interaction,
    wait_seconds,
    selector_timeout_ms,
    reload_after_consent,
    max_network_events,
    output_format,
    output_path,
):
    """Collect CMP, consent, and pre/post-choice evidence from one page.

    This is an evidence report, not a legal compliance determination. By
    default it never clicks or submits a consent choice; that requires both
    --consent-action and --authorize-consent-interaction.
    """
    from pytagmanager.cmp import (
        AdapterFileError,
        CmpAuditAuthorizationError,
        CmpAuditOptions,
        CmpAuditRunner,
        load_adapter_files,
        render_cmp_audit_report,
    )

    try:
        extra_adapters = load_adapter_files(adapter_files) if adapter_files else ()
    except AdapterFileError as exc:
        raise click.UsageError(str(exc)) from exc

    options = CmpAuditOptions(
        headless=headless,
        browser_name=browser,
        accept_selectors=accept_selector,
        reject_selectors=reject_selector,
        wait_seconds=wait_seconds,
        selector_timeout_ms=selector_timeout_ms,
        reload_after_consent=reload_after_consent,
        max_network_events=max_network_events,
        extra_adapters=extra_adapters,
    )
    try:
        report = CmpAuditRunner(options).run(
            url,
            consent_action=consent_action,
            authorize_consent_interaction=authorize_consent_interaction,
        )
    except CmpAuditAuthorizationError as exc:
        raise click.UsageError(str(exc)) from exc
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        text = json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
    else:
        text = render_cmp_audit_report(report)
    if output_path:
        output_path.write_text(text + "\n", encoding="utf-8")
        click.echo(f"Wrote CMP audit report to {output_path}")
    else:
        click.echo(text)


@main.group()
def gtm() -> None:
    """Inspect and convert Google Tag Manager container exports."""


@gtm.command("inspect")
@click.argument("container_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), default=None)
def gtm_inspect(container_file, output_format, output):
    """Explain likely GTM configuration faults from an exported container."""
    document = load_container(container_file)
    findings = analyze_container(document)
    payload = {
        "container_file": str(container_file),
        "finding_count": len(findings),
        "findings": [finding.to_dict() for finding in findings],
    }
    if output_format == "json":
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
        if output:
            output.write_text(text + "\n", encoding="utf-8")
        else:
            click.echo(text)
        return
    if output:
        output.write_text(_render_gtm_findings(findings) + "\n", encoding="utf-8")
        return
    click.echo(_render_gtm_findings(findings))


def _render_gtm_findings(findings) -> str:
    if not findings:
        return "No deterministic GTM configuration findings."
    lines = [f"{len(findings)} GTM configuration finding(s):"]
    for finding in findings:
        lines.append(
            f"[{finding.severity.upper()}/{finding.confidence}] {finding.code}: {finding.message}"
        )
        for evidence in finding.evidence:
            lines.append(f"  evidence: {evidence}")
        lines.append(f"  remediation: {finding.remediation}")
    return "\n".join(lines)


@gtm.command("export")
@click.argument("container_id")
@click.option("--config-version", default=None)
@click.option("-o", "--output", type=click.Path(dir_okay=False, path_type=Path), required=True)
@click.option("--format", "output_format", type=click.Choice(["json", "yaml"]), default=None)
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@_control_command
def gtm_export(container_id, config_version, output, output_format, org_id, home):
    """Export a managed revision as a GTM-compatible container snapshot."""
    service = _control_service(str(home) if home else None)
    if config_version:
        revision = service.get_revision(container_id, config_version, org_id=org_id)
    else:
        revisions = service.list_revisions(container_id, org_id=org_id)
        if not revisions:
            raise click.ClickException("container has no revisions to export")
        revision = revisions[-1]
    document = payload_to_gtm(revision.payload)
    write_container(document, output, format=output_format)
    click.echo(f"Wrote GTM container snapshot from revision {revision.config_version} to {output}.")


@gtm.command("import")
@click.argument("container_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("container_id")
@click.option("--org", "org_id", default=None)
@click.option("--home", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--notes", default="Imported from GTM export", show_default=True)
@click.option("--json", "as_json", is_flag=True)
@_control_command
def gtm_import(container_file, container_id, org_id, home, notes, as_json):
    """Create a draft revision from a GTM JSON/YAML container export.

    The import is best-effort and never activates the revision. Unsupported
    trigger conditions and variables are reported instead of being silently
    reinterpreted.
    """
    service = _control_service(str(home) if home else None)
    document = load_container(container_file)
    payload, warnings = gtm_to_payload(document)
    revision = service.create_revision(
        container_id,
        payload,
        org_id=org_id,
        notes=notes,
    )
    result = {
        "container_id": container_id,
        "config_version": revision.config_version,
        "revision_number": revision.revision_number,
        "object_counts": {
            "tags": len(payload.tags),
            "triggers": len(payload.triggers),
            "variables": len(payload.variables),
        },
        "warnings": warnings,
        "activated": False,
    }
    if as_json:
        _print_json(result)
        return
    click.echo(
        f"Imported draft revision {revision.config_version} with "
        f"{len(payload.tags)} tag(s), {len(payload.triggers)} trigger(s), "
        f"{len(payload.variables)} variable(s). Not activated."
    )
    for warning in warnings:
        click.echo(f"WARNING {warning}", err=True)


if __name__ == "__main__":
    main()
