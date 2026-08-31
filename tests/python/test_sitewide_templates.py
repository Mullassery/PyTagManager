from pytagmanager.sitewide.templates import detect_templates, url_template


class _FakeNode:
    def __init__(self, classes):
        self.classes = classes


class _FakeGraph:
    def __init__(self, node_class_lists):
        self.nodes = [_FakeNode(classes) for classes in node_class_lists]


class _FakePage:
    def __init__(self, url, node_class_lists=()):
        self.url = url
        self.graph = _FakeGraph(node_class_lists)


def test_url_template_generalizes_numeric_and_uuid_segments():
    assert url_template("https://example.com/products/123") == "/products/{param}"
    assert url_template("https://example.com/products/9f8b7c6d-1111-2222-3333-444455556666") == "/products/{param}"
    assert url_template("https://example.com/") == "/"
    assert url_template("https://example.com/checkout/confirmation") == "/checkout/confirmation"


def test_url_template_generalizes_deep_slug_segments():
    assert url_template("https://example.com/products/blue-running-shoes") == "/products/{param}"
    # Top-level slugs (depth 1) are NOT treated as dynamic -- /about-us is a
    # real static page, not a product-detail-style slug.
    assert url_template("https://example.com/about-us") == "/about-us"


def test_detect_templates_groups_by_url_pattern():
    pages = [
        _FakePage("https://example.com/products/1"),
        _FakePage("https://example.com/products/2"),
        _FakePage("https://example.com/products/3"),
        _FakePage("https://example.com/cart"),
    ]
    templates = detect_templates(pages)
    by_label = {t.label: t for t in templates}

    assert len(by_label["Products"].page_urls) == 3
    assert len(by_label["Cart"].page_urls) == 1


def test_detect_templates_merges_by_dom_fingerprint_across_different_urls():
    shared_classes = [["product-grid"], ["product-card"], ["product-card"], ["price-tag"], ["price-tag"]]
    pages = [
        _FakePage("https://example.com/deals", shared_classes),
        _FakePage("https://example.com/new-arrivals", shared_classes),
        _FakePage("https://example.com/about-us", [["prose"], ["prose"]]),
    ]
    templates = detect_templates(pages, similarity_threshold=0.6)

    merged = next(t for t in templates if "https://example.com/deals" in t.page_urls)
    assert "https://example.com/new-arrivals" in merged.page_urls
    assert len(merged.page_urls) == 2

    unrelated = next(t for t in templates if "https://example.com/about-us" in t.page_urls)
    assert len(unrelated.page_urls) == 1
