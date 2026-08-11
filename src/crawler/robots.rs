/// Minimal robots.txt parser: honors `Disallow` rules for the `User-agent: *`
/// group only. Does not implement `Allow` overrides, crawl-delay, or
/// wildcard/`$`-anchored path matching — sufficient for a v1 "don't crawl
/// obviously disallowed paths" check, not a full RFC-adjacent implementation.
pub struct RobotsRules {
    disallow: Vec<String>,
}

impl RobotsRules {
    pub fn parse(text: &str) -> Self {
        let mut disallow = Vec::new();
        let mut in_wildcard_group = false;

        for raw_line in text.lines() {
            let line = raw_line.split('#').next().unwrap_or("").trim();
            if line.is_empty() {
                continue;
            }
            let mut parts = line.splitn(2, ':');
            let (key, value) = match (parts.next(), parts.next()) {
                (Some(k), Some(v)) => (k.trim().to_ascii_lowercase(), v.trim().to_string()),
                _ => continue,
            };

            match key.as_str() {
                "user-agent" => in_wildcard_group = value == "*",
                "disallow" if in_wildcard_group && !value.is_empty() => disallow.push(value),
                _ => {}
            }
        }

        Self { disallow }
    }

    pub fn allow_all() -> Self {
        Self {
            disallow: Vec::new(),
        }
    }

    pub fn is_allowed(&self, path: &str) -> bool {
        !self
            .disallow
            .iter()
            .any(|rule| path.starts_with(rule.as_str()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn disallows_matching_prefix_for_wildcard_agent() {
        let rules = RobotsRules::parse("User-agent: *\nDisallow: /admin\nDisallow: /private/\n");
        assert!(!rules.is_allowed("/admin"));
        assert!(!rules.is_allowed("/admin/settings"));
        assert!(!rules.is_allowed("/private/data"));
        assert!(rules.is_allowed("/products"));
    }

    #[test]
    fn ignores_rules_scoped_to_other_agents() {
        let rules = RobotsRules::parse("User-agent: Googlebot\nDisallow: /\n");
        assert!(rules.is_allowed("/anything"));
    }

    #[test]
    fn empty_text_allows_everything() {
        let rules = RobotsRules::parse("");
        assert!(rules.is_allowed("/anything"));
    }
}
