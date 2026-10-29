"""Compile the production input queue with Rust 1.94 and check fail-closed hooks."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pointer_migrate', ROOT/'scripts/migrate.py')
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)


class NativePointerAdapterTests(unittest.TestCase):
    def source(self, root):
        tui = root/'codex-rs/tui/src'
        (tui/'bottom_pane').mkdir(parents=True)
        (tui/'lib.rs').write_text('mod pets;\n')
        (tui/'app.rs').write_text('''        tui.link_hover.observe(&event);
        if self.handle_rendered_selection_event(tui, &event)? {
    fn render_chat_widget_frame(&mut self, tui: &mut tui::Tui, screen_size: Size) -> Result<Rect> {
                    if self.chat_widget.ambient_pet_image_enabled() {
''')
        (tui/'bottom_pane/chat_composer.rs').write_text('''        let is_baseline = !self.effort_observed;
        self.effort_tier = EffortTier::from_effort(effort);
        self.effort_observed = true;
        self.render_status_surface(status, buf, options);
            // Overlay rows must erase both glyphs and styles from the transcript underneath.
        drop(state);
        self.render_voice_strip(composer_rect, buf);
''')
        return tui

    def test_mouse_observer_precedes_selection_without_intercepting_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tui = self.source(root)
            output = migrate.prepare(root)
            self.assertEqual(len(output), 3)
            app = output[tui/'app.rs']
            self.assertLess(app.index('companion_bridge::note_mouse(mouse)'),
                            app.index('self.handle_rendered_selection_event'))
            self.assertIn('TuiEvent::FocusLost | TuiEvent::Resize(_) | TuiEvent::Resume', app)
            self.assertIn('companion_bridge::hide(tui.frame_requester())', app)
            self.assertEqual(app.count('tui.link_hover.observe(&event);'), 1)
            self.assertNotIn('return Ok', app)
            composer = output[tui/'bottom_pane/chat_composer.rs']
            self.assertLess(composer.index('drop(state);'), composer.index('record_cursor(x, y)'))
            self.assertIn('self.cursor_pos_with_options(area, options)', composer)
            self.assertNotIn('textarea.text()', composer)

    def test_missing_mouse_or_caret_anchor_rejects_all_edits(self):
        for anchor in ('tui.link_hover.observe(&event);', 'self.render_voice_strip(composer_rect, buf);'):
            with self.subTest(anchor=anchor), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                tui = self.source(root)
                for path in tui.rglob('*.rs'):
                    path.write_text(path.read_text().replace(anchor, 'changed upstream anchor'))
                before = {p:p.read_bytes() for p in tui.rglob('*.rs')}
                with self.assertRaisesRegex(ValueError, 'anchor count 0'):
                    migrate.prepare(root)
                self.assertEqual(before, {p:p.read_bytes() for p in tui.rglob('*.rs')})

    def test_rust_194_queue_coordinates_and_delivery(self):
        source = (ROOT/'adapters/codex/companion_bridge.rs').read_text()
        production = source[source.index('mod pointer_state {'):source.index('// End pointer_state.')]
        checks = r'''
use pointer_state::{PointerInput, PointerEvent};
fn event(kind: &'static str, x: f64) -> PointerEvent {
    PointerEvent { kind, x, y: 0.4, button: 0 }
}
#[test]
fn terminal_cell_centers_and_offstage_coordinates_are_preserved() {
    let mut input = PointerInput::default();
    assert!(input.coordinates(10, 20).is_none());
    input.geometry((10, 20, 100, 10));
    assert_eq!(input.coordinates(10, 20), Some((0.005, 0.05)));
    assert_eq!(input.coordinates(60, 32), Some((0.505, 1.25)));
    assert_eq!(input.coordinates(9, 19), Some((-0.005, -0.05)));
}
#[test]
fn identical_redraw_retains_events_but_resize_resets_old_geometry() {
    let mut input = PointerInput::default();
    input.geometry((0, 10, 100, 8)); input.sent(true);
    input.push(event("down", 0.2));
    input.geometry((0, 10, 100, 8));
    assert_eq!(input.events.front().unwrap().kind, "down");
    input.geometry((0, 10, 120, 8));
    assert_eq!(input.events.len(), 1);
    assert_eq!(input.events.front().unwrap().kind, "leave");
    assert_eq!(input.coordinates(59, 10), Some((59.5/120.0, 0.0625)));
}
#[test]
fn full_mailbox_retries_click_boundaries_until_actual_submission() {
    let mut input = PointerInput::default();
    input.push(event("down", 0.1)); input.push(event("move", 0.3)); input.push(event("up", 0.3));
    let (tx,rx) = std::sync::mpsc::sync_channel(1);
    tx.try_send(0).unwrap();
    input.sent(tx.try_send(1).is_ok());
    assert_eq!(input.events.iter().map(|e|e.kind).collect::<Vec<_>>(), vec!["down","move","up"]);
    assert_eq!(rx.recv().unwrap(), 0);
    input.sent(tx.try_send(1).is_ok());
    assert!(input.events.is_empty());
}
#[test]
fn queue_preserves_shake_reversals_and_prioritizes_clicks_under_motion_flood() {
    let mut input = PointerInput::default();
    input.push(event("down", 0.3));
    for i in 0..100 { input.push(event("move", if i%2 == 0 { 0.2 } else { 0.6 })); }
    input.push(event("up", 0.6));
    assert_eq!(input.events.len(), 64);
    assert_eq!(input.events.front().unwrap().kind, "down");
    assert_eq!(input.events.back().unwrap().kind, "up");
    let motion: Vec<_> = input.events.iter().filter(|e|e.kind == "move").map(|e|e.x).collect();
    assert!(motion.windows(2).all(|pair|pair[0] != pair[1]));
}
#[test]
fn hide_clears_stale_events_and_prevents_invisible_hits() {
    let mut input = PointerInput::default();
    input.geometry((0, 10, 100, 8)); input.push(event("down", 0.3));
    input.leave();
    assert!(input.coordinates(30, 15).is_none());
    assert_eq!(input.events.len(), 1);
    assert_eq!(input.events.front().unwrap().kind, "leave");
}
#[test]
fn_excessive_click_bursts_remain_bounded_and_reset_attachment_state() {
    let mut input = PointerInput::default();
    for _ in 0..65 { input.push(event("down", 0.2)); }
    assert_eq!(input.events.len(), 2);
    assert_eq!(input.events.front().unwrap().kind, "leave");
}
'''.replace('fn_excessive', 'fn excessive')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'pointer.rs'
            binary = Path(temp)/'pointer-tests'
            path.write_text(production + checks)
            result = subprocess.run(['rustc', '+1.94.1', '--edition=2024', '--test', str(path),
                                     '-o', str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('6 passed', result.stdout)
