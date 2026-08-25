// Optimizer GUI - Tauri Shell
// Starts backend-sidecar (frozen Python/FastAPI) automatically when the app opens.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri_plugin_shell::ShellExt;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let shell = app.shell();
            let sidecar = shell
                .sidecar("backend-sidecar")
                .expect("failed to load backend-sidecar - check externalBin in tauri.conf.json");

            tauri::async_runtime::spawn(async move {
                let (mut rx, _child) = sidecar.spawn().expect("failed to start backend-sidecar");
                while let Some(event) = rx.recv().await {
                    if let tauri_plugin_shell::process::CommandEvent::Stderr(line) = event {
                        eprintln!("[backend] {}", String::from_utf8_lossy(&line));
                    }
                }
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running Tauri application");
}
