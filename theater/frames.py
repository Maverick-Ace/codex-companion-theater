"""Budgeted drawing and lossless encoding for both CLI and browser consumers."""
from collections import OrderedDict
from dataclasses import dataclass
import io
import zlib

def interval(state):
    if state['reduced_motion']:return 1/8
    if state['quiet'] or state.get('flight') or state.get('spectacle') or state.get('play'):return 1/30
    actors=state['cast'];t=state['time']
    if (state.get('departing') or state.get('pointer',{}).get('position')
            or any(a.get('reaction') or a.get('attention') or a.get('interaction')
                   or abs(a['v'])>.008 or abs(a.get('depth_v',0))>.015 or 0<=t-a['arrival']<1.2 for a in actors)
            or state.get('life',{}).get('treasure')):return 1/30
    station=state.get('station')
    if station:return 1/30 if station['returning'] else 1/24
    if state['phase']=='working':return 1/20
    return 1/10 if state.get('life',{}).get('sleeping') or state['phase'] in ('waiting','blocked') else 1/15

@dataclass
class EncodedFrame:
    png: bytes
    pixels: bytes
    serial: int
    state: dict
    rendered: float
    due: float

class Frames:
    def __init__(self,renderer):
        self.renderer=renderer;self.entries=OrderedDict();self.serial=0

    def get(self,state,width,height,labels,now):
        key=(width,height,labels);old=self.entries.get(key);period=interval(state)
        if old:
            self.entries.move_to_end(key)
            if state==old.state:return old
            if not state['paused'] and now<min(old.due,old.rendered+period):return old
        image=self.renderer.frame(state,width,height,labels=labels);pixels=image.tobytes()
        if old and pixels==old.pixels:
            old.state=state;old.rendered=now;old.due=now+period;return old
        output=io.BytesIO()
        # RLE encodes long transparent runs efficiently and preserves every pixel.
        image.save(output,format='PNG',compress_level=1,compress_type=zlib.Z_RLE)
        self.serial+=1
        due=now+period if old is None else max(now+period*.25,old.due+period)
        packet=EncodedFrame(output.getvalue(),pixels,self.serial,state,now,due)
        self.entries[key]=packet;self.entries.move_to_end(key)
        while len(self.entries)>2:self.entries.popitem(last=False)
        return packet
