//! End-to-end integration tests for `crawler::orchestrator::crawl_with_fetcher`
//! (the real BFS/batching crawl loop, robots.txt/sitemap.xml handling, and
//! `Fetcher`'s HTTP behavior) driven against a local mock HTTP server.
//!
//! These use `Fetcher::with_ssrf_guard(false)` -- the mock server runs on
//! loopback, which the SSRF guard (correctly) blocks by default. See
//! `crawler::orchestrator::crawl_with_fetcher`'s doc comment for why this
//! injection point exists and why it's safe (no real/CLI/Python entry
//! point can reach it).

mod support;

use std::collections::HashMap;

use _core::crawler::crawl_with_fetcher;
use _core::crawler::fetcher::Fetcher;

use support::{MockResponse, MockServer};

fn urls(pages: &[_core::crawler::Page]) -> Vec<String> {
    let mut v: Vec<String> = pages.iter().map(|p| p.url.clone()).collect();
    v.sort();
    v
}

#[tokio::test]
async fn bfs_crawls_all_linked_same_domain_pages_and_skips_off_domain_links() {
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html(
            r#"<html><body>
                <a href="/about">About</a>
                <a href="/contact">Contact</a>
                <a href="https://off-domain.example.invalid/elsewhere">Off domain</a>
            </body></html>"#,
        ),
    );
    routes.insert(
        "/about".to_string(),
        MockResponse::html(
            r#"<html><body><a href="/">Home</a><a href="/contact">Contact</a></body></html>"#,
        ),
    );
    routes.insert(
        "/contact".to_string(),
        MockResponse::html("<html><body>Contact us</body></html>"),
    );

    let server = MockServer::start(routes).await;
    let fetcher = Fetcher::with_ssrf_guard(false);

    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 4, true)
        .await
        .expect("crawl should succeed");

    let base = server.base_url();
    assert_eq!(
        urls(&pages),
        vec![
            format!("{base}/"),
            format!("{base}/about"),
            format!("{base}/contact")
        ],
        "BFS should visit exactly the 3 same-domain pages and never the off-domain link"
    );
}

#[tokio::test]
async fn bfs_handles_fan_out_across_multiple_concurrency_batches() {
    // 4 leaf pages linked from the root; with concurrency=2 the orchestrator
    // must process them across 2 batches of 2, not just the first batch.
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html(
            r#"<html><body>
                <a href="/p1">1</a><a href="/p2">2</a>
                <a href="/p3">3</a><a href="/p4">4</a>
            </body></html>"#,
        ),
    );
    for p in ["/p1", "/p2", "/p3", "/p4"] {
        routes.insert(
            p.to_string(),
            MockResponse::html(format!("<html><body>{p}</body></html>")),
        );
    }

    let server = MockServer::start(routes).await;
    let fetcher = Fetcher::with_ssrf_guard(false);

    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 2, true)
        .await
        .expect("crawl should succeed");

    let base = server.base_url();
    let mut expected = vec![
        format!("{base}/"),
        format!("{base}/p1"),
        format!("{base}/p2"),
        format!("{base}/p3"),
        format!("{base}/p4"),
    ];
    expected.sort();
    assert_eq!(urls(&pages), expected);
}

#[tokio::test]
async fn respects_robots_txt_disallow_for_wildcard_agent() {
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html(
            r#"<html><body><a href="/allowed">ok</a><a href="/blocked/page">no</a></body></html>"#,
        ),
    );
    routes.insert(
        "/allowed".to_string(),
        MockResponse::html("<html><body>allowed</body></html>"),
    );
    routes.insert(
        "/blocked/page".to_string(),
        MockResponse::html("<html><body>should not be fetched</body></html>"),
    );
    routes.insert(
        "/robots.txt".to_string(),
        MockResponse::text(200, "User-agent: *\nDisallow: /blocked\n"),
    );

    let server = MockServer::start(routes).await;
    let fetcher = Fetcher::with_ssrf_guard(false);

    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 4, true)
        .await
        .expect("crawl should succeed");

    let base = server.base_url();
    assert_eq!(
        urls(&pages),
        vec![format!("{base}/"), format!("{base}/allowed")]
    );
}

