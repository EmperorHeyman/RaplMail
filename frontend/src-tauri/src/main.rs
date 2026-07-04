// Prevents an extra console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpListener;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Manager, RunEvent, State, WindowEvent};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

use base64::Engine;

/// Connection details handed to the webview so it can reach the local backend.
struct Backend {
    base: String,
    token: String,
}

/// Holds the spawned backend process so we can kill it on app exit.
struct ChildGuard(Mutex<Option<CommandChild>>);

/// Set when the user picks "Quit" from the tray, so the window-close handler
/// knows to actually exit instead of just hiding to the tray.
struct QuitFlag(AtomicBool);

/// Whether closing the window hides to the tray (true) or quits (false).
/// Driven by the "Minimize to tray on close" setting via `set_close_to_tray`.
struct CloseToTray(AtomicBool);

#[tauri::command]
fn set_close_to_tray(app: tauri::AppHandle, on: bool) {
    app.state::<CloseToTray>().0.store(on, Ordering::SeqCst);
}

/// Tell WebView2 to aggressively release renderer memory while the window is
/// hidden in the tray / minimized, and go back to normal when it's visible.
/// This is the documented lever for the renderer's working set: a tray-resident
/// WebView2 otherwise keeps its full JS heap + image/GPU caches (hundreds of MB)
/// alive even though nothing is on screen.
fn set_webview_memory_target(app: &tauri::AppHandle, low: bool) {
    #[cfg(windows)]
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.with_webview(move |wv| unsafe {
            use webview2_com::Microsoft::Web::WebView2::Win32::{
                ICoreWebView2_19, COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL,
            };
            use windows_core::Interface;
            if let Ok(core) = wv.controller().CoreWebView2() {
                if let Ok(wv19) = core.cast::<ICoreWebView2_19>() {
                    // 0 = NORMAL, 1 = LOW (matches COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL_*).
                    let _ = wv19.SetMemoryUsageTargetLevel(
                        COREWEBVIEW2_MEMORY_USAGE_TARGET_LEVEL(if low { 1 } else { 0 }),
                    );
                }
            }
        });
    }
    #[cfg(not(windows))]
    let _ = (app, low);
}

fn show_main(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
    set_webview_memory_target(app, false);
}

#[tauri::command]
fn backend_config(state: State<Backend>) -> serde_json::Value {
    serde_json::json!({ "base": state.base, "token": state.token })
}

