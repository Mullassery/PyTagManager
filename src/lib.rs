// `#[pyfunction]`'s macro-generated wrapper code triggers a
// `clippy::useless_conversion` false positive on the `PyResult<T>` return
// path of every pyfunction in this crate (reproduced with a minimal
// pyo3 0.22 example independent of any of our own code -- see
// https://github.com/PyO3/pyo3/issues/2853 for the same class of
// pyo3/clippy interaction). An `#[allow]` on the function itself does not
// suppress it because the lint is attributed to a macro-generated sibling
// item, not the annotated item, so this is silenced crate-wide instead.
#![allow(clippy::useless_conversion)]

// pub(crate) internals need to be `pub` (not just `mod`) so that
// tests/*.rs integration tests -- compiled as a separate crate linked
// against the "rlib" artifact above -- can drive `crawler::crawl` and the
// DOM/error types directly, the same way the PyO3 wrapper functions below
// do internally.
pub mod crawler;
pub mod dom;
pub mod error;

use pyo3::prelude::*;

use crawler::Page;
use dom::{SemanticGraph, SemanticNode};

/// Crawl a site starting from `start_url` and return each visited page's
/// semantic DOM graph. Blocks the calling Python thread but releases the
/// GIL while the async crawl runs internally on a Tokio runtime.
#[pyfunction]
#[pyo3(signature = (start_url, max_pages=50, concurrency=10, respect_robots=true, rate_limit_per_sec=None, headers=vec![]))]
#[allow(clippy::too_many_arguments)]
fn crawl(
    py: Python<'_>,
    start_url: &str,
    max_pages: usize,
    concurrency: usize,
    respect_robots: bool,
    rate_limit_per_sec: Option<f64>,
    headers: Vec<(String, String)>,
) -> PyResult<Vec<Page>> {
    let result: Result<Vec<Page>, error::AppError> = py.allow_threads(|| {
        let rt = tokio::runtime::Runtime::new().expect("failed to start tokio runtime");
        rt.block_on(crawler::crawl(
            start_url,
            max_pages,
            concurrency,
            respect_robots,
            rate_limit_per_sec,
            headers,
        ))
    });
    result.map_err(PyErr::from)
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
