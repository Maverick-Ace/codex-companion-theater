//! JSON-v1 display bridge. No character logic or terminal output lives here.
//! The existing ambient image slot owns drawing, cursor restore, and exit cleanup.
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::sync::{mpsc, Mutex, OnceLock};
use std::time::{Duration, Instant};
use ratatui::layout::Rect;
use serde_json::{json, Value};

// Pure input bookkeeping, also compiled independently by the adapter tests.
mod pointer_state {
    use std::collections::VecDeque;

    #[derive(Clone, Debug, PartialEq)]
    pub(super) struct PointerEvent {
        pub kind: &'static str,
        pub x: f64,
        pub y: f64,
        pub button: u8,
    }

    #[derive(Default)]
    pub(super) struct PointerInput {
        pub events: VecDeque<PointerEvent>,
        geometry: Option<(u16, u16, u16, u16)>,
    }

    impl PointerInput {
        pub fn geometry(&mut self, value: (u16, u16, u16, u16)) {
            if self.geometry != Some(value) {
                self.leave();
                self.geometry = Some(value);
            }
        }

        pub fn coordinates(&self, column: u16, row: u16) -> Option<(f64, f64)> {
            let (x, y, width, height) = self.geometry?;
            if width == 0 || height == 0 { return None; }
            Some(((f64::from(column) + 0.5 - f64::from(x)) / f64::from(width),
                  (f64::from(row) + 0.5 - f64::from(y)) / f64::from(height)))
        }

        pub fn leave(&mut self) {
            self.geometry = None;
            self.events.clear();
            self.events.push_back(PointerEvent { kind: "leave", x: 0.0, y: 0.0, button: 0 });
        }

        pub fn push(&mut self, event: PointerEvent) {
            // Preserve crossings and direction changes for the shake recognizer.
            // Under backpressure, discard old motion before any click boundaries.
            if self.events.len() >= 64 {
                if let Some(index) = self.events.iter().position(|item| item.kind == "move") {
                    self.events.remove(index);
                } else {
                    // An excessive click burst must never leave a stuck button/attachment.
                    self.events.clear();
                    self.events.push_back(PointerEvent { kind: "leave", x: 0.0, y: 0.0, button: 0 });
                }
            }
            self.events.push_back(event);
        }

        pub fn sent(&mut self, delivered: bool) {
            if delivered { self.events.clear(); }
        }
    }
}
// End pointer_state.
use pointer_state::{PointerEvent, PointerInput};

struct Reply { value: Value, received: Instant }
struct Bridge {
    composer: Option<Rect>,
    cursor: Option<(u16, u16)>,
    pointer: PointerInput,
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
        Some(Mutex::new(Bridge { composer: None, cursor: None, pointer: PointerInput::default(), popup: false, last_input: None, effort: None, effort_baseline: true, tx, rx, latest: None }))
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
        if let Ok(mut b) = lock.lock() { b.composer = None; b.cursor = None; b.popup = false; }
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

/// Read the same rendered caret that upstream uses, never the editor's text.
pub(crate) fn record_cursor(x: u16, y: u16) {
    if let Some(lock) = bridge() {
        if let Ok(mut b) = lock.lock() { b.cursor = Some((x, y)); }
    }
}

pub(crate) fn note_key(key: &crossterm::event::KeyEvent) {
    use crossterm::event::{KeyCode, KeyEventKind, KeyModifiers};
    if key.kind != KeyEventKind::Release
        && !key.modifiers.intersects(KeyModifiers::CONTROL | KeyModifiers::ALT | KeyModifiers::SUPER)
        && matches!(key.code, KeyCode::Char(_) | KeyCode::Backspace | KeyCode::Delete | KeyCode::Enter | KeyCode::Tab)
    {
        note_input();
    }
}

/// Observe only; upstream still receives every mouse event for selection, links and scrolling.
pub(crate) fn note_mouse(mouse: &crossterm::event::MouseEvent) {
    use crossterm::event::{KeyModifiers, MouseButton, MouseEventKind};
    let Some(lock) = bridge() else { return; };
    let Ok(mut b) = lock.lock() else { return; };
    if mouse.modifiers.contains(KeyModifiers::SHIFT) {
        b.pointer.leave();
        return;
    }
    let (kind, button) = match mouse.kind {
        MouseEventKind::Moved | MouseEventKind::Drag(_) => ("move", 0),
        MouseEventKind::Down(button) => ("down", match button { MouseButton::Left => 0, MouseButton::Middle => 1, MouseButton::Right => 2 }),
        MouseEventKind::Up(button) => ("up", match button { MouseButton::Left => 0, MouseButton::Middle => 1, MouseButton::Right => 2 }),
        _ => return,
    };
    if let Some((x, y)) = b.pointer.coordinates(mouse.column, mouse.row) {
        let event = if !(-0.5..=1.5).contains(&x) || !(-1.0..=2.0).contains(&y) {
            PointerEvent { kind: "leave", x: 0.0, y: 0.0, button: 0 }
        } else {
            PointerEvent { kind, x, y, button }
        };
        b.pointer.push(event);
    }
}

fn send_hidden(b: &mut Bridge) -> bool {
    b.pointer.leave();
    b.latest = None;
    let delivered = b.tx.try_send(json!({"v":1,"op":"layout","layout_key":"hidden","visible":false,
                           "pointer_events":[{"kind":"leave","x":0.0,"y":0.0,"button":0}]})).is_ok();
    b.pointer.sent(delivered);
    delivered
}

/// Release character attachments across modal/overview/focus/editor ownership changes.
pub(crate) fn hide(requester: crate::tui::FrameRequester) {
    if let Some(lock) = bridge() {
        if let Ok(mut b) = lock.lock() {
            if !send_hidden(&mut b) { requester.schedule_frame_in(Duration::from_millis(33)); }
        }
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
    let Some(composer) = b.composer else { send_hidden(&mut b); return None; };
    if hidden || b.popup || composer.y < 3 || screen.width < 60 {
        send_hidden(&mut b);
        return None;
    }
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
    b.pointer.geometry((x, y, columns, rows));
    let cursor = b.cursor.and_then(|(column,row)| b.pointer.coordinates(column,row))
        .map(|(x,y)| json!({"x":x,"y":y}));
    let pointer_events: Vec<Value> = b.pointer.events.iter()
        .map(|event| json!({"kind":event.kind,"x":event.x,"y":event.y,"button":event.button})).collect();
    let typing = b.last_input.is_some_and(|t| t.elapsed() < Duration::from_millis(900));
    let delivered = b.tx.try_send(json!({"v":1,"op":"layout","layout_key":key,
        "visible":true,"width_px":width_px,"height_px":height_px,
        "model":model,"phase":if working {"working"} else {"idle"},"typing":typing,
        "cursor":cursor,"pointer_events":pointer_events,
        "effort":b.effort,"effort_baseline":b.effort_baseline})).is_ok();
    // A full IPC mailbox retries the same click/motion sequence next frame.
    b.pointer.sent(delivered);
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
