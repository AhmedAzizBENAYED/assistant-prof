//! Backend sidecar, walking-skeleton version (T-006, ADR-038, ADR-039).
//!
//! Spawns the packaged backend with `--port 0 --exit-on-stdin-eof` and the session token in
//! `ASSISTANT_PROF_TOKEN`, reads its ready line from stdout, then checks the authorised
//! `/health`. The write end of the backend's stdin stays open for the shell's whole life: when
//! the shell dies, even killed from the Task Manager, the OS closes it and the backend shuts
//! down by itself. T-801 adds crash restart, process-tree kill and the French error screen.

use std::fmt;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError};
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;

/// Environment variable naming the backend executable (overrides the repository default).
pub const BACKEND_EXE_ENV: &str = "ASSISTANT_PROF_BACKEND_EXE";
const TOKEN_ENV: &str = "ASSISTANT_PROF_TOKEN";
const TOKEN_HEADER: &str = "X-Session-Token";
const TOKEN_BYTES: usize = 32;
const HEX: &[u8; 16] = b"0123456789abcdef";
const HTTP_TIMEOUT: Duration = Duration::from_secs(5);
const EXIT_POLL: Duration = Duration::from_millis(50);
/// Windows `CREATE_NO_WINDOW`: the backend is a console program, but no console is shown.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Why the backend could not be started or reached.
#[derive(Debug)]
pub enum SidecarError {
    Token(getrandom::Error),
    Spawn(io::Error),
    ReadyTimeout(Duration),
    ExitedBeforeReady,
    BadReadyLine(String),
    Http(io::Error),
    BadHttpResponse,
    Unhealthy(u16),
}

impl fmt::Display for SidecarError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Token(err) => write!(f, "cannot generate the session token: {err}"),
            Self::Spawn(err) => write!(f, "cannot start the backend: {err}"),
            Self::ReadyTimeout(after) => write!(f, "no ready line after {} s", after.as_secs()),
            Self::ExitedBeforeReady => write!(f, "the backend exited before its ready line"),
            Self::BadReadyLine(why) => write!(f, "invalid ready line: {why}"),
            Self::Http(err) => write!(f, "cannot reach the backend: {err}"),
            Self::BadHttpResponse => write!(f, "invalid HTTP response from the backend"),
            Self::Unhealthy(status) => write!(f, "/health answered HTTP {status}"),
        }
    }
}

impl std::error::Error for SidecarError {}

/// The `{"event":"ready","port":…,"version":…}` line written by the backend once listening.
#[derive(Debug, PartialEq, Eq, Deserialize)]
pub struct ReadyLine {
    pub port: u16,
    pub version: String,
}

/// Parses the backend's ready line; the port must be a real (non-zero) port.
pub fn parse_ready_line(line: &str) -> Result<ReadyLine, SidecarError> {
    #[derive(Deserialize)]
    struct Raw {
        event: String,
        #[serde(flatten)]
        ready: ReadyLine,
    }
    let raw: Raw = serde_json::from_str(line.trim())
        .map_err(|err| SidecarError::BadReadyLine(err.to_string()))?;
    if raw.event != "ready" {
        return Err(SidecarError::BadReadyLine(format!(
            "event is {:?}",
            raw.event
        )));
    }
    if raw.ready.port == 0 {
        return Err(SidecarError::BadReadyLine("port is 0".to_owned()));
    }
    Ok(raw.ready)
}

/// Generates a fresh session token: 32 random bytes as 64 lowercase hex characters.
pub fn generate_token() -> Result<String, SidecarError> {
    let mut bytes = [0_u8; TOKEN_BYTES];
    getrandom::fill(&mut bytes).map_err(SidecarError::Token)?;
    Ok(bytes
        .iter()
        .flat_map(|byte| [HEX[usize::from(byte >> 4)], HEX[usize::from(byte & 0x0f)]])
        .map(char::from)
        .collect())
}

/// Reads the first line of `reader` on a thread and sends it (`None` at end of file), then keeps
/// draining the stream so the child never blocks on a full pipe.
pub fn spawn_first_line_reader<R: Read + Send + 'static>(
    reader: R,
) -> Receiver<io::Result<Option<String>>> {
    let (sender, receiver) = mpsc::channel();
    thread::spawn(move || {
        let mut reader = BufReader::new(reader);
        let mut line = String::new();
        let first = reader
            .read_line(&mut line)
            .map(|read| (read > 0).then_some(line));
        let keep_draining = matches!(first, Ok(Some(_)));
        // The receiver may be gone after a timeout; draining still matters then.
        let _ = sender.send(first);
        if keep_draining {
            let _ = io::copy(&mut reader, &mut io::sink());
        }
    });
    receiver
}

