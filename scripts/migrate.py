#!/usr/bin/env python3
"""Conservative source adapter: check all semantic anchors before writing anything.

Targets a clean, isolated source export. Never updates a user's existing binary.
"""
import argparse
from pathlib import Path
import shutil
import json

ROOT=Path(__file__).resolve().parents[1]
def prepare(source):
    tui=source/"codex-rs/tui/src"
    replacements={
      "lib.rs":[("mod pets;","mod pets;\nmod companion_bridge;")],
      "app.rs":[
        ("        tui.link_hover.observe(&event);",
         """        // Observe before upstream selection may consume an event; never reroute input.
        match &event {
            TuiEvent::Mouse(mouse) => crate::companion_bridge::note_mouse(mouse),
            TuiEvent::Key(key) if self.overlay.is_none()
                && self.chat_widget.no_modal_or_popup_active() => crate::companion_bridge::note_key(key),
            TuiEvent::Paste(text) if !text.is_empty() && self.overlay.is_none()
                && self.chat_widget.no_modal_or_popup_active() => crate::companion_bridge::note_input(),
            TuiEvent::FocusLost | TuiEvent::Resize(_) | TuiEvent::Resume =>
                crate::companion_bridge::hide(tui.frame_requester()),
            _ => {}
        }
        if crate::companion_bridge::enabled()
            && (self.overlay.is_some()
                || matches!(&event, TuiEvent::Key(key)
                    if key.modifiers.contains(KeyModifiers::CONTROL) && key.code == KeyCode::Char('z')))
        {
            crate::companion_bridge::hide(tui.frame_requester());
            let _ = tui.clear_ambient_pet_image();
        }
        tui.link_hover.observe(&event);"""),
        ("    fn render_chat_widget_frame(&mut self, tui: &mut tui::Tui, screen_size: Size) -> Result<Rect> {",
         "    fn render_chat_widget_frame(&mut self, tui: &mut tui::Tui, screen_size: Size) -> Result<Rect> {\n        crate::companion_bridge::begin_frame();"),
        ("                    if self.chat_widget.ambient_pet_image_enabled() {",
         "                    if crate::companion_bridge::enabled() {\n                        let request = crate::companion_bridge::frame(\n                            Rect::new(0, 0, screen_size.width, screen_size.height),\n                            self.chat_widget.current_model(),\n                            self.chat_widget.is_agent_turn_running(),\n                            self.chat_widget.has_active_modal()\n                                || self.chat_widget.external_editor_state() != ExternalEditorState::Closed,\n                            tui.frame_requester(),\n                        );\n                        match request {\n                            crate::companion_bridge::Frame::Draw(frame) => { let _ = tui.draw_ambient_pet_image(Some(frame)); }\n                            crate::companion_bridge::Frame::Clear => { let _ = tui.clear_ambient_pet_image(); }\n                            crate::companion_bridge::Frame::Hold => {}\n                        }\n                    } else if self.chat_widget.ambient_pet_image_enabled() {")],
      "chatwidget/protocol.rs":[
        ("        let from_replay = replay_kind.is_some();",
         "        let from_replay = replay_kind.is_some();\n        if !from_replay { crate::companion_bridge::note_activity(&notification); }")],
      "chatwidget/input_submission.rs":[
        ("        if !self.submit_op(op.clone()) {\n            return (false, None);\n        }",
         "        if !self.submit_op(op.clone()) {\n            return (false, None);\n        }\n        if source == UserMessageSource::Prompt {\n            crate::companion_bridge::note_submission(effective_mode.model());\n        }")],
      "bottom_pane/chat_composer.rs":[
        ("        let is_baseline = !self.effort_observed;",
         "        let is_baseline = !self.effort_observed;\n        crate::companion_bridge::note_effort(\n            &effort.map(ToString::to_string).unwrap_or_default(), is_baseline,\n        );"),
        ("        self.effort_tier = EffortTier::from_effort(effort);\n        self.effort_observed = true;",
         "        crate::companion_bridge::note_effort(\n            &effort.map(ToString::to_string).unwrap_or_default(), true,\n        );\n        self.effort_tier = EffortTier::from_effort(effort);\n        self.effort_observed = true;"),
        ("        self.render_status_surface(status, buf, options);",
         "        crate::companion_bridge::record_composer(composer_rect);\n        self.render_status_surface(status, buf, options);"),
        ("        self.render_voice_strip(composer_rect, buf);",
         "        if let Some((x, y)) = self.cursor_pos_with_options(area, options) {\n            crate::companion_bridge::record_cursor(x, y);\n        }\n        self.render_voice_strip(composer_rect, buf);"),
        ("            // Overlay rows must erase both glyphs and styles from the transcript underneath.",
         "            crate::companion_bridge::record_popup();\n            // Overlay rows must erase both glyphs and styles from the transcript underneath.")]
    }
    output={}
    for name,pairs in replacements.items():
        original=(tui/name).read_text()
        if "companion_bridge" in original:raise ValueError(f"adapter already present or partial: {name}")
        modified=original
        for before,after in pairs:
            count=modified.count(before)
            if count!=1:raise ValueError(f"unsupported source: {name}: anchor count {count}; no changes applied")
            modified=modified.replace(before,after,1)
        output[tui/name]=modified
    if (tui/"companion_bridge.rs").exists():raise ValueError("bridge file exists; refusing to overwrite")
    return output

def main():
    p=argparse.ArgumentParser();p.add_argument("source",type=Path);p.add_argument("--apply",action="store_true")
    args=p.parse_args()
    output=prepare(args.source)
    print(json.dumps({"compatible_anchors":True,"existing_files":5,"new_module":1,"applied":args.apply},indent=2))
    if not args.apply:return
    for file,content in output.items():
        backup=file.with_suffix(file.suffix+".theater-original")
        if backup.exists():raise ValueError(f"backup already exists: {backup}")
    for file,content in output.items():
        shutil.copy2(file,file.with_suffix(file.suffix+".theater-original"))
        file.write_text(content)
    shutil.copy2(ROOT/"adapters/codex/companion_bridge.rs",args.source/"codex-rs/tui/src/companion_bridge.rs")

if __name__=="__main__":main()
