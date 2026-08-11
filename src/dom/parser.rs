use scraper::{ElementRef, Html};
use std::collections::HashMap;

use crate::dom::graph::{SemanticGraph, SemanticNode};
use crate::dom::selectors::compute_stable_selector;

/// Parse raw HTML into a semantic graph: static structure only (no
/// visibility/bounding-box/z-index — those require a real browser renderer
/// and are out of scope for this static parser; the Python runtime layer
/// can hand rendered HTML back through this same function).
pub fn parse_html(html: &str, url: &str) -> SemanticGraph {
    let document = Html::parse_document(html);
    let mut nodes = Vec::new();
    let mut next_id: usize = 0;

    walk(
        document.root_element(),
        None,
        "",
        "",
        &mut nodes,
        &mut next_id,
    );

    SemanticGraph {
        url: url.to_string(),
        nodes,
    }
}

fn walk(
    el: ElementRef,
    parent_id: Option<usize>,
    parent_xpath: &str,
    parent_css: &str,
    nodes: &mut Vec<SemanticNode>,
    next_id: &mut usize,
) {
    let id = *next_id;
    *next_id += 1;

    let tag = el.value().name().to_string();

    let xpath = format!("{}/{}[{}]", parent_xpath, tag, sibling_index_by_tag(el));
    let css_segment = format!("{}:nth-child({})", tag, sibling_index_all(el));
    let css_selector = if parent_css.is_empty() {
        css_segment
    } else {
        format!("{} > {}", parent_css, css_segment)
    };

    let mut attributes: HashMap<String, String> = HashMap::new();
    for (k, v) in el.value().attrs() {
        attributes.insert(k.to_string(), v.to_string());
    }

    let classes: Vec<String> = el.value().classes().map(|c| c.to_string()).collect();
    let aria_label = attributes.get("aria-label").cloned();
    let aria_role = attributes.get("role").cloned();
    let stable_selector = compute_stable_selector(&tag, &attributes);

    let text = el
        .text()
        .collect::<Vec<_>>()
        .join(" ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ");

    let node = SemanticNode {
        id,
        parent_id,
        tag,
        xpath: xpath.clone(),
        css_selector: css_selector.clone(),
        stable_selector,
        text,
        aria_role,
        aria_label,
        classes,
        attributes,
    };
    nodes.push(node);

    for child in el.children() {
        if let Some(child_el) = ElementRef::wrap(child) {
            walk(child_el, Some(id), &xpath, &css_selector, nodes, next_id);
        }
    }
}

fn sibling_index_by_tag(el: ElementRef) -> usize {
    let tag = el.value().name();
    let mut idx = 1;
    for sib in el.prev_siblings() {
        if let Some(sib_el) = ElementRef::wrap(sib) {
            if sib_el.value().name() == tag {
                idx += 1;
            }
        }
    }
    idx
}

fn sibling_index_all(el: ElementRef) -> usize {
    let mut idx = 1;
    for sib in el.prev_siblings() {
        if ElementRef::wrap(sib).is_some() {
            idx += 1;
        }
    }
    idx
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_basic_page_structure() {
        let html = r#"
            <html><body>
                <div id="hero">
                    <button data-testid="buy-now">Buy Now</button>
                    <a href="/contact" aria-label="Contact us">Contact</a>
                </div>
                <form id="signup"><input name="email"/></form>
            </body></html>
        "#;
        let graph = parse_html(html, "https://example.com");

        let buttons = graph.find_by_tag("button");
        assert_eq!(buttons.len(), 1);
        assert_eq!(
            buttons[0].stable_selector.as_deref(),
            Some("[data-testid=\"buy-now\"]")
        );

        let links = graph.find_by_tag("a");
        assert_eq!(links.len(), 1);
        assert_eq!(links[0].aria_label.as_deref(), Some("Contact us"));

        let forms = graph.find_by_tag("form");
        assert_eq!(forms.len(), 1);

        // parent linkage: button's parent should be the div#hero node
        let hero_divs = graph.find_by_tag("div");
        assert_eq!(hero_divs.len(), 1);
        assert_eq!(buttons[0].parent_id, Some(hero_divs[0].id));
    }
}