/// Waits up to `timeout` for the ready line sent by [`spawn_first_line_reader`].
pub fn recv_ready_line(
    lines: &Receiver<io::Result<Option<String>>>,
    timeout: Duration,
) -> Result<ReadyLine, SidecarError> {
    match lines.recv_timeout(timeout) {
        Ok(Ok(Some(line))) => parse_ready_line(&line),
        Ok(Ok(None) | Err(_)) | Err(RecvTimeoutError::Disconnected) => {
            Err(SidecarError::ExitedBeforeReady)
        }
        Err(RecvTimeoutError::Timeout) => Err(SidecarError::ReadyTimeout(timeout)),
    }
}

/// Sends one bodiless request to the backend on 127.0.0.1 and returns the HTTP status code.
/// Hand-written on purpose (ADR-039): one local request does not justify an HTTP client crate.
pub fn http_request(port: u16, method: &str, path: &str, token: &str) -> Result<u16, SidecarError> {
    let address = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let mut stream =
        TcpStream::connect_timeout(&address, HTTP_TIMEOUT).map_err(SidecarError::Http)?;
    stream
        .set_read_timeout(Some(HTTP_TIMEOUT))
        .and_then(|()| stream.set_write_timeout(Some(HTTP_TIMEOUT)))
        .map_err(SidecarError::Http)?;
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n{TOKEN_HEADER}: {token}\r\n\
         Content-Length: 0\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(SidecarError::Http)?;
    let mut status_line = String::new();
    BufReader::new(stream)
        .read_line(&mut status_line)
        .map_err(SidecarError::Http)?;
    parse_status_line(&status_line)
}

fn parse_status_line(line: &str) -> Result<u16, SidecarError> {
    let mut parts = line.split_whitespace();
    match (parts.next(), parts.next()) {
        (Some(version), Some(code)) if version.starts_with("HTTP/1.") => {
            code.parse().map_err(|_| SidecarError::BadHttpResponse)
        }
        _ => Err(SidecarError::BadHttpResponse),
    }
}

/// Where the packaged backend is: `ASSISTANT_PROF_BACKEND_EXE`, else the repository build output.
/// T-803 replaces the default with the installer's resource directory.
pub fn backend_exe() -> PathBuf {
    std::env::var_os(BACKEND_EXE_ENV).map_or_else(
        || {
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("../../backend/dist/assistant-prof-backend")
                .join(format!(
                    "assistant-prof-backend{}",
                    std::env::consts::EXE_SUFFIX
                ))
        },
        PathBuf::from,
    )
}

/// A running, healthy backend. Dropping it kills the process if it is still alive.
pub struct Sidecar {
    child: Child,
    /// Write end of the backend's stdin, kept open: closing it asks the backend to stop.
    stdin: Option<ChildStdin>,
    token: String,
    pub port: u16,
    pub version: String,
}

