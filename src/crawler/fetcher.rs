use crate::error::AppError;

#[derive(Debug, Clone)]
pub struct FetchedPage {
    pub url: String,
    pub status: u16,
    pub body: String,
}

pub struct Fetcher {
    client: reqwest::Client,
}

impl Fetcher {
    pub fn new() -> Self {
        let client = reqwest::Client::builder()
            .user_agent("PyTagManagerBot/0.1 (+https://github.com/pytagmanager)")
            .build()
            .expect("failed to build HTTP client");
        Self { client }
    }

    pub async fn fetch(&self, url: &str) -> Result<FetchedPage, AppError> {
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

    /// Fetch an optional resource (robots.txt / sitemap.xml): network errors
    /// or non-2xx/3xx responses are treated as "not present" rather than fatal.
    pub async fn fetch_optional(&self, url: &str) -> Option<FetchedPage> {
        match self.fetch(url).await {
            Ok(page) if page.status < 400 => Some(page),
            _ => None,
        }
    }
}
