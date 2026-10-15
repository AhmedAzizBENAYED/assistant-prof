//! Thin desktop shell: starts the backend sidecar and stops it on exit (T-006).
//! T-801 adds crash restart, single instance, window state and dialogs; T-804 the updater.

mod sidecar;

use std::sync::{Mutex, PoisonError};
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent};

use crate::sidecar::Sidecar;

/// How long the backend may take to write its ready line (ARCH §4).
const READY_TIMEOUT: Duration = Duration::from_secs(20);
/// How long a graceful shutdown may take before the backend is killed (ARCH §4).
const SHUTDOWN_GRACE: Duration = Duration::from_secs(3);

/// The running backend, once healthy.
#[derive(Default)]
struct Backend(Mutex<Option<Sidecar>>);

/// Builds and runs the Tauri application.
///
/// # Panics
///
/// Panics if the Tauri runtime fails to start.
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let launched = Instant::now();
    let app = tauri::Builder::default()
        .manage(Backend::default())
        .setup(move |app| {
            let handle = app.handle().clone();
            // Off the main thread, so the window shows while the backend starts.
            thread::spawn(move || start_backend(&handle, launched));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the Tauri application");
    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            let sidecar = handle
                .state::<Backend>()
                .0
                .lock()
                .unwrap_or_else(PoisonError::into_inner)
                .take();
            if let Some(mut sidecar) = sidecar {
                sidecar.stop(SHUTDOWN_GRACE);
            }
        }
    });
}

/// Starts the backend and reports the outcome as one JSON line on stdout, read by
/// `just measure`. If the app exits before this finishes, the backend still stops: the
/// shell's end of its stdin closes with the process (ADR-039).
fn start_backend(handle: &AppHandle, launched: Instant) {
    let exe = sidecar::backend_exe();
    let event = match Sidecar::start(&exe, READY_TIMEOUT) {
        Ok(sidecar) => {
            let event = serde_json::json!({
                "event": "backend_healthy",
                "elapsed_ms": launched.elapsed().as_millis(),
                "port": sidecar.port,
                "backend_pid": sidecar.pid(),
                "version": sidecar.version,
            });
            *handle
                .state::<Backend>()
                .0
                .lock()
                .unwrap_or_else(PoisonError::into_inner) = Some(sidecar);
            event
        }
        Err(err) => serde_json::json!({
            "event": "backend_failed",
            "error": err.to_string(),
            "exe": exe.display().to_string(),
        }),
    };
    println!("{event}");
}
