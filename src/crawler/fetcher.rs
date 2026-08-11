use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};

use crate::error::AppError;

#[derive(Debug, Clone)]
pub struct FetchedPage {
    pub url: String,
    pub status: u16,
    pub body: String,
}

pub struct Fetcher {
    client: reqwest::Client,
    /// When true (the default via `Fetcher::new`), every fetch is preceded
    /// by a resolved-IP SSRF check (see `assert_target_not_blocked`).
    ssrf_guard: bool,
}

impl Default for Fetcher {
    fn default() -> Self {
        Self::new()
    }
}

impl Fetcher {
    /// Every real entry point (the CLI, via `crawler::crawl`, and the
    /// PyO3-exposed `crawl` pyfunction) constructs its `Fetcher` this way,
    /// so the SSRF guard is always on in production.
    pub fn new() -> Self {
        Self::with_ssrf_guard(true)
    }

    /// Construct a `Fetcher` with the SSRF guard optionally disabled.
    /// Production code never passes `false` here -- this exists so
    /// integration tests (see `crawler::orchestrator::crawl_with_fetcher`)
    /// can drive the crawler against a local mock HTTP server on loopback,
    /// which the guard would otherwise (correctly) refuse to fetch.
    pub fn with_ssrf_guard(enabled: bool) -> Self {
        let client = reqwest::Client::builder()
            .user_agent("PyTagManagerBot/0.1 (+https://github.com/pytagmanager)")
            .build()
            .expect("failed to build HTTP client");
        Self {
            client,
            ssrf_guard: enabled,
        }
    }

    pub async fn fetch(&self, url: &str) -> Result<FetchedPage, AppError> {
        if self.ssrf_guard {
            assert_target_not_blocked(url).await?;
        }
        let resp = self.client.get(url).send().await?;
        let status = resp.status().as_u16();
        let final_url = resp.url().to_string();
        let body = resp.text().await?;
        Ok(FetchedPage {
            url: final_url,
            status,
            body,
        })
    }

    /// Fetch an optional resource (robots.txt / sitemap.xml): network errors,
    /// SSRF-guard rejections, or non-2xx/3xx responses are treated as "not
    /// present" rather than fatal.
    pub async fn fetch_optional(&self, url: &str) -> Option<FetchedPage> {
        match self.fetch(url).await {
            Ok(page) if page.status < 400 => Some(page),
            _ => None,
        }
    }
}

/// Basic SSRF guard: resolves `url`'s host and rejects it if any resolved
/// address falls in a loopback/private/link-local/cloud-metadata range.
/// This is a simple resolved-IP check performed once per fetch, not a full
/// policy engine -- in particular it does not re-check redirect hops that
/// `reqwest` follows internally after this initial check passes.
async fn assert_target_not_blocked(url: &str) -> Result<(), AppError> {
    let parsed = url::Url::parse(url)?;
    let host = parsed
        .host_str()
        .ok_or_else(|| AppError::InvalidUrl(format!("no host in url: {url}")))?;

    // A literal IP in the URL (e.g. "http://127.0.0.1/") needs no DNS
    // lookup -- check it directly.
    if let Ok(ip) = host.parse::<IpAddr>() {
        return if is_blocked_ip(ip) {
            Err(AppError::Blocked(format!(
                "{url} targets disallowed address {ip}"
            )))
        } else {
            Ok(())
        };
    }

    let port = parsed.port_or_known_default().unwrap_or(80);
    let lookup_target = format!("{host}:{port}");
    let mut addrs = tokio::net::lookup_host(&lookup_target)
        .await
        .map_err(|e| AppError::Http(format!("DNS resolution failed for {host}: {e}")))?
        .peekable();

    if addrs.peek().is_none() {
        return Err(AppError::Http(format!(
            "DNS resolution returned no addresses for {host}"
        )));
    }

    for addr in addrs {
        if is_blocked_ip(addr.ip()) {
            return Err(AppError::Blocked(format!(
                "{url} ({host}) resolves to disallowed address {}",
                addr.ip()
            )));
        }
    }
    Ok(())
}

