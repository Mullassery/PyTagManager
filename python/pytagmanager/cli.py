from __future__ import annotations

import json

import click

from pytagmanager.discovery.crawl import crawl_site
from pytagmanager.export.gtm import build_gtm_container, export_gtm_json
from pytagmanager.recommend.heuristics import recommend_for_graph


@click.group()
def main() -> None:
    """PyTagManager: AI-native analytics implementation platform (v1: crawl -> DOM graph -> recommend -> export)."""


@main.command()
@click.argument("url")
@click.option("--max-pages", default=50, show_default=True, type=int)
@click.option("--concurrency", default=10, show_default=True, type=int)
@click.option("--no-robots", is_flag=True, help="Ignore robots.txt")
@click.option("--export", "export_format", type=click.Choice(["gtm"]), default=None)
@click.option("-o", "--output", "output_path", type=click.Path(), default=None)
def crawl(
    url: str,
    max_pages: int,
    concurrency: int,
    no_robots: bool,
    export_format: str | None,
    output_path: str | None,
) -> None:
    """Crawl URL, generate rule-based tracking recommendations, and optionally export them."""
    click.echo(f"Crawling {url} (max_pages={max_pages}, concurrency={concurrency})...")
    pages = crawl_site(url, max_pages=max_pages, concurrency=concurrency, respect_robots=not no_robots)
    click.echo(f"Crawled {len(pages)} page(s).")

    all_recs = []
    for page in pages:
        recs = recommend_for_graph(page.graph)
        all_recs.extend(recs)
        click.echo(f"  {page.url} [{page.status}] -> {len(recs)} recommendation(s)")

    click.echo(f"\nTotal recommendations: {len(all_recs)}")
    for rec in all_recs[:20]:
        click.echo(f"  - {rec.event_name} ({rec.business_objective}, confidence={rec.confidence}) via {rec.selector}")
    if len(all_recs) > 20:
        click.echo(f"  ... and {len(all_recs) - 20} more")

    if export_format == "gtm":
        if output_path:
            export_gtm_json(all_recs, output_path)
            click.echo(f"\nExported GTM container to {output_path}")
        else:
            click.echo(json.dumps(build_gtm_container(all_recs), indent=2))


if __name__ == "__main__":
    main()