impl Sidecar {
    /// Spawns `exe`, waits up to `ready_timeout` for its ready line, then checks `/health`.
    pub fn start(exe: &Path, ready_timeout: Duration) -> Result<Self, SidecarError> {
        let token = generate_token()?;
        let mut command = Command::new(exe);
        command
            .args(["--port", "0", "--exit-on-stdin-eof"])
            .env(TOKEN_ENV, &token)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(CREATE_NO_WINDOW);
        }
        let mut child = command.spawn().map_err(SidecarError::Spawn)?;
        let stdin = child.stdin.take();
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        if let Some(stderr) = stderr {
            forward_stderr(stderr);
        }
        let mut sidecar = Self {
            child,
            stdin,
            token,
            port: 0,
            version: String::new(),
        };
        let lines = match stdout {
            Some(stdout) => spawn_first_line_reader(stdout),
            None => return Err(SidecarError::ExitedBeforeReady),
        };
        let ready = recv_ready_line(&lines, ready_timeout)?;
        sidecar.port = ready.port;
        sidecar.version = ready.version;
        match http_request(sidecar.port, "GET", "/health", &sidecar.token)? {
            200 => Ok(sidecar),
            status => Err(SidecarError::Unhealthy(status)),
        }
    }

    /// The backend's process ID.
    pub fn pid(&self) -> u32 {
        self.child.id()
    }

    /// Asks the backend to stop (`POST /shutdown`, then stdin closed) and kills it after `grace`.
    pub fn stop(&mut self, grace: Duration) {
        // Best effort: if the request fails, closing stdin and the kill below still stop it.
        let _ = http_request(self.port, "POST", "/shutdown", &self.token);
        self.stdin = None;
        let deadline = Instant::now() + grace;
        while Instant::now() < deadline {
            if !matches!(self.child.try_wait(), Ok(None)) {
                return;
            }
            thread::sleep(EXIT_POLL);
        }
        self.kill();
    }

    fn kill(&mut self) {
        if matches!(self.child.try_wait(), Ok(None)) {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

impl Drop for Sidecar {
    fn drop(&mut self) {
        self.kill();
    }
}

/// Copies the backend's stderr (startup errors only outside dev mode) to the shell's stderr.
fn forward_stderr<R: Read + Send + 'static>(stderr: R) {
    thread::spawn(move || {
        for line in BufReader::new(stderr).lines().map_while(Result::ok) {
            eprintln!("backend: {line}");
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use std::net::TcpListener;

    #[test]
    fn parses_a_ready_line() {
        let line = "{\"event\":\"ready\",\"port\":51234,\"version\":\"0.1.0\"}\n";
        let ready = parse_ready_line(line).expect("valid line");
        assert_eq!(
            ready,
            ReadyLine {
                port: 51234,
                version: "0.1.0".to_owned()
            }
        );
    }

    #[test]
    fn rejects_bad_ready_lines() {
        for line in [
            "not json",
            "{\"event\":\"started\",\"port\":1,\"version\":\"0.1.0\"}",
            "{\"event\":\"ready\",\"version\":\"0.1.0\"}",
            "{\"event\":\"ready\",\"port\":0,\"version\":\"0.1.0\"}",
            "{\"event\":\"ready\",\"port\":70000,\"version\":\"0.1.0\"}",
        ] {
            assert!(
                matches!(parse_ready_line(line), Err(SidecarError::BadReadyLine(_))),
                "{line}"
            );
        }
    }

    #[test]
    fn tokens_are_64_hex_chars_and_fresh() {
        let first = generate_token().expect("token");
        let second = generate_token().expect("token");
        assert_eq!(first.len(), 64);
        assert!(
            first
                .chars()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
        );
        assert_ne!(first, second);
    }

    #[test]
    fn receives_the_first_line_and_drains_the_rest() {
        let output = Cursor::new(b"{\"event\":\"ready\",\"port\":4321,\"version\":\"x\"}\nmore\n");
        let lines = spawn_first_line_reader(output);
        let ready = recv_ready_line(&lines, Duration::from_secs(5)).expect("ready");
        assert_eq!(ready.port, 4321);
    }

    #[test]
    fn end_of_file_before_ready_is_reported() {
        let lines = spawn_first_line_reader(Cursor::new(Vec::new()));
        assert!(matches!(
            recv_ready_line(&lines, Duration::from_secs(5)),
            Err(SidecarError::ExitedBeforeReady)
        ));
    }

    #[test]
    fn missing_ready_line_times_out() {
        struct Silent;
        impl Read for Silent {
            fn read(&mut self, _: &mut [u8]) -> io::Result<usize> {
                thread::sleep(Duration::from_secs(2));
                Ok(0)
            }
        }
        let lines = spawn_first_line_reader(Silent);
        assert!(matches!(
            recv_ready_line(&lines, Duration::from_millis(100)),
            Err(SidecarError::ReadyTimeout(_))
        ));
    }

    /// Serves one request with `status_line` and returns the port and the received request.
    fn one_shot_server(status_line: &'static str) -> (u16, thread::JoinHandle<String>) {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).expect("bind");
        let port = listener.local_addr().expect("address").port();
        let server = thread::spawn(move || {
            let (stream, _) = listener.accept().expect("accept");
            let mut reader = BufReader::new(stream);
            let mut request = String::new();
            loop {
                let mut line = String::new();
                if reader.read_line(&mut line).expect("read") == 0 || line == "\r\n" {
                    break;
                }
                request.push_str(&line);
            }
            let mut stream = reader.into_inner();
            stream
                .write_all(format!("{status_line}\r\nContent-Length: 0\r\n\r\n").as_bytes())
                .expect("write");
            request
        });
        (port, server)
    }

    #[test]
    fn health_request_sends_the_token_and_returns_the_status() {
        let (port, server) = one_shot_server("HTTP/1.1 200 OK");
        assert_eq!(
            http_request(port, "GET", "/health", "secret").expect("status"),
            200
        );
        let request = server.join().expect("server");
        assert!(request.starts_with("GET /health HTTP/1.1\r\n"));
        assert!(request.contains("\r\nX-Session-Token: secret\r\n"));
    }

    #[test]
    fn unauthorised_status_is_returned() {
        let (port, server) = one_shot_server("HTTP/1.1 401 Unauthorized");
        assert_eq!(
            http_request(port, "GET", "/health", "wrong").expect("status"),
            401
        );
        server.join().expect("server");
    }

    #[test]
    fn refused_connection_is_an_http_error() {
        let port = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))
            .and_then(|listener| listener.local_addr())
            .expect("free port")
            .port(); // the listener is dropped here, so nothing listens on the port
        assert!(matches!(
            http_request(port, "GET", "/health", "t"),
            Err(SidecarError::Http(_))
        ));
    }

    #[test]
    fn status_line_parsing() {
        assert_eq!(
            parse_status_line("HTTP/1.1 202 Accepted\r\n").expect("ok"),
            202
        );
        assert!(parse_status_line("garbage").is_err());
        assert!(parse_status_line("HTTP/1.1 abc\r\n").is_err());
        assert!(parse_status_line("").is_err());
    }

    #[test]
    fn missing_executable_is_a_spawn_error() {
        let exe = Path::new("this-backend-does-not-exist.exe");
        assert!(matches!(
            Sidecar::start(exe, Duration::from_secs(1)),
            Err(SidecarError::Spawn(_))
        ));
    }
}
