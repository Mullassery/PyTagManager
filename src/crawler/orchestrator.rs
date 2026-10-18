use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, RwLock};
use std::time::Duration;

use mudfish_browser::BrowserRenderer;
use mudfish_core::{CrawlConfig, NormalizationOptions, TrailingSlashPolicy};
use mudfish_fetch::{
    classify_status, detect_challenge, DomainHealthTracker, HttpFetcher, PolitenessManager,
    RobotsManager,
};
use mudfish_frontier::{DepthPriority, Frontier};
use mudfish_parser::static_html_looks_js_dependent;
use pyo3::prelude::*;
use scraper::{Html, Selector};
use tokio::sync::{Mutex, Semaphore};
use url::Url;

use crate::crawler::sitemap::{parse_sitemap, SitemapContent};
use crate::dom::graph::SemanticGraph;
use crate::dom::parser::parse_html;
use crate::error::AppError;

/// Effectively unbounded: `max_pages`/`max_urls` is the real cap this
/// crawler has ever offered (matching the pre-Mudfish `Frontier`'s
/// page-count-only budget), so `max_depth` only needs to be larger than
/// any depth a real `max_pages` crawl could reach before that cap bites.
const MAX_CRAWL_DEPTH: usize = 1_000;

/// How long a browser render waits after `load` for post-load XHR/fetch
/// activity (many analytics tags fire shortly after, not during, load).
const BROWSER_SETTLE: Duration = Duration::from_millis(800);

/// How a page's static HTML is used to decide whether to pay for a real
/// browser render.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BrowserMode {
    /// Never render -- the pre-existing, zero-overhead behavior.
    Off,
    /// Render only pages `static_html_looks_js_dependent` flags as a
    /// likely near-empty client-rendered shell.
    Auto,
    /// Render every HTML page.
    Always,
}

impl BrowserMode {
    pub fn parse(s: &str) -> Result<Self, AppError> {
        match s {
            "off" => Ok(BrowserMode::Off),
            "auto" => Ok(BrowserMode::Auto),
            "always" => Ok(BrowserMode::Always),
            other => Err(AppError::InvalidBrowserMode(other.to_string())),
        }
    }
}

/// A single captured network request/response, surfaced to Python only
/// when a page was rendered through a real browser (`mudfish_fetch`'s
/// plain HTTP path has no way to observe XHR/fetch calls a page's own JS
/// makes) -- see `BrowserMode`.
#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct NetworkRequest {
    #[pyo3(get)]
    pub url: String,
    #[pyo3(get)]
    pub method: String,
    #[pyo3(get)]
    pub resource_type: String,
    #[pyo3(get)]
    pub status: Option<i64>,
    #[pyo3(get)]
    pub mime_type: Option<String>,
}

impl From<mudfish_browser::NetworkRequestRecord> for NetworkRequest {
    fn from(r: mudfish_browser::NetworkRequestRecord) -> Self {
        Self {
            url: r.url,
            method: r.method,
            resource_type: r.resource_type,
            status: r.status,
            mime_type: r.mime_type,
        }
    }
}

#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct Cookie {
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub value: String,
    #[pyo3(get)]
    pub domain: String,
}

impl From<mudfish_browser::CookieRecord> for Cookie {
    fn from(c: mudfish_browser::CookieRecord) -> Self {
        Self {
            name: c.name,
            value: c.value,
            domain: c.domain,
        }
    }
}

/// One crawled page: HTTP result, its precomputed semantic DOM graph, a
/// structured crawl status, and (only when rendered through a real
/// browser) captured network activity and cookies.
#[pyclass(from_py_object)]
#[derive(Clone)]
pub struct Page {
    #[pyo3(get)]
    pub url: String,
    #[pyo3(get)]
    pub status: u16,
    #[pyo3(get)]
    pub graph: SemanticGraph,
    /// One of "success"/"throttled"/"blocked"/"challenged"/"failed" --
    /// see `mudfish_fetch::CrawlStatus`. Exposed as a plain string across
    /// the PyO3 boundary rather than a new enum-backed pyclass, matching
    /// this crate's existing convention of keeping Python-facing types
    /// simple.
    #[pyo3(get)]
    pub crawl_status: String,
    /// Whether this page's content came from a real browser render
    /// (`graph` reflects post-JS DOM) rather than the raw HTTP response.
    #[pyo3(get)]
    pub rendered: bool,
    /// Always empty unless `rendered` is true -- the plain HTTP fetch
    /// path has no way to observe a page's own XHR/fetch calls.
    #[pyo3(get)]
    pub network_requests: Vec<NetworkRequest>,
    #[pyo3(get)]
    pub cookies: Vec<Cookie>,
}