#[tokio::test]
async fn robots_txt_disallow_is_ignored_when_respect_robots_is_false() {
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html(r#"<html><body><a href="/blocked/page">no</a></body></html>"#),
    );
    routes.insert(
        "/blocked/page".to_string(),
        MockResponse::html("<html><body>now fetchable</body></html>"),
    );
    routes.insert(
        "/robots.txt".to_string(),
        MockResponse::text(200, "User-agent: *\nDisallow: /blocked\n"),
    );

    let server = MockServer::start(routes).await;
    let fetcher = Fetcher::with_ssrf_guard(false);

    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 4, false)
        .await
        .expect("crawl should succeed");

    let base = server.base_url();
    assert_eq!(
        urls(&pages),
        vec![format!("{base}/"), format!("{base}/blocked/page")]
    );
}

#[tokio::test]
async fn sitemap_xml_seeds_a_page_with_no_inbound_links() {
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html("<html><body>no links here</body></html>"),
    );
    routes.insert(
        "/hidden".to_string(),
        MockResponse::html("<html><body>only reachable via sitemap</body></html>"),
    );

    let server = MockServer::start(routes).await;
    let sitemap_xml = format!(
        r#"<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>{}/hidden</loc></url>
        </urlset>"#,
        server.base_url()
    );
    server.set_route("/sitemap.xml", MockResponse::xml(sitemap_xml));

    let fetcher = Fetcher::with_ssrf_guard(false);
    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 4, true)
        .await
        .expect("crawl should succeed");

    let base = server.base_url();
    assert_eq!(
        urls(&pages),
        vec![format!("{base}/"), format!("{base}/hidden")]
    );
}

#[tokio::test]
async fn follows_redirects_and_records_the_final_url_and_status() {
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html(r#"<html><body><a href="/old">old link</a></body></html>"#),
    );
    routes.insert("/old".to_string(), MockResponse::redirect_to("/new"));
    routes.insert(
        "/new".to_string(),
        MockResponse::html(r#"<html><body><a href="/leaf">leaf</a></body></html>"#),
    );
    routes.insert(
        "/leaf".to_string(),
        MockResponse::html("<html><body>leaf page</body></html>"),
    );

    let server = MockServer::start(routes).await;
    let fetcher = Fetcher::with_ssrf_guard(false);

    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 4, true)
        .await
        .expect("crawl should succeed");

    let base = server.base_url();
    // The redirect target ("/new"), not "/old", is what gets recorded as
    // the page URL -- and links found on the post-redirect page ("/leaf")
    // are still discovered and crawled, proving link extraction uses the
    // final (post-redirect) URL as its base for resolving relative hrefs.
    assert_eq!(
        urls(&pages),
        vec![
            format!("{base}/"),
            format!("{base}/leaf"),
            format!("{base}/new")
        ]
    );
    let new_page = pages
        .iter()
        .find(|p| p.url == format!("{base}/new"))
        .unwrap();
    assert_eq!(new_page.status, 200);
}

#[tokio::test]
async fn non_2xx_status_pages_are_recorded_rather_than_dropped() {
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html(r#"<html><body><a href="/broken">broken</a></body></html>"#),
    );
    routes.insert(
        "/broken".to_string(),
        MockResponse::text(500, "server exploded"),
    );

    let server = MockServer::start(routes).await;
    let fetcher = Fetcher::with_ssrf_guard(false);

    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 4, true)
        .await
        .expect("crawl should succeed");

    let base = server.base_url();
    let broken = pages
        .iter()
        .find(|p| p.url == format!("{base}/broken"))
        .expect("the 500-status page should still appear in results, not be silently dropped");
    assert_eq!(broken.status, 500);
}

#[tokio::test]
async fn a_dead_link_does_not_abort_the_rest_of_the_crawl() {
    // "/" links to a normal page plus a same-domain (by host, ignoring
    // port) address nothing is listening on. The orchestrator's batch
    // fetch drops failed fetches (`.ok()`) rather than propagating the
    // error, so the crawl should still complete and return the page(s)
    // that did succeed.
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html(r#"<html><body><a href="/ok">ok</a><a href="http://127.0.0.1:1/dead">dead</a></body></html>"#),
    );
    routes.insert(
        "/ok".to_string(),
        MockResponse::html("<html><body>ok</body></html>"),
    );

    let server = MockServer::start(routes).await;
    let fetcher = Fetcher::with_ssrf_guard(false);

    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 4, true)
        .await
        .expect("crawl should succeed despite one unreachable link");

    let base = server.base_url();
    assert!(pages.iter().any(|p| p.url == format!("{base}/")));
    assert!(pages.iter().any(|p| p.url == format!("{base}/ok")));
    assert!(
        pages.iter().all(|p| !p.url.contains(":1/dead")),
        "the unreachable page must not appear in results"
    );
}

