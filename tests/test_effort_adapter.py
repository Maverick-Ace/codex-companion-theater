"""The source adapter validates effort hooks before applying any upstream edits."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('effort_migrate', ROOT/'scripts/migrate.py')
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)


class EffortAdapterTests(unittest.TestCase):
    def source(self, root):
        tui = root/'codex-rs/tui/src'
        (tui/'bottom_pane').mkdir(parents=True)
        (tui/'chatwidget').mkdir()
        (tui/'chatwidget/protocol.rs').write_text('        let from_replay = replay_kind.is_some();\n')
        (tui/'chatwidget/input_submission.rs').write_text('        if !self.submit_op(op.clone()) {\n            return (false, None);\n        }\n')
        (tui/'lib.rs').write_text('mod pets;\n')
        (tui/'app.rs').write_text('''        match &event {
            TuiEvent::FocusLost => {
        tui.link_hover.observe(&event);
    fn render_chat_widget_frame(&mut self, tui: &mut tui::Tui, screen_size: Size) -> Result<Rect> {
                    if self.chat_widget.ambient_pet_image_enabled() {
''')
        (tui/'bottom_pane/chat_composer.rs').write_text('''        let is_baseline = !self.effort_observed;
        self.effort_tier = EffortTier::from_effort(effort);
        self.effort_observed = true;
        self.render_status_surface(status, buf, options);
        self.render_voice_strip(composer_rect, buf);
            // Overlay rows must erase both glyphs and styles from the transcript underneath.
''')
        return tui

    def test_adapter_captures_normal_and_baseline_setters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tui = self.source(root)
            before = {p:p.read_text() for p in tui.rglob('*.rs')}
            output = migrate.prepare(root)
            self.assertEqual(len(output), 5)
            composer = output[tui/'bottom_pane/chat_composer.rs']
            self.assertEqual(composer.count('companion_bridge::note_effort('), 2)
            self.assertIn('unwrap_or_default(), is_baseline,', composer)
            self.assertIn('unwrap_or_default(), true,', composer)
            self.assertEqual(before, {p:p.read_text() for p in tui.rglob('*.rs')})

    def test_missing_effort_anchor_rejects_every_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tui = self.source(root)
            composer = tui/'bottom_pane/chat_composer.rs'
            composer.write_text(composer.read_text().replace('let is_baseline', 'let changed_baseline'))
            before = {p:p.read_text() for p in tui.rglob('*.rs')}
            with self.assertRaisesRegex(ValueError, 'anchor count 0'):
                migrate.prepare(root)
            self.assertEqual(before, {p:p.read_text() for p in tui.rglob('*.rs')})
            self.assertFalse((tui/'companion_bridge.rs').exists())
