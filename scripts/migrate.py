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
        ("        match &event {\n            TuiEvent::FocusLost => {",
         "        if matches!(&event, TuiEvent::Key(_) | TuiEvent::Paste(_)) {\n            crate::companion_bridge::note_input();\n        }\n        if crate::companion_bridge::enabled() && self.overlay.is_some() {\n            let _ = tui.clear_ambient_pet_image();\n        }\n\n        match &event {\n            TuiEvent::FocusLost => {"),
        ("    fn render_chat_widget_frame(&mut self, tui: &mut tui::Tui, screen_size: Size) -> Result<Rect> {",
         "    fn render_chat_widget_frame(&mut self, tui: &mut tui::Tui, screen_size: Size) -> Result<Rect> {\n        crate::companion_bridge::begin_frame();"),
        ("                    if self.chat_widget.ambient_pet_image_enabled() {",
         "                    if crate::companion_bridge::enabled() {\n                        let request = crate::companion_bridge::frame(\n                            Rect::new(0, 0, screen_size.width, screen_size.height),\n                            self.chat_widget.current_model(),\n                            self.chat_widget.is_agent_turn_running(),\n                            self.chat_widget.has_active_modal()\n                                || self.chat_widget.external_editor_state() != ExternalEditorState::Closed,\n                            tui.frame_requester(),\n                        );\n                        let _ = tui.draw_ambient_pet_image(request);\n                    } else if self.chat_widget.ambient_pet_image_enabled() {")],
      "bottom_pane/chat_composer.rs":[
        ("        let is_baseline = !self.effort_observed;",
         "        let is_baseline = !self.effort_observed;\n        crate::companion_bridge::note_effort(\n            &effort.map(ToString::to_string).unwrap_or_default(), is_baseline,\n        );"),
        ("        self.effort_tier = EffortTier::from_effort(effort);\n        self.effort_observed = true;",
         "        crate::companion_bridge::note_effort(\n            &effort.map(ToString::to_string).unwrap_or_default(), true,\n        );\n        self.effort_tier = EffortTier::from_effort(effort);\n        self.effort_observed = true;"),
        ("        self.render_status_surface(status, buf, options);",
         "        crate::companion_bridge::record_composer(composer_rect);\n        self.render_status_surface(status, buf, options);"),
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
    print(json.dumps({"compatible_anchors":True,"existing_files":3,"new_module":1,"applied":args.apply},indent=2))
    if not args.apply:return
    for file,content in output.items():
        backup=file.with_suffix(file.suffix+".theater-original")
        if backup.exists():raise ValueError(f"backup already exists: {backup}")
    for file,content in output.items():
        shutil.copy2(file,file.with_suffix(file.suffix+".theater-original"))
        file.write_text(content)
    shutil.copy2(ROOT/"adapters/codex/companion_bridge.rs",args.source/"codex-rs/tui/src/companion_bridge.rs")

if __name__=="__main__":main()