#[pymethods]
impl Page {
    fn __repr__(&self) -> String {
        format!(
            "Page(url='{}', status={}, crawl_status='{}', rendered={}, nodes={})",
            self.url,
            self.status,
            self.crawl_status,
            self.rendered,
            self.graph.nodes.len()
        )
    }
}

/// `rate_limit_per_sec` and `headers` configure the underlying Mudfish
/// `HttpFetcher` this builds -- rate limiting so crawling a production site
/// you don't control doesn't trip a WAF, and custom headers so
/// authenticated pages (behind a login cookie, a staging basic-auth
/// header, etc.) can be crawled at all. `browser_mode` is one of
/// "off"/"auto"/"always" -- see `BrowserMode`.
pub async fn crawl(
    start_url: &str,
    max_pages: usize,
    concurrency: usize,
    respect_robots: bool,
    rate_limit_per_sec: Option<f64>,
    headers: Vec<(String, String)>,
    browser_mode: &str,
) -> Result<Vec<Page>, AppError> {
    let config = build_config(
        max_pages,
        concurrency,
        respect_robots,
        rate_limit_per_sec,
        headers,
        false,
    );
    crawl_with_config(config, start_url, BrowserMode::parse(browser_mode)?).await
}

/// Builds the `mudfish_core::CrawlConfig` this crawler always runs with.
/// `allow_private_networks` is a parameter (rather than always `false`)
/// solely so integration tests can target a local mock server on loopback
/// -- see `crawl_with_config`'s doc comment for why that injection point is
/// safe (no real CLI/Python entry point can reach it with `true`).
pub fn build_config(
    max_pages: usize,
    concurrency: usize,
    respect_robots: bool,
    rate_limit_per_sec: Option<f64>,
    headers: Vec<(String, String)>,
    allow_private_networks: bool,
) -> CrawlConfig {
    let request_delay = rate_limit_per_sec
        .map(|r| Duration::from_secs_f64(1.0 / r.max(0.001)))
        .unwrap_or(Duration::ZERO);
    // `TrailingSlashPolicy::Remove` matches this crawler's own pre-Mudfish
    // dedup behavior (`/about` and `/about/` were always treated as the
    // same page) -- Mudfish's own default is `Preserve`, which is correct
    // for Mudfish's own generic use case but would be a silent behavior
    // change here.
    let normalization = NormalizationOptions {
        trailing_slash: TrailingSlashPolicy::Remove,
        ..NormalizationOptions::default()
    };
    CrawlConfig {
        max_depth: MAX_CRAWL_DEPTH,
        concurrency: concurrency.max(1),
        per_host_concurrency: concurrency.max(1),
        same_domain: true,
        respect_robots,
        request_delay,
        default_headers: headers,
        allow_private_networks,
        max_urls: Some(max_pages.max(1) as u64),
        user_agent: "PyTagManagerBot/0.2 (+https://github.com/Mullassery/PyTagManager)".to_string(),
        normalization,
        ..CrawlConfig::default()
    }
}