/// True if `ip` is loopback, RFC1918 private, link-local (which covers the
/// 169.254.169.254 cloud-metadata address), unspecified, broadcast, or the
/// IPv6 equivalents of those ranges.
fn is_blocked_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => is_blocked_ipv4(v4),
        IpAddr::V6(v6) => match v6.to_ipv4_mapped() {
            Some(mapped) => is_blocked_ipv4(mapped),
            None => is_blocked_ipv6(v6),
        },
    }
}

fn is_blocked_ipv4(ip: Ipv4Addr) -> bool {
    ip.is_loopback()
        || ip.is_private()
        || ip.is_link_local()
        || ip.is_unspecified()
        || ip.is_broadcast()
}

fn is_blocked_ipv6(ip: Ipv6Addr) -> bool {
    if ip.is_loopback() || ip.is_unspecified() {
        return true;
    }
    let segments = ip.segments();
    let is_unique_local = segments[0] & 0xfe00 == 0xfc00; // fc00::/7
    let is_link_local = segments[0] & 0xffc0 == 0xfe80; // fe80::/10
    is_unique_local || is_link_local
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn blocks_loopback_and_private_and_link_local_ipv4() {
        assert!(is_blocked_ip("127.0.0.1".parse().unwrap()));
        assert!(is_blocked_ip("169.254.169.254".parse().unwrap())); // cloud metadata
        assert!(is_blocked_ip("10.0.0.5".parse().unwrap()));
        assert!(is_blocked_ip("172.16.0.5".parse().unwrap()));
        assert!(is_blocked_ip("192.168.1.5".parse().unwrap()));
        assert!(is_blocked_ip("0.0.0.0".parse().unwrap()));
    }

    #[test]
    fn allows_public_ipv4() {
        assert!(!is_blocked_ip("93.184.216.34".parse().unwrap()));
        assert!(!is_blocked_ip("8.8.8.8".parse().unwrap()));
    }

    #[test]
    fn blocks_loopback_and_link_local_and_unique_local_ipv6() {
        assert!(is_blocked_ip("::1".parse().unwrap()));
        assert!(is_blocked_ip("fe80::1".parse().unwrap()));
        assert!(is_blocked_ip("fc00::1".parse().unwrap()));
        assert!(is_blocked_ip("fd12:3456:789a::1".parse().unwrap()));
    }

    #[test]
    fn allows_public_ipv6() {
        assert!(!is_blocked_ip("2606:4700:4700::1111".parse().unwrap()));
    }

    #[test]
    fn blocks_ipv4_mapped_ipv6_of_blocked_address() {
        assert!(is_blocked_ip("::ffff:127.0.0.1".parse().unwrap()));
        assert!(is_blocked_ip("::ffff:169.254.169.254".parse().unwrap()));
    }

    #[tokio::test]
    async fn fetch_rejects_loopback_url() {
        let fetcher = Fetcher::new();
        let err = fetcher.fetch("http://127.0.0.1/").await.unwrap_err();
        assert!(
            matches!(err, AppError::Blocked(_)),
            "expected Blocked, got {err:?}"
        );
    }

    #[tokio::test]
    async fn fetch_rejects_cloud_metadata_url() {
        let fetcher = Fetcher::new();
        let err = fetcher.fetch("http://169.254.169.254/").await.unwrap_err();
        assert!(
            matches!(err, AppError::Blocked(_)),
            "expected Blocked, got {err:?}"
        );
    }

    #[tokio::test]
    async fn fetch_optional_treats_blocked_target_as_absent() {
        let fetcher = Fetcher::new();
        assert!(fetcher
            .fetch_optional("http://127.0.0.1/robots.txt")
            .await
            .is_none());
    }

    #[tokio::test]
    async fn ssrf_guard_can_be_disabled_for_tests() {
        // With the guard off, the loopback check is skipped entirely; the
        // fetch still fails here (nothing is listening on this fixed port),
        // but with a plain Http error rather than a Blocked one -- proving
        // the guard, not connectivity, was what previously produced Blocked.
        let fetcher = Fetcher::with_ssrf_guard(false);
        let err = fetcher.fetch("http://127.0.0.1:1/").await.unwrap_err();
        assert!(
            matches!(err, AppError::Http(_)),
            "expected Http, got {err:?}"
        );
    }
}
