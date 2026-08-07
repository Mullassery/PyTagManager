mod crawler;
mod dom;
mod error;

use pyo3::prelude::*;

use crawler::Page;
use dom::{SemanticGraph, SemanticNode};

/// Crawl a site starting from `start_url` and return each visited page's
/// semantic DOM graph. Blocks the calling Python thread but releases the
/// GIL while the async crawl runs internally on a Tokio runtime.
#[pyfunction]
#[pyo3(signature = (start_url, max_pages=50, concurrency=10, respect_robots=true))]
fn crawl(
    py: Python<'_>,
    start_url: &str,
    max_pages: usize,
    concurrency: usize,
    respect_robots: bool,
) -> PyResult<Vec<Page>> {
    let result: Result<Vec<Page>, error::AppError> = py.allow_threads(|| {
        let rt = tokio::runtime::Runtime::new().expect("failed to start tokio runtime");
        rt.block_on(crawler::crawl(start_url, max_pages, concurrency, respect_robots))
    });
    Ok(result?)
}

/// Parse already-fetched HTML (e.g. from a Python-side browser renderer)
/// into a semantic DOM graph, without crawling.
#[pyfunction]
fn parse_html(html: &str, url: &str) -> SemanticGraph {
    crate::dom::parser::parse_html(html, url)
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<SemanticNode>()?;
    m.add_class::<SemanticGraph>()?;
    m.add_class::<Page>()?;
    m.add_function(wrap_pyfunction!(crawl, m)?)?;
    m.add_function(wrap_pyfunction!(parse_html, m)?)?;
    Ok(())
}
