use std::collections::{HashSet, VecDeque};
use url::Url;

/// BFS URL queue: normalizes URLs (strips fragments, trims trailing slash),
/// restricts to the seed's domain, dedupes, and caps total pages visited.
pub struct Frontier {
    queue: VecDeque<String>,
    seen: HashSet<String>,
    root_domain: String,
    max_pages: usize,
}

impl Frontier {
    pub fn new(start_url: &str, max_pages: usize) -> Result<Self, url::ParseError> {
        let parsed = Url::parse(start_url)?;
        let root_domain = parsed.host_str().unwrap_or("").to_string();
        let mut frontier = Self {
            queue: VecDeque::new(),
            seen: HashSet::new(),
            root_domain,
            max_pages: max_pages.max(1),
        };
        frontier.push(start_url);
        Ok(frontier)
    }

    pub fn normalize(url: &str) -> Option<String> {
        let mut parsed = Url::parse(url).ok()?;
        parsed.set_fragment(None);
        if parsed.path().len() > 1 && parsed.path().ends_with('/') {
            let trimmed = parsed.path().trim_end_matches('/').to_string();
            parsed.set_path(&trimmed);
        }
        Some(parsed.to_string())
    }

    fn is_same_domain(&self, url: &str) -> bool {
        Url::parse(url)
            .ok()
            .and_then(|u| u.host_str().map(|h| h == self.root_domain))
            .unwrap_or(false)
    }

    /// Attempts to enqueue a URL. Returns false if it was rejected (off-domain,
    /// already seen, at capacity, or unparseable) rather than enqueued.
    pub fn push(&mut self, url: &str) -> bool {
        if self.seen.len() >= self.max_pages {
            return false;
        }
        let Some(normalized) = Self::normalize(url) else {
            return false;
        };
        if !self.is_same_domain(&normalized) {
            return false;
        }
        if !self.seen.insert(normalized.clone()) {
            return false;
        }
        self.queue.push_back(normalized);
        true
    }

    pub fn pop(&mut self) -> Option<String> {
        self.queue.pop_front()
    }

    /// Whether the BFS loop should keep draining the queue. Deliberately
    /// does NOT also check `self.seen.len() < self.max_pages`: `push()`
    /// above already refuses to enqueue anything once `seen` reaches
    /// `max_pages`, so `seen` can never exceed the cap. Re-checking it here
    /// used to cut the loop off as soon as `seen` *reached* (not exceeded)
    /// `max_pages`, even while the queue still held already-accepted,
    /// not-yet-fetched URLs -- e.g. `max_pages=1` hit the cap the instant
    /// the seed URL was pushed, so the seed itself was queued but the loop
    /// exited before ever popping and fetching it, returning zero pages for
    /// a request that should return exactly one. Draining strictly by queue
    /// emptiness still terminates (the queue can only ever hold up to
    /// `max_pages` URLs across the crawl's lifetime, by the same `push()`
    /// guard) while actually fetching everything the cap allowed in.
    pub fn has_capacity(&self) -> bool {
        !self.queue.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dedupes_normalized_variants() {
        let mut f = Frontier::new("https://example.com/", 10).unwrap();
        assert!(!f.push("https://example.com")); // same as seed after normalization
        assert!(!f.push("https://example.com/#section"));
        assert!(f.push("https://example.com/about"));
        assert!(!f.push("https://example.com/about/"));
    }

    #[test]
    fn rejects_off_domain() {
        let mut f = Frontier::new("https://example.com", 10).unwrap();
        assert!(!f.push("https://other.com/page"));
    }

    #[test]
    fn respects_max_pages() {
        let mut f = Frontier::new("https://example.com", 1).unwrap();
        assert!(!f.push("https://example.com/about"));
    }

    #[test]
    fn has_capacity_stays_true_until_the_queue_actually_drains() {
        // Regression test: `has_capacity` must reflect "is there still
        // something queued to fetch," not "is `seen` below `max_pages`" --
        // the seed push alone can already put `seen` at `max_pages`, and
        // the seed itself is still sitting in the queue at that point.
        let mut f = Frontier::new("https://example.com", 1).unwrap();
        // The cap (max_pages=1) was reached by the seed push itself...
        assert!(!f.push("https://example.com/about"));
        // ...but the seed is still unpopped in the queue, so there must
        // still be capacity to drain it.
        assert!(f.has_capacity());
        assert_eq!(f.pop().as_deref(), Some("https://example.com/"));
        // Now the queue is genuinely empty.
        assert!(!f.has_capacity());
    }
}