/// Same as `crawl`, but with an explicit `CrawlConfig`/`BrowserMode`.
/// `crawl` above is the only real (CLI/Python-facing) entry point and
/// always builds its config via `build_config(...,
/// allow_private_networks=false)`, so the SSRF guard (`mudfish_fetch`'s
/// DNS-resolution-based check) is always on for the HTTP path. **Browser
/// rendering does not go through that guard** (disclosed in both repos'
/// `ROADMAP_HONEST.md`) -- `BrowserMode::Auto`/`Always` against untrusted
/// input carries that risk until `mudfish-browser` has its own check.
///
/// This variant also exists so integration tests can pass
/// `allow_private_networks: true` to exercise the crawl loop against a
/// local mock HTTP server on loopback, which the guard would otherwise
/// correctly refuse to fetch.
///
/// Fetch/politeness/robots.txt/frontier dedup/circuit-breaking are all
/// delegated to Mudfish (`mudfish_fetch`/`mudfish_frontier`) -- this
/// function's own responsibility is narrower than the old pre-Mudfish
/// orchestrator's was: sitemap seeding (Mudfish has no sitemap support),
/// building this crate's own `SemanticGraph` from each fetched page's
/// body (Mudfish's fetcher returns the raw body; its own engine discards
/// it after extracting links/metadata, which isn't enough for a DOM
/// graph), and the browser-escalation decision itself.
pub async fn crawl_with_config(
    config: CrawlConfig,
    start_url: &str,
    browser_mode: BrowserMode,
) -> Result<Vec<Page>, AppError> {
    let seed = Url::parse(start_url)?;

    // The seed itself may redirect (e.g. `www.example.com` -> `example.com`);
    // same-domain scoping must follow that resolved host, not the literal
    // seed host, or every link on the real page would be misclassified as
    // cross-domain. Mirrors `mudfish_engine::crawl`'s own `scope_host`
    // handling exactly, including poisoned-lock recovery, since this
    // function reimplements that engine's worker loop rather than calling
    // it (see this function's doc comment for why).
    let scope_host = Arc::new(RwLock::new(seed.host_str().unwrap_or_default().to_string()));

    let fetcher = Arc::new(HttpFetcher::new(&config)?);
    let robots = Arc::new(RobotsManager::new(config.user_agent.clone()));
    let politeness = Arc::new(PolitenessManager::new(
        config.request_delay,
        config.per_host_concurrency,
    ));
    let frontier = Arc::new(Frontier::new(
        Box::new(DepthPriority),
        config.normalization.clone(),
    ));
    // Opens a host's circuit (and skips it for a cooldown) after repeated
    // 429/403/5xx responses -- "detect -> slow down -> cool down -> retry
    // later", never a change of IP/identity to get around a block. See
    // `mudfish_fetch::health` for the full breaker semantics.
    let health = Arc::new(DomainHealthTracker::default());

    // Launched lazily (only when browser escalation can actually happen)
    // since it spawns a real Chrome process -- a plain `BrowserMode::Off`
    // crawl (the default, matching pre-existing behavior exactly) never
    // pays for it.
    let browser: Option<Arc<BrowserRenderer>> = if browser_mode == BrowserMode::Off {
        None
    } else {
        Some(Arc::new(BrowserRenderer::launch(None).await.map_err(
            |e| AppError::Internal(format!("failed to launch browser renderer: {e}")),
        )?))
    };

    frontier.try_push(seed.clone(), 0, None);

    if let Ok(sitemap_url) = seed.join("/sitemap.xml") {
        seed_from_sitemap(&fetcher, sitemap_url.as_str(), &frontier).await;
    }

    let link_selector = Arc::new(Selector::parse("a[href]").expect("static selector is valid"));
    let pages = Arc::new(Mutex::new(Vec::<Page>::new()));
    let fetched = Arc::new(AtomicU64::new(0));
    let global_sem = Arc::new(Semaphore::new(config.concurrency.max(1)));
    let max_urls = config.max_urls;
    let max_depth = config.max_depth;
    let same_domain = config.same_domain;
    let respect_robots = config.respect_robots;

    let mut workers = Vec::with_capacity(config.concurrency.max(1));
    for _ in 0..config.concurrency.max(1) {
        let frontier = frontier.clone();
        let fetcher = fetcher.clone();
        let robots = robots.clone();
        let politeness = politeness.clone();
        let health = health.clone();
        let browser = browser.clone();
        let pages = pages.clone();
        let fetched = fetched.clone();
        let scope_host = scope_host.clone();
        let global_sem = global_sem.clone();
        let link_selector = link_selector.clone();

        workers.push(tokio::spawn(async move {
            'worker: loop {
                let item = match frontier.pop().await {
                    Some(item) => item,
                    None => break,
                };

                let _global_permit = global_sem.acquire().await.expect("semaphore not closed");
                let host = item.url.host_str().unwrap_or("").to_string();

                if !health.is_available(&host) {
                    frontier.complete(&item);
                    continue;
                }

                if respect_robots && !robots.is_allowed(&fetcher, &item.url).await {
                    frontier.complete(&item);
                    continue;
                }

                // Atomically reserve a fetch slot against `max_urls` right
                // before committing to the fetch -- see
                // `mudfish_engine::crawl`'s identical compare-exchange loop
                // for why a plain load-then-branch check would overshoot
                // the cap under concurrency.
                if let Some(max) = max_urls {
                    let mut current = fetched.load(Ordering::SeqCst);
                    loop {
                        if current >= max {
                            frontier.stop();
                            frontier.complete(&item);
                            break 'worker;
                        }
                        match fetched.compare_exchange_weak(
                            current,
                            current + 1,
                            Ordering::SeqCst,
                            Ordering::SeqCst,
                        ) {
                            Ok(_) => break,
                            Err(actual) => current = actual,
                        }
                    }
                }

                let host_sem = politeness.host_semaphore(&host);
                let _host_permit = host_sem.acquire().await.expect("semaphore not closed");
                politeness.wait_for_slot(&host).await;

                match fetcher.fetch(&item.url).await {
                    Ok(resp) => {
                        health.record_response(&host, resp.status);
                        let challenge = detect_challenge(resp.status, &resp.body);
                        let crawl_status = classify_status(resp.status, challenge);

                        let is_html = resp
                            .content_type
                            .as_deref()
                            .map(|ct| ct.contains("text/html"))
                            .unwrap_or(false);
                        let body_str = String::from_utf8_lossy(&resp.body).into_owned();

                        let should_render = is_html
                            && match browser_mode {
                                BrowserMode::Off => false,
                                BrowserMode::Always => true,
                                BrowserMode::Auto => static_html_looks_js_dependent(&body_str),
                            };

                        // Falls back to the static fetch's own body/links
                        // on a render failure (a page that times out or
                        // crashes the renderer shouldn't drop out of the
                        // crawl entirely) -- `rendered` tells the caller
                        // which actually happened.
                        let rendered_page = if should_render {
                            browser
                                .as_ref()
                                .expect(
                                    "should_render implies browser_mode != Off, which launched one",
                                )
                                .render(&resp.final_url, BROWSER_SETTLE)
                                .await
                                .ok()
                        } else {
                            None
                        };

                        let (effective_html, network_requests, cookies, rendered) =
                            match &rendered_page {
                                Some(r) => (
                                    r.html.clone(),
                                    r.network_requests
                                        .iter()
                                        .cloned()
                                        .map(NetworkRequest::from)
                                        .collect(),
                                    r.cookies.iter().cloned().map(Cookie::from).collect(),
                                    true,
                                ),
                                None => (body_str.clone(), Vec::new(), Vec::new(), false),
                            };

                        let graph = if is_html {
                            parse_html(&effective_html, resp.final_url.as_str())
                        } else {
                            SemanticGraph::default()
                        };

                        if item.depth == 0 {
                            if let Some(final_host) = resp.final_url.host_str() {
                                update_scope_host(&scope_host, final_host);
                            }
                        }

                        if is_html && item.depth < max_depth {
                            let effective_scope_host = read_scope_host(&scope_host);
                            let document = Html::parse_document(&effective_html);
                            for el in document.select(&link_selector) {
                                if let Some(href) = el.value().attr("href") {
                                    if let Ok(joined) = resp.final_url.join(href) {
                                        if same_domain
                                            && joined.host_str()
                                                != Some(effective_scope_host.as_str())
                                        {
                                            continue;
                                        }
                                        frontier.try_push(
                                            joined,
                                            item.depth + 1,
                                            Some(item.url.clone()),
                                        );
                                    }
                                }
                            }
                        }

                        pages.lock().await.push(Page {
                            url: resp.final_url.to_string(),
                            status: resp.status,
                            graph,
                            crawl_status: crawl_status.to_string(),
                            rendered,
                            network_requests,
                            cookies,
                        });
                    }
                    Err(_) => {
                        // A failed fetch never became a real page: release
                        // the slot reserved above so it doesn't permanently
                        // consume budget a later successful fetch could use.
                        if max_urls.is_some() {
                            fetched.fetch_sub(1, Ordering::SeqCst);
                        }
                    }
                }

                frontier.complete(&item);
            }
        }));
    }

    for w in workers {
        let _ = w.await;
    }

    let pages = match Arc::try_unwrap(pages) {
        Ok(mutex) => mutex.into_inner(),
        Err(_) => unreachable!("all workers joined, so no other Arc clone can remain"),
    };
    Ok(pages)
}

