use pyo3::prelude::*;
use scraper::{Html, Selector};
use std::collections::VecDeque;
use std::sync::Arc;
use url::Url;

use crate::crawler::fetcher::Fetcher;
use crate::crawler::frontier::Frontier;
use crate::crawler::robots::RobotsRules;
use crate::crawler::sitemap::{parse_sitemap, SitemapContent};
use crate::dom::graph::SemanticGraph;
use crate::dom::parser::parse_html;
use crate::error::AppError;

/// One crawled page: HTTP result plus its precomputed semantic DOM graph.
#[pyclass]
#[derive(Clone)]
pub struct Page {
    #[pyo3(get)]
    pub url: String,
    #[pyo3(get)]
    pub status: u16,
    #[pyo3(get)]
    pub graph: SemanticGraph,
}

#[pymethods]
impl Page {
    fn __repr__(&self) -> String {
        format!(
            "Page(url='{}', status={}, nodes={})",
            self.url,
            self.status,
            self.graph.nodes.len()
        )
    }
}

pub async fn crawl(
    start_url: &str,
    max_pages: usize,
    concurrency: usize,
    respect_robots: bool,
) -> Result<Vec<Page>, AppError> {
    crawl_with_fetcher(
        Fetcher::new(),
        start_url,
        max_pages,
        concurrency,
        respect_robots,
    )
    .await
}

/// Same as `crawl`, but with an explicit `Fetcher`. `crawl` above is the
/// only real (CLI/Python-facing) entry point and always passes
/// `Fetcher::new()`, which has the SSRF guard enabled. This variant is
/// exposed so integration tests can pass a `Fetcher::with_ssrf_guard(false)`
/// to exercise the BFS/batching loop against a local mock HTTP server on
/// loopback, which the guard would otherwise correctly refuse to fetch.
pub async fn crawl_with_fetcher(
    fetcher: Fetcher,
    start_url: &str,
    max_pages: usize,
    concurrency: usize,
    respect_robots: bool,
) -> Result<Vec<Page>, AppError> {
    let fetcher = Arc::new(fetcher);
    let mut frontier = Frontier::new(start_url, max_pages)?;
    let base = Url::parse(start_url)?;

    let robots = if respect_robots {
        let robots_url = base.join("/robots.txt")?;
        match fetcher.fetch_optional(robots_url.as_str()).await {
            Some(page) => RobotsRules::parse(&page.body),
            None => RobotsRules::allow_all(),
        }
    } else {
        RobotsRules::allow_all()
    };

    if let Ok(sitemap_url) = base.join("/sitemap.xml") {
        seed_from_sitemap(&fetcher, sitemap_url.as_str(), &mut frontier).await;
    }

    let link_selector = Selector::parse("a[href]").expect("static selector is valid");
    let batch_size = concurrency.max(1);
    let mut results: Vec<Page> = Vec::new();

    while frontier.has_capacity() {
        let mut batch = Vec::new();
        while batch.len() < batch_size {
            match frontier.pop() {
                Some(url) => {
                    if robots.is_allowed(&path_of(&url)) {
                        batch.push(url);
                    }
                }
                None => break,
            }
        }
        if batch.is_empty() {
            break;
        }

        let fetches = batch.into_iter().map(|url| {
            let fetcher = Arc::clone(&fetcher);
            async move { fetcher.fetch(&url).await.ok() }
        });
        let fetched_pages = futures::future::join_all(fetches).await;

        for fetched in fetched_pages.into_iter().flatten() {
            let graph = parse_html(&fetched.body, &fetched.url);

            if let Ok(base_url) = Url::parse(&fetched.url) {
                let document = Html::parse_document(&fetched.body);
                for el in document.select(&link_selector) {
                    if let Some(href) = el.value().attr("href") {
                        if let Ok(joined) = base_url.join(href) {
                            frontier.push(joined.as_str());
                        }
                    }
                }
            }

            results.push(Page {
                url: fetched.url,
                status: fetched.status,
                graph,
            });
        }
    }

    Ok(results)
}

async fn seed_from_sitemap(fetcher: &Fetcher, start_sitemap_url: &str, frontier: &mut Frontier) {
    const MAX_SITEMAP_DEPTH: u8 = 3;
    let mut queue = VecDeque::new();
    queue.push_back((start_sitemap_url.to_string(), 0u8));

    while let Some((sitemap_url, depth)) = queue.pop_front() {
        if depth > MAX_SITEMAP_DEPTH {
            continue;
        }
        let Some(page) = fetcher.fetch_optional(&sitemap_url).await else {
            continue;
        };
        match parse_sitemap(&page.body) {
            Some(SitemapContent::UrlSet(urls)) => {
                for u in urls {
                    frontier.push(&u);
                }
            }
            Some(SitemapContent::Index(subs)) => {
                for sub in subs {
                    queue.push_back((sub, depth + 1));
                }
            }
            None => {}
        }
    }
}

fn path_of(url: &str) -> String {
    Url::parse(url)
        .map(|u| u.path().to_string())
        .unwrap_or_else(|_| "/".to_string())
}
