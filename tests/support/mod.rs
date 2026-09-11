//! Minimal hand-rolled HTTP/1.1 mock server used by the crawler integration
//! tests. Deliberately dependency-free (just `tokio::net`) rather than
//! pulling in hyper/axum/wiremock: the test surface only needs to serve a
//! handful of canned GET responses (200/302/404/500 + headers) keyed by
//! path, so a ~60-line hand-rolled server is simpler than a new dependency.

use std::collections::{HashMap, VecDeque};
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::TcpListener;

/// One received request: its path plus request headers (lowercased names),
/// in receipt order.
type ReceivedRequests = Arc<Mutex<Vec<(String, Vec<(String, String)>)>>>;

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
    /// Per-path queues of responses to serve in order (for testing retry
    /// behavior, e.g. 503 then 200); once a queue is down to its last
    /// entry, that entry keeps being served rather than falling through to
    /// 404. Checked before `routes`.
    sequences: Arc<Mutex<HashMap<String, VecDeque<MockResponse>>>>,
    /// Every request's path plus its request headers (lowercased names),
    /// in receipt order -- lets tests assert on what the crawler actually
    /// sent (e.g. a custom `--header`/`Cookie`).
    received: ReceivedRequests,
}

impl MockServer {
    pub async fn start(routes: HashMap<String, MockResponse>) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0")
            .await
            .expect("failed to bind mock server to a loopback port");
        let addr = listener.local_addr().expect("mock server has a local addr");
        let routes = Arc::new(Mutex::new(routes));
        let sequences = Arc::new(Mutex::new(HashMap::new()));
        let received = Arc::new(Mutex::new(Vec::new()));

        let routes_for_task = Arc::clone(&routes);
        let sequences_for_task = Arc::clone(&sequences);
        let received_for_task = Arc::clone(&received);
        tokio::spawn(async move {
            loop {
                let (socket, _) = match listener.accept().await {
                    Ok(pair) => pair,
                    Err(_) => break,
                };
                tokio::spawn(handle_connection(
                    socket,
                    Arc::clone(&routes_for_task),
                    Arc::clone(&sequences_for_task),
                    Arc::clone(&received_for_task),
                ));
            }
        });

        Self {
            addr,
            routes,
            sequences,
            received,
        }
    }

    pub fn base_url(&self) -> String {
        format!("http://{}", self.addr)
    }

    pub fn set_route(&self, path: impl Into<String>, response: MockResponse) {
        self.routes.lock().unwrap().insert(path.into(), response);
    }

    /// Serve `responses` in order for `path` across successive requests;
    /// the last one repeats indefinitely once the queue is exhausted.
    pub fn set_sequence(&self, path: impl Into<String>, responses: Vec<MockResponse>) {
        self.sequences
            .lock()
            .unwrap()
            .insert(path.into(), responses.into());
    }

    /// Headers (lowercased names) the server received for the given path's
    /// most recent request, if any.
    pub fn last_received_headers(&self, path: &str) -> Option<Vec<(String, String)>> {
        self.received
            .lock()
            .unwrap()
            .iter()
            .rev()
            .find(|(p, _)| p == path)
            .map(|(_, headers)| headers.clone())
    }

    pub fn request_count(&self, path: &str) -> usize {
        self.received
            .lock()
            .unwrap()
            .iter()
            .filter(|(p, _)| p == path)
            .count()
    }
}

async fn handle_connection(
    socket: tokio::net::TcpStream,
    routes: Arc<Mutex<HashMap<String, MockResponse>>>,
    sequences: Arc<Mutex<HashMap<String, VecDeque<MockResponse>>>>,
    received: ReceivedRequests,
) {
    let mut reader = BufReader::new(socket);

    let mut request_line = String::new();
    if reader.read_line(&mut request_line).await.unwrap_or(0) == 0 {
        return;
    }

    let mut headers = Vec::new();
    loop {
        let mut line = String::new();
        match reader.read_line(&mut line).await {
            Ok(0) => return,
            Ok(_) if line == "\r\n" || line == "\n" => break,
            Ok(_) => {
                if let Some((name, value)) = line.trim_end().split_once(':') {
                    headers.push((name.trim().to_lowercase(), value.trim().to_string()));
                }
            }
            Err(_) => return,
        }
    }

    let path = request_line
        .split_whitespace()
        .nth(1)
        .unwrap_or("/")
        .to_string();

    received.lock().unwrap().push((path.clone(), headers));

    let sequenced = {
        let mut sequences = sequences.lock().unwrap();
        sequences.get_mut(&path).and_then(|queue| {
            if queue.len() > 1 {
                queue.pop_front()
            } else {
                queue.front().cloned()
            }
        })
    };

    let response = match sequenced {
        Some(r) => r,
        None => {
            let routes = routes.lock().unwrap();
            routes
                .get(&path)
                .cloned()
                .unwrap_or_else(MockResponse::not_found)
        }
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
