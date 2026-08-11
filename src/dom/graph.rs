use pyo3::prelude::*;
use std::collections::HashMap;

/// A single DOM element captured as part of a page's semantic graph.
///
/// Selector fields are precomputed at parse time so Python-side consumers
/// (heuristics, exporters) never need to re-walk raw HTML.
#[pyclass]
#[derive(Clone, Debug)]
pub struct SemanticNode {
    #[pyo3(get)]
    pub id: usize,
    #[pyo3(get)]
    pub parent_id: Option<usize>,
    #[pyo3(get)]
    pub tag: String,
    #[pyo3(get)]
    pub xpath: String,
    #[pyo3(get)]
    pub css_selector: String,
    /// Best-effort resilient selector (data-testid / data-* / aria-label / id),
    /// preferred over `css_selector` when present. None if no stable attribute exists.
    #[pyo3(get)]
    pub stable_selector: Option<String>,
    #[pyo3(get)]
    pub text: String,
    #[pyo3(get)]
    pub aria_role: Option<String>,
    #[pyo3(get)]
    pub aria_label: Option<String>,
    #[pyo3(get)]
    pub classes: Vec<String>,
    #[pyo3(get)]
    pub attributes: HashMap<String, String>,
}

#[pymethods]
impl SemanticNode {
    fn __repr__(&self) -> String {
        format!(
            "SemanticNode(id={}, tag='{}', css_selector='{}', stable_selector={:?})",
            self.id, self.tag, self.css_selector, self.stable_selector
        )
    }
}

/// The full semantic graph for one crawled/parsed page.
#[pyclass]
#[derive(Clone, Debug, Default)]
pub struct SemanticGraph {
    #[pyo3(get)]
    pub url: String,
    #[pyo3(get)]
    pub nodes: Vec<SemanticNode>,
}

#[pymethods]
impl SemanticGraph {
    fn __len__(&self) -> usize {
        self.nodes.len()
    }

    fn __repr__(&self) -> String {
        format!(
            "SemanticGraph(url='{}', nodes={})",
            self.url,
            self.nodes.len()
        )
    }

    /// Case-insensitive lookup of all nodes with the given tag name.
    pub fn find_by_tag(&self, tag: &str) -> Vec<SemanticNode> {
        self.nodes
            .iter()
            .filter(|n| n.tag.eq_ignore_ascii_case(tag))
            .cloned()
            .collect()
    }
}