/// Updates `lock` to `new_host` if it differs, recovering from poisoning
/// instead of propagating it -- see `mudfish_engine::crawl`'s identical
/// helper for the full rationale (a single worker panicking while holding
/// this lock must not cascade into every other worker panicking).
fn update_scope_host(lock: &RwLock<String>, new_host: &str) {
    let mut guard = lock
        .write()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    if guard.as_str() != new_host {
        *guard = new_host.to_string();
    }
}

fn read_scope_host(lock: &RwLock<String>) -> String {
    lock.read()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
        .clone()
}

/// Seeds the frontier with every URL listed in `start_sitemap_url` (and any
/// sitemap index it points to), at depth 0 -- same treatment as the seed
/// URL itself. Mudfish has no sitemap support of its own, so this stays
/// entirely PyTagManager-side.
async fn seed_from_sitemap(fetcher: &HttpFetcher, start_sitemap_url: &str, frontier: &Frontier) {
    const MAX_SITEMAP_DEPTH: u8 = 3;
    let mut queue = VecDeque::new();
    queue.push_back((start_sitemap_url.to_string(), 0u8));

    while let Some((sitemap_url, depth)) = queue.pop_front() {
        if depth > MAX_SITEMAP_DEPTH {
            continue;
        }
        let Ok(url) = Url::parse(&sitemap_url) else {
            continue;
        };
        let Ok(resp) = fetcher.fetch(&url).await else {
            continue;
        };
        if !(200..300).contains(&resp.status) {
            continue;
        }
        let body_str = String::from_utf8_lossy(&resp.body).into_owned();
        match parse_sitemap(&body_str) {
            Some(SitemapContent::UrlSet(urls)) => {
                for u in urls {
                    if let Ok(parsed) = Url::parse(&u) {
                        frontier.try_push(parsed, 0, None);
                    }
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
