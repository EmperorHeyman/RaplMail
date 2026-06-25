// Prevents an extra console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpListener;
use std::sync::Mutex;

use tauri::{Manager, RunEvent, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Connection details handed to the webview so it can reach the local backend.
struct Backend {
    base: String,
    token: String,
}

/// Holds the spawned backend process so we can kill it on app exit.
struct ChildGuard(Mutex<Option<CommandChild>>);

#[tauri::command]
fn backend_config(state: State<Backend>) -> serde_json::Value {
    serde_json::json!({ "base": state.base, "token": state.token })
}

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8765)
}

fn random_token() -> String {
    use rand::RngCore;
    let mut buf = [0u8; 24];
    rand::thread_rng().fill_bytes(&mut buf);
    buf.iter().map(|b| format!("{:02x}", b)).collect()
}

fn main() {
    let port = free_port();
    let token = random_token();
    let base = format!("http://127.0.0.1:{port}");

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Backend {
            base: base.clone(),
            token: token.clone(),
        })
        .manage(ChildGuard(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![backend_config])
        .setup(move |app| {
            // Launch the bundled Python backend as a sidecar on the chosen port.
            let sidecar = app
                .shell()
                .sidecar("raplmail-backend")?
                .env("RAPLMAIL_PORT", port.to_string())
                .env("RAPLMAIL_TOKEN", token.clone());
            let (mut rx, child) = sidecar.spawn()?;
            *app.state::<ChildGuard>().0.lock().unwrap() = Some(child);

            // Forward backend stdout/stderr to our log for debugging.
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            println!("[backend] {}", String::from_utf8_lossy(&line))
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("[backend] {}", String::from_utf8_lossy(&line))
                        }
                        _ => {}
                    }
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building RaplMail")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(child) = app.state::<ChildGuard>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}
