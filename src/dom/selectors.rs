use std::collections::HashMap;

/// data-* attribute names checked first, in priority order, before falling
/// back to an arbitrary (but deterministically sorted) data-* attribute.
const PRIORITY_DATA_ATTRS: &[&str] = &["data-testid", "data-test", "data-qa", "data-cy"];

/// Compute the most resilient selector available for an element, preferring
/// test/automation hooks and ARIA labels over brittle positional selectors,
/// per the platform's selector-resilience requirement.
pub fn compute_stable_selector(tag: &str, attributes: &HashMap<String, String>) -> Option<String> {
    for attr in PRIORITY_DATA_ATTRS {
        if let Some(val) = attributes.get(*attr) {
            if !val.is_empty() {
                return Some(format!("[{}=\"{}\"]", attr, val));
            }
        }
    }

    // Any other data-* attribute. Sorted for determinism since HashMap
    // iteration order is not stable.
    let mut data_attrs: Vec<(&String, &String)> = attributes
        .iter()
        .filter(|(k, v)| k.starts_with("data-") && !v.is_empty())
        .collect();
    data_attrs.sort_by(|(k1, _), (k2, _)| k1.cmp(k2));
    if let Some((k, v)) = data_attrs.first() {
        return Some(format!("[{}=\"{}\"]", k, v));
    }

    if let Some(label) = attributes.get("aria-label") {
        if !label.is_empty() {
            return Some(format!("{}[aria-label=\"{}\"]", tag, label));
        }
    }

    if let Some(id) = attributes.get("id") {
        if !id.is_empty() {
            return Some(format!("#{}", id));
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn attrs(pairs: &[(&str, &str)]) -> HashMap<String, String> {
        pairs.iter().map(|(k, v)| (k.to_string(), v.to_string())).collect()
    }

    #[test]
    fn prefers_data_testid_over_id() {
        let a = attrs(&[("data-testid", "buy-now"), ("id", "btn-1")]);
        assert_eq!(compute_stable_selector("button", &a).as_deref(), Some("[data-testid=\"buy-now\"]"));
    }

    #[test]
    fn falls_back_to_sorted_data_attr() {
        let a = attrs(&[("data-zeta", "z"), ("data-alpha", "a")]);
        assert_eq!(compute_stable_selector("div", &a).as_deref(), Some("[data-alpha=\"a\"]"));
    }

    #[test]
    fn falls_back_to_aria_label_then_id() {
        let a = attrs(&[("aria-label", "Add to cart")]);
        assert_eq!(
            compute_stable_selector("button", &a).as_deref(),
            Some("button[aria-label=\"Add to cart\"]")
        );

        let a = attrs(&[("id", "cta-1")]);
        assert_eq!(compute_stable_selector("a", &a).as_deref(), Some("#cta-1"));
    }

    #[test]
    fn none_when_nothing_stable() {
        let a = attrs(&[("class", "btn btn-primary")]);
        assert_eq!(compute_stable_selector("button", &a), None);
    }
}
