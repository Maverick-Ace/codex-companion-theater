"""Interruptible, low-key crossfades for miniature stage sets."""
from PIL import Image
from .stagecraft import environment


class SetTransition:
    duration = .6

    def __init__(self):
        self.target = 'none'
        self.start = -self.duration
        self.source = {}

    def weights(self, now):
        progress=max(0,min(1,(now-self.start)/self.duration))
        eased=progress*progress*(3-2*progress)
        values={name:weight*(1-eased) for name,weight in self.source.items()}
        if self.target != 'none':
            values[self.target]=values.get(self.target,0)+eased
        return {name:weight for name,weight in values.items() if weight>1e-6}

    def change(self, name, now):
        if name == self.target:
            return
        self.source=self.weights(now)
        self.target=name
        self.start=now

    def snapshot(self, now, still=False):
        weights=({self.target:1.0} if self.target!='none' else {}) if still else self.weights(now)
        return {'layers':[{'name':name,'opacity':weight} for name,weight in weights.items()],
                'age':max(0,min(self.duration,now-self.start)),'duration':self.duration}


def draw_set(canvas, state, floor, size):
    """Crossfade only scenery; characters retain their own animation timeline."""
    still=state['quiet'] or state['reduced_motion']
    transition=state.get('stage_transition')
    layers=transition['layers'] if transition else [{'name':state.get('environment','none'),'opacity':1}]
    for spec in layers:
        if spec['name']=='none' or spec['opacity']<=0:
            continue
        layer=Image.new('RGBA',canvas.size)
        # Outgoing props settle; only the destination set reacts to its actors.
        context=state if spec['name']==state.get('environment') else None
        environment(layer,spec['name'],floor,size,state['time'],still=still,state=context)
        if spec['opacity']<1:
            alpha=round(spec['opacity']*255)
            layer.putalpha(layer.getchannel('A').point([i*alpha//255 for i in range(256)]))
        canvas.alpha_composite(layer)