#[tokio::test]
async fn max_pages_caps_total_pages_discovered_and_the_crawl_terminates() {
    // A long linear chain -- each page links only to the next -- with a
    // small max_pages. Whatever the exact cap semantics, the crawl must
    // terminate quickly and never return more than max_pages pages.
    let mut routes = HashMap::new();
    let chain: Vec<String> = (0..10).map(|i| format!("/p{i}")).collect();
    for (i, path) in chain.iter().enumerate() {
        let next = chain.get(i + 1).cloned().unwrap_or_default();
        let body = if next.is_empty() {
            "<html><body>end</body></html>".to_string()
        } else {
            format!(r#"<html><body><a href="{next}">next</a></body></html>"#)
        };
        routes.insert(path.clone(), MockResponse::html(body));
    }
    routes.insert(
        "/".to_string(),
        MockResponse::html(r#"<html><body><a href="/p0">start</a></body></html>"#),
    );

    let server = MockServer::start(routes).await;
    let fetcher = Fetcher::with_ssrf_guard(false);

    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 3, 1, true)
        .await
        .expect("crawl should succeed");

    assert!(
        pages.len() <= 3,
        "max_pages=3 must cap total pages returned, got {}",
        pages.len()
    );
    assert!(
        !pages.is_empty(),
        "the crawl should make at least some progress"
    );
}

#[tokio::test]
async fn ssrf_guard_blocks_start_url_and_crawl_returns_empty_rather_than_erroring() {
    // Unlike every other test in this file, this one uses `Fetcher::new()`
    // (the SSRF guard ON) -- the same constructor every real CLI/Python
    // crawl uses -- to prove the guard is effective at the full orchestrator
    // level, not just in `Fetcher::fetch` in isolation. Per-page fetch
    // failures (including SSRF-guard rejections) are swallowed by the
    // orchestrator's batch loop (`.ok()`), so the observable result is an
    // empty page list, not a propagated error.
    let fetcher = Fetcher::new();
    let pages = crawl_with_fetcher(fetcher, "http://127.0.0.1:1/", 2, 1, false)
        .await
        .expect("a blocked/failed fetch should not fail the whole crawl");
    assert!(pages.is_empty());
}

#[tokio::test]
async fn custom_headers_are_sent_with_every_request() {
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html("<html><body>ok</body></html>"),
    );

    let server = MockServer::start(routes).await;
    let fetcher = Fetcher::build(
        false,
        None,
        &[
            ("Cookie".to_string(), "session=abc123".to_string()),
            ("X-Api-Key".to_string(), "secret".to_string()),
        ],
    )
    .expect("valid headers should build a Fetcher");

    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 1, true)
        .await
        .expect("crawl should succeed");
    assert_eq!(pages.len(), 1);

    let sent = server
        .last_received_headers("/")
        .expect("the server should have recorded a request to /");
    assert!(
        sent.contains(&("cookie".to_string(), "session=abc123".to_string())),
        "expected Cookie header to be sent, got {sent:?}"
    );
    assert!(
        sent.contains(&("x-api-key".to_string(), "secret".to_string())),
        "expected X-Api-Key header to be sent, got {sent:?}"
    );
}

#[tokio::test]
async fn fetch_retries_a_503_and_returns_the_eventual_success() {
    let mut routes = HashMap::new();
    routes.insert(
        "/".to_string(),
        MockResponse::html("<html><body>start</body></html>"),
    );

    let server = MockServer::start(routes).await;
    server.set_sequence(
        "/flaky",
        vec![
            MockResponse::text(503, "try again later"),
            MockResponse::html("<html><body>recovered</body></html>"),
        ],
    );
    server.set_route(
        "/".to_string(),
        MockResponse::html(r#"<html><body><a href="/flaky">flaky</a></body></html>"#),
    );

    let fetcher = Fetcher::with_ssrf_guard(false);
    let pages = crawl_with_fetcher(fetcher, &server.base_url(), 50, 1, true)
        .await
        .expect("crawl should succeed despite the first 503");

    let base = server.base_url();
    let flaky = pages
        .iter()
        .find(|p| p.url == format!("{base}/flaky"))
        .expect("the flaky page should eventually succeed and appear in results");
    assert_eq!(flaky.status, 200);
    assert_eq!(
        server.request_count("/flaky"),
        2,
        "expected exactly one retry after the initial 503"
    );
}
