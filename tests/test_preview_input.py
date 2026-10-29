"""Run the shipped browser transport in Node with deterministic DOM geometry."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT/'web/index.html').read_text()


@unittest.skipUnless(shutil.which('node'), 'Node is required for browser transport regressions')
class PreviewInputTests(unittest.TestCase):
    def run_js(self, declarations, assertions):
        program = declarations + '\n(async()=>{\n' + assertions + '\n})().catch(error=>{console.error(error);process.exitCode=1})'
        result = subprocess.run(['node', '-e', program], text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_pointer_reversals_and_gesture_edges_survive_request_backpressure(self):
        transport = PAGE[PAGE.index('let pointerQueue='):PAGE.index("const frame=$('#frame');")]
        declarations = """
const assert=require('node:assert/strict');
const packets=[];
const command=async data=>{packets.push(data)};
const report=error=>{throw error};
const setTimeout=()=>1,clearTimeout=()=>{};
""" + transport
        self.run_js(declarations, """
pointerBusy=true;
for(const x of [.1,.3,.1,.3,.1])queuePointer({kind:'move',x,y:.2});
assert.deepEqual(pointerQueue.map(event=>event.x),[.1,.3,.1,.3,.1]);
pointerQueue=[];
for(let x=0;x<10;x++)queuePointer({kind:'move',x:x/10,y:.2});
assert.equal(pointerQueue.length,2);
pointerQueue=[];
for(const kind of ['down','up','leave'])queuePointer({kind,x:.4,y:.5});
for(let index=0;index<160;index++)queuePointer({kind:'move',x:index%2?.3:.6,y:.2});
assert.equal(pointerQueue.length,128);
assert.deepEqual(pointerQueue.slice(0,3).map(event=>event.kind),['down','up','leave']);
pointerBusy=false;
await flushPointer();await flushPointer();
assert.equal(packets.length,2);
assert.equal(packets[0].events.length,64);
assert.equal(packets[1].events.length,64);
assert.deepEqual(packets[0].events.slice(0,3).map(event=>event.kind),['down','up','leave']);
assert.deepEqual(packets[1].events.slice(-5).map(event=>event.x),[.3,.6,.3,.6,.3]);
""")

    def test_caret_uses_active_selection_edge_scroll_padding_and_object_fit(self):
        geometry = PAGE[PAGE.index('function imageBounds()'):PAGE.index('function typing()')]
        declarations = """
const assert=require('node:assert/strict');
const input={value:'abcdef',selectionStart:1,selectionEnd:4,selectionDirection:'forward',scrollLeft:0,
  getBoundingClientRect:()=>({left:20,top:230,width:100,height:24})};
const image={naturalWidth:1600,naturalHeight:220,
  getBoundingClientRect:()=>({left:0,top:0,width:800,height:220})};
const $=selector=>selector==='#draft'?input:image;
const getComputedStyle=()=>({font:'15px sans-serif',letterSpacing:'0px',paddingLeft:'2px',paddingRight:'2px',borderLeftWidth:'0px',borderRightWidth:'0px'});
const document={createElement:()=>({getContext:()=>({measureText:text=>({width:text.length*10})})})};
""" + geometry
        self.run_js(declarations, """
assert.deepEqual(imageBounds(),{left:0,top:55,width:800,height:110,width_px:1600,height_px:220});
assert.equal(caretPoint().x,62/800);
assert.equal(caretPoint().y,187/110);
input.selectionDirection='backward';assert.equal(caretPoint().x,32/800);
input.selectionDirection='forward';input.scrollLeft=15;assert.equal(caretPoint().x,47/800);
input.scrollLeft=400;assert.equal(caretPoint().x,22/800);
""")
