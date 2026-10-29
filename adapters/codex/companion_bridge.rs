//! JSON-v1 display bridge. No character logic or terminal output lives here.
//! The existing ambient image slot owns drawing, cursor restore, and exit cleanup.
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::sync::{mpsc, Mutex, OnceLock};
use std::time::{Duration, Instant};
use ratatui::layout::Rect;
use serde_json::{json, Value};

struct Reply { value: Value, received: Instant }
struct Bridge {
    composer: Option<Rect>,
    popup: bool,
    last_input: Option<Instant>,
    effort: Option<String>,
    effort_baseline: bool,
    tx: mpsc::SyncSender<Value>,
    rx: mpsc::Receiver<Option<Value>>,
    latest: Option<Reply>,
}
static BRIDGE: OnceLock<Option<Mutex<Bridge>>> = OnceLock::new();

fn bridge() -> Option<&'static Mutex<Bridge>> {
    BRIDGE.get_or_init(|| {
        let path = std::env::var_os("CODEX_THEATER_SOCKET")?;
        let (tx, requests) = mpsc::sync_channel::<Value>(1);
        let (responses, rx) = mpsc::sync_channel::<Option<Value>>(2);
        std::thread::Builder::new().name("companion-ipc".into()).spawn(move || {
            for message in requests {
                let reply = exchange(&path, &message);
                let _ = responses.try_send(reply);
            }
        }).ok()?;
        Some(Mutex::new(Bridge { composer: None, popup: false, last_input: None, effort: None, effort_baseline: true, tx, rx, latest: None }))
    }).as_ref()
}

#[cfg(unix)]
fn exchange(path: &std::ffi::OsStr, message: &Value) -> Option<Value> {
    use std::os::unix::net::UnixStream;
    let mut stream = UnixStream::connect(path).ok()?;
    stream.set_read_timeout(Some(Duration::from_millis(250))).ok()?;
    stream.set_write_timeout(Some(Duration::from_millis(250))).ok()?;
    serde_json::to_writer(&mut stream, message).ok()?;
    stream.write_all(b"\n").ok()?;
    let mut line = String::new();
    BufReader::new(stream).take(65536).read_line(&mut line).ok()?;
    serde_json::from_str(&line).ok()
}

#[cfg(not(unix))]
fn exchange(_: &std::ffi::OsStr, _: &Value) -> Option<Value> { None }

pub(crate) fn enabled() -> bool { bridge().is_some() }

pub(crate) fn begin_frame() {
    if let Some(lock) = bridge() {
        if let Ok(mut b) = lock.lock() { b.composer = None; b.popup = false; }
    }
}

pub(crate) fn record_composer(rect: Rect) {
    if let Some(lock) = bridge() {
        if let Ok(mut b) = lock.lock() { b.composer = Some(rect); }
    }
}

pub(crate) fn record_popup() {
    if let Some(lock) = bridge() {
        if let Ok(mut b) = lock.lock() { b.popup = true; }
    }
}

pub(crate) fn note_input() {
    if let Some(lock) = bridge() {
        if let Ok(mut b) = lock.lock() { b.last_input = Some(Instant::now()); }
    }
}

/// Observe the effective upstream value; repeated redraws must not restart an effect.
pub(crate) fn note_effort(effort: &str, baseline: bool) {
    let effort = if effort.is_empty() { "none" } else { effort };
    if let Some(lock) = bridge() {
        if let Ok(mut b) = lock.lock() {
            if baseline || b.effort.as_deref() != Some(effort) {
                if !baseline { b.last_input = None; }
                b.effort = Some(effort.to_owned());
                b.effort_baseline = baseline;
            }
        }
    }
}

pub(crate) fn frame(
    screen: Rect, model: &str, working: bool, hidden: bool,
    requester: crate::tui::FrameRequester,
) -> Option<crate::pets::AmbientPetDraw> {
    let lock = bridge()?;
    let mut b = lock.lock().ok()?;
    requester.schedule_frame_in(Duration::from_millis(33));
    while let Ok(reply) = b.rx.try_recv() {
        b.latest = reply.map(|value| Reply {value, received: Instant::now()});
    }
    let composer = b.composer?;
    if hidden || b.popup || composer.y < 3 || screen.width < 60 { return None; }
    // Read real terminal pixel dimensions, preserving natural sprite proportions.
    let window = crossterm::terminal::window_size().ok();
    let (cell_w, cell_h) = match window {
        Some(w) if w.columns > 0 && w.rows > 0 && w.width > 0 && w.height > 0 =>
            (f64::from(w.width)/f64::from(w.columns), f64::from(w.height)/f64::from(w.rows)),
        _ => (8.0, 16.0),
    };
    let columns = screen.width.saturating_sub(4).min(130);
    let rows = ((160.0 / cell_h).round() as u16).clamp(3, 9).min(composer.y);
    let x = screen.right().saturating_sub(columns + 2);
    let y = composer.y.saturating_sub(rows);
    let width_px = (f64::from(columns) * cell_w).round().clamp(80.0, 2560.0) as u16;
    let height_px = (f64::from(rows) * cell_h).round().clamp(48.0, 480.0) as u16;
    let key = format!("{x}:{y}:{columns}:{rows}:{width_px}:{height_px}");
    let typing = b.last_input.is_some_and(|t| t.elapsed() < Duration::from_millis(900));
    let _ = b.tx.try_send(json!({"v":1,"op":"layout","layout_key":key,
        "visible":true,"width_px":width_px,"height_px":height_px,
        "model":model,"phase":if working {"working"} else {"idle"},"typing":typing,
        "effort":b.effort,"effort_baseline":b.effort_baseline}));
    let latest = b.latest.as_ref()?;
    if latest.received.elapsed() > Duration::from_millis(800)
        || latest.value.get("layout_key")?.as_str()? != key
        || latest.value.get("visible")?.as_bool()? == false { return None; }
    #[cfg(not(test))]
    let protocol = crate::pets::detect_pet_image_support().protocol()?;
    #[cfg(test)]
    let protocol = crate::pets::ImageProtocol::Kitty;
    let frame = PathBuf::from(latest.value.get("frame")?.as_str()?);
    let parent = PathBuf::from(std::env::var_os("CODEX_THEATER_SOCKET")?).parent()?.to_path_buf();
    if frame.parent()? != parent || !frame.is_file() { return None; }
    Some(crate::pets::AmbientPetDraw { frame, protocol, x, y, clear_top_y: y,
        columns, rows, height_px, sixel_dir: parent.join("sixel") })
}
