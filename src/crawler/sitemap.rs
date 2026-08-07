/// Parsed content of a sitemap.xml resource: either a leaf urlset (page
/// URLs) or a sitemap index (pointers to further sitemaps to fetch).
pub enum SitemapContent {
    UrlSet(Vec<String>),
    Index(Vec<String>),
}

pub fn parse_sitemap(xml: &str) -> Option<SitemapContent> {
    let doc = roxmltree::Document::parse(xml).ok()?;
    let root = doc.root_element();
    let root_name = root.tag_name().name();

    let locs: Vec<String> = root
        .children()
        .filter(|n| n.is_element())
        .filter_map(|entry| {
            entry
                .children()
                .find(|c| c.is_element() && c.tag_name().name() == "loc")
                .and_then(|loc_node| loc_node.text())
                .map(|t| t.trim().to_string())
        })
        .filter(|s| !s.is_empty())
        .collect();

    match root_name {
        "sitemapindex" => Some(SitemapContent::Index(locs)),
        "urlset" => Some(SitemapContent::UrlSet(locs)),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_urlset() {
        let xml = r#"<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <url><loc>https://example.com/a</loc></url>
            <url><loc>https://example.com/b</loc></url>
        </urlset>"#;
        match parse_sitemap(xml) {
            Some(SitemapContent::UrlSet(urls)) => {
                assert_eq!(urls, vec!["https://example.com/a", "https://example.com/b"]);
            }
            _ => panic!("expected UrlSet"),
        }
    }

    #[test]
    fn parses_sitemap_index() {
        let xml = r#"<?xml version="1.0"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
            <sitemap><loc>https://example.com/sitemap-a.xml</loc></sitemap>
        </sitemapindex>"#;
        match parse_sitemap(xml) {
            Some(SitemapContent::Index(urls)) => {
                assert_eq!(urls, vec!["https://example.com/sitemap-a.xml"]);
            }
            _ => panic!("expected Index"),
        }
    }

    #[test]
    fn invalid_xml_returns_none() {
        assert!(parse_sitemap("not xml").is_none());
    }
}
