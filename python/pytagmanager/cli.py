from __future__ import annotations

import json

import click

from pytagmanager.discovery.crawl import crawl_site
from pytagmanager.export.base import EXPORTERS
from pytagmanager.recommend.heuristics import recommend_for_graph
from pytagmanager.version_control.diff import diff_snapshots, format_diff_report
from pytagmanager.version_control.snapshot import build_snapshot, load_snapshot, save_snapshot


@click.group()
def main() -> None:
    """PyTagManager: AI-native analytics implementation platform (v1: crawl -> DOM graph -> recommend -> export)."""


@main.command()
@click.argument("url")
@click.option("--max-pages", default=50, show_default=True, type=int)
@click.option("--concurrency", default=10, show_default=True, type=int)
@click.option("--no-robots", is_flag=True, help="Ignore robots.txt")
@click.option("--export", "export_format", type=click.Choice(sorted(EXPORTERS)), default=None)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
@click.option(
    "--save-snapshot",
    "snapshot_path",
    type=click.Path(),
    default=None,
    help="Save this crawl (pages, DOM elements, recommendations) as a JSON snapshot for later `pytagmanager diff`.",
)
def crawl(
    url: str,
    max_pages: int,
    concurrency: int,
    no_robots: bool,
    export_format: str | None,
    output_path: str | None,
    snapshot_path: str | None,
) -> None:
    """Crawl URL, generate rule-based tracking recommendations, and optionally export them."""
    click.echo(f"Crawling {url} (max_pages={max_pages}, concurrency={concurrency})...")
    pages = crawl_site(url, max_pages=max_pages, concurrency=concurrency, respect_robots=not no_robots)
    click.echo(f"Crawled {len(pages)} page(s).")

    all_recs = []
    recs_by_url = {}
    for page in pages:
        recs = recommend_for_graph(page.graph)
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


if __name__ == "__main__":
    main()