fn _sanitize(name: &str) -> String {
    let n: String = name
        .chars()
        .map(|c| if r#"<>:"/\|?*"#.contains(c) { '_' } else { c })
        .collect();
    let n = n.trim().trim_matches('.').to_string();
    if n.is_empty() { "attachment".into() } else { n }
}

fn _write_temp(app: &tauri::AppHandle, filename: &str, data_b64: &str) -> Result<std::path::PathBuf, String> {
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(data_b64)
        .map_err(|e| e.to_string())?;
    let mut dir = std::env::temp_dir();
    dir.push("RaplMail-attachments");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join(_sanitize(filename));
    std::fs::write(&path, bytes).map_err(|e| e.to_string())?;
    let _ = app; // reserved for future use
    Ok(path)
}

/// Save an attachment to the user's Downloads folder; returns the full path.
#[tauri::command]
fn save_attachment(app: tauri::AppHandle, filename: String, data_b64: String) -> Result<String, String> {
    let bytes = base64::engine::general_purpose::STANDARD
        .decode(&data_b64)
        .map_err(|e| e.to_string())?;
    let mut dir = app
        .path()
        .download_dir()
        .unwrap_or_else(|_| std::env::temp_dir());
    dir.push("RaplMail");
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    // Avoid clobbering: foo.pdf, foo (1).pdf, ...
    let safe = _sanitize(&filename);
    let mut path = dir.join(&safe);
    if path.exists() {
        let stem = std::path::Path::new(&safe)
            .file_stem().and_then(|s| s.to_str()).unwrap_or("file").to_string();
        let ext = std::path::Path::new(&safe)
            .extension().and_then(|s| s.to_str()).map(|e| format!(".{e}")).unwrap_or_default();
        for i in 1..1000 {
            let cand = dir.join(format!("{stem} ({i}){ext}"));
            if !cand.exists() { path = cand; break; }
        }
    }
    std::fs::write(&path, bytes).map_err(|e| e.to_string())?;
    Ok(path.to_string_lossy().into_owned())
}

/// Write an attachment to a temp file and open it with the OS default app.
#[tauri::command]
fn open_attachment(app: tauri::AppHandle, filename: String, data_b64: String) -> Result<(), String> {
    let path = _write_temp(&app, &filename, &data_b64)?;
    app.opener()
        .open_path(path.to_string_lossy().to_string(), None::<&str>)
        .map_err(|e| e.to_string())
}

/// Reveal a saved file in the OS file manager.
#[tauri::command]
fn reveal_path(app: tauri::AppHandle, path: String) -> Result<(), String> {
    app.opener().reveal_item_in_dir(path).map_err(|e| e.to_string())
}

/// Open a URL in the user's default browser (links inside emails).
#[tauri::command]
fn open_url(app: tauri::AppHandle, url: String) -> Result<(), String> {
    let u = url.trim();
    if !(u.starts_with("http://") || u.starts_with("https://") || u.starts_with("mailto:")) {
        return Err("refused: only http(s)/mailto URLs".into());
    }
    app.opener().open_url(u, None::<&str>).map_err(|e| e.to_string())
}

/// Show an unread-count badge on the taskbar/dock icon (None clears it).
#[tauri::command]
fn set_unread_badge(app: tauri::AppHandle, count: i64) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.set_badge_count(if count > 0 { Some(count) } else { None });
    }
    if let Some(tray) = app.tray_by_id("main-tray") {
        let tip = if count > 0 {
            format!("RaplMail — {count} unread")
        } else {
            "RaplMail".to_string()
        };
        let _ = tray.set_tooltip(Some(&tip));
    }
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
        // Must be the FIRST plugin: a second launch (e.g. Start-menu / Win+search)
        // focuses the existing window instead of spawning another instance.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            show_main(app);
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .manage(Backend {
            base: base.clone(),
            token: token.clone(),
        })
        .manage(ChildGuard(Mutex::new(None)))
        .manage(QuitFlag(AtomicBool::new(false)))
        .manage(CloseToTray(AtomicBool::new(true)))
        .invoke_handler(tauri::generate_handler![
            backend_config, set_unread_badge, save_attachment, open_attachment, reveal_path,
            open_url, set_close_to_tray
        ])
        // Closing the window hides to the tray (so IMAP IDLE + notifications keep
        // running in the background) unless the user explicitly chose Quit.
        .on_window_event(|window, event| {
            match event {
                WindowEvent::CloseRequested { api, .. } => {
                    let app = window.app_handle();
                    let quitting = app.state::<QuitFlag>().0.load(Ordering::SeqCst);
                    let to_tray = app.state::<CloseToTray>().0.load(Ordering::SeqCst);
                    if !quitting && to_tray {
                        let _ = window.hide();
                        api.prevent_close();
                        // Hidden in the tray: let the renderer drop its heap/caches.
                        set_webview_memory_target(&window.app_handle(), true);
                    }
                }
                // Minimized → trim; restored/focused → back to normal.
                WindowEvent::Resized(_) => {
                    if window.is_minimized().unwrap_or(false) {
                        set_webview_memory_target(&window.app_handle(), true);
                    }
                }
                WindowEvent::Focused(true) => {
                    set_webview_memory_target(&window.app_handle(), false);
                }
                _ => {}
            }
        })
        .setup(move |app| {
            // System-tray icon: keeps RaplMail alive in the background with a
            // menu to reopen or fully quit; left-click reopens the window.
            let show_item = MenuItem::with_id(app, "show", "Open RaplMail", true, None::<&str>)?;
            let quit_item = MenuItem::with_id(app, "quit", "Quit RaplMail", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_item, &quit_item])?;
            TrayIconBuilder::with_id("main-tray")
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("RaplMail")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => show_main(app),
                    "quit" => {
                        app.state::<QuitFlag>().0.store(true, Ordering::SeqCst);
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main(&tray.app_handle());
                    }
                })
                .build(app)?;

            // Launch the bundled Python backend as a sidecar on the chosen port.
            let sidecar = app
                .shell()
                .sidecar("raplmail-backend")?
                .env("RAPLMAIL_PORT", port.to_string())
                .env("RAPLMAIL_TOKEN", token.clone())
                .env("RAPLMAIL_VERSION", app.package_info().version.to_string());
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
