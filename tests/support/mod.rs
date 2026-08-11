//! Minimal hand-rolled HTTP/1.1 mock server used by the crawler integration
//! tests. Deliberately dependency-free (just `tokio::net`) rather than
//! pulling in hyper/axum/wiremock: the test surface only needs to serve a
//! handful of canned GET responses (200/302/404/500 + headers) keyed by
//! path, so a ~60-line hand-rolled server is simpler than a new dependency.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpListener;

#[derive(Clone, Debug)]
pub struct MockResponse {
    pub status: u16,
    pub headers: Vec<(String, String)>,
    pub body: String,
}

impl MockResponse {
    pub fn html(body: impl Into<String>) -> Self {
        Self {
            status: 200,
            headers: vec![("Content-Type".to_string(), "text/html".to_string())],
            body: body.into(),
        }
    }

    pub fn xml(body: impl Into<String>) -> Self {
        Self {
            status: 200,
            headers: vec![("Content-Type".to_string(), "application/xml".to_string())],
            body: body.into(),
        }
    }

    pub fn text(status: u16, body: impl Into<String>) -> Self {
        Self {
            status,
            headers: Vec::new(),
            body: body.into(),
        }
    }

    /// A redirect response; `location` may be relative (e.g. "/next").
    pub fn redirect_to(location: impl Into<String>) -> Self {
        Self {
            status: 302,
            headers: vec![("Location".to_string(), location.into())],
            body: String::new(),
        }
    }

    fn not_found() -> Self {
        Self {
            status: 404,
            headers: Vec::new(),
            body: "not found".to_string(),
        }
    }
}

/// A background HTTP server bound to an OS-assigned loopback port, serving
/// canned `MockResponse`s keyed by request path. Routes can be registered
/// up front (`start`) or added later (`set_route`) once the server's real
/// address is known (useful for self-referencing redirects/links).
pub struct MockServer {
    pub addr: SocketAddr,
    routes: Arc<Mutex<HashMap<String, MockResponse>>>,
}

impl MockServer {
    pub async fn start(routes: HashMap<String, MockResponse>) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0")
            .await
            .expect("failed to bind mock server to a loopback port");
        let addr = listener.local_addr().expect("mock server has a local addr");
        let routes = Arc::new(Mutex::new(routes));

        let routes_for_task = Arc::clone(&routes);
        tokio::spawn(async move {
            loop {
                let (socket, _) = match listener.accept().await {
                    Ok(pair) => pair,
                    Err(_) => break,
                };
                tokio::spawn(handle_connection(socket, Arc::clone(&routes_for_task)));
            }
        });

        Self { addr, routes }
    }

    pub fn base_url(&self) -> String {
        format!("http://{}", self.addr)
    }

    pub fn set_route(&self, path: impl Into<String>, response: MockResponse) {
        self.routes.lock().unwrap().insert(path.into(), response);
    }
}

async fn handle_connection(
    socket: tokio::net::TcpStream,
    routes: Arc<Mutex<HashMap<String, MockResponse>>>,
) {
    let mut reader = BufReader::new(socket);

    let mut request_line = String::new();
    if reader.read_line(&mut request_line).await.unwrap_or(0) == 0 {
        return;
    }

    // Drain headers up to the blank line; we don't need them (GET only).
    loop {
        let mut line = String::new();
        match reader.read_line(&mut line).await {
            Ok(0) => return,
            Ok(_) if line == "\r\n" || line == "\n" => break,
            Ok(_) => continue,
            Err(_) => return,
        }
    }

    let path = request_line
        .split_whitespace()
        .nth(1)
        .unwrap_or("/")
        .to_string();

    let response = {
        let routes = routes.lock().unwrap();
        routes
            .get(&path)
            .cloned()
            .unwrap_or_else(MockResponse::not_found)
    };

    let mut out = format!(
        "HTTP/1.1 {} {}\r\n",
        response.status,
        status_text(response.status)
    );
    out.push_str(&format!("Content-Length: {}\r\n", response.body.len()));
    out.push_str("Connection: close\r\n");
    for (k, v) in &response.headers {
        out.push_str(&format!("{k}: {v}\r\n"));
    }
    out.push_str("\r\n");
    out.push_str(&response.body);

    let mut socket = reader.into_inner();
    let _ = socket.write_all(out.as_bytes()).await;
    let _ = socket.shutdown().await;
}

fn status_text(status: u16) -> &'static str {
    match status {
        200 => "OK",
        302 => "Found",
        404 => "Not Found",
        500 => "Internal Server Error",
        _ => "OK",
    }
}
