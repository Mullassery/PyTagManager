use pyo3::exceptions::PyRuntimeError;
use pyo3::PyErr;
use std::fmt;

#[derive(Debug)]
pub enum AppError {
    Http(String),
    InvalidUrl(String),
    /// Rejected by the SSRF guard: the target URL resolves to a
    /// loopback/private/link-local/cloud-metadata address.
    Blocked(String),
    /// A `--header`/`headers=` value passed to the crawler wasn't a valid
    /// HTTP header name or value.
    InvalidHeader(String),
}

impl fmt::Display for AppError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AppError::Http(msg) => write!(f, "HTTP error: {}", msg),
            AppError::InvalidUrl(msg) => write!(f, "Invalid URL: {}", msg),
            AppError::Blocked(msg) => write!(f, "Blocked by SSRF guard: {}", msg),
            AppError::InvalidHeader(msg) => write!(f, "Invalid header: {}", msg),
        }
    }
}

impl std::error::Error for AppError {}

impl From<AppError> for PyErr {
    fn from(err: AppError) -> PyErr {
        PyRuntimeError::new_err(err.to_string())
    }
}

impl From<reqwest::Error> for AppError {
    fn from(err: reqwest::Error) -> Self {
        AppError::Http(err.to_string())
    }
}

impl From<url::ParseError> for AppError {
    fn from(err: url::ParseError) -> Self {
        AppError::InvalidUrl(err.to_string())
    }
}
