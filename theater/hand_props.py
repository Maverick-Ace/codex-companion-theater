"""Held objects travel between prop anchors and the character's hands."""
import math
from PIL import Image, ImageDraw
from .props import prop_layout


def engagement(progress):
    p=max(0,min(1,progress))
    value=max(0,min(1,p/.14,(1-p)/.14))
    return value*value*(3-2*value)


def draw_held(canvas, state, actor, x, floor, size):
    contact=actor.get('interaction')
    if not contact or not contact['active'] or state['quiet'] or state['reduced_motion']:
        return
    anchors=prop_layout(state.get('environment'),canvas.width,floor,size)
    anchor=anchors.get(contact['prop'])
    if anchor is None:return
    p=contact['progress'];grip=engagement(p)
    action=contact['action'];u=max(.65,min(1.8,size/110))
    direction=1 if anchor['x']>=x else -1
    hx=x+direction*size*.16;hy=floor-size*.40
    phase=state['time']*actor.get('tempo',1)*3
    # Local supersampling keeps cups, fingers' tools and book edges legible.
    left=math.floor(min(x-size*.55,anchor['x']-30*u))
    top=math.floor(floor-size*.88)
    right=math.ceil(max(x+size*.55,anchor['x']+30*u))
    bottom=math.ceil(floor+3)
    surface=Image.new('RGBA',((right-left)*2,(bottom-top)*2))
    d=ImageDraw.Draw(surface)
    def pts(values):return tuple((v-(left if i%2==0 else top))*2 for i,v in enumerate(values))
    def line(values,fill,width=1):d.line(pts(values),fill=fill,width=max(1,round(width*u*2)))
    def oval(values,fill,outline=None):d.ellipse(pts(values),fill=fill,outline=outline,width=max(1,round(2*u)))
    def rect(values,fill,outline=None,radius=2):
        box=tuple(round(v) for v in pts(values));r=min(round(radius*u*2),(box[2]-box[0])//2,(box[3]-box[1])//2)
        d.rounded_rectangle(box,radius=max(0,r),fill=fill,outline=outline,width=max(1,round(2*u)))
    if action=='sip':
        # Pick up, lift to the face, lower and return to the table.
        cx=anchor['x']+(hx-anchor['x'])*grip
        cy=anchor['y']+(hy-8*u-anchor['y'])*grip
        cy-=max(0,math.sin(phase*.65))*4*u*grip
        rect((cx-6*u,cy-5*u,cx+6*u,cy+6*u),'#a3bec8','#d7dbe2',3)
        oval((cx-5*u,cy-6*u,cx+5*u,cy-2*u),'#ad8066','#e5e1d8')
        d.arc(pts((cx+3*u,cy-3*u,cx+11*u,cy+4*u)),-80,90,fill='#c1c7d3',width=max(1,round(2*u)))
    elif action=='read':
        cx=anchor['x']+(x-anchor['x'])*grip
        cy=anchor['y']+(floor-size*.34-anchor['y'])*grip
        rect((cx-16*u,cy-10*u,cx+16*u,cy+10*u),'#887898','#c0aeca',2)
        d.polygon(pts((cx-14*u,cy-8*u,cx,cy-6*u,cx,cy+8*u,cx-14*u,cy+6*u)),fill='#ddd3bd')
        d.polygon(pts((cx,cy-6*u,cx+14*u,cy-8*u,cx+14*u,cy+6*u,cx,cy+8*u)),fill='#f0dfc5')
        for n in range(3):
            line((cx-11*u,cy+(-4+n*4)*u,cx-3*u,cy+(-3+n*4)*u),'#b9a299',.65)
        line((cx,cy-6*u,cx,cy+8*u),'#c8aaa3',.7)
    elif action=='water':
        cx=hx;cy=hy
        rect((cx-10*u,cy-4*u,cx+8*u,cy+10*u),'#90b7b6','#c1d8cc',3)
        d.arc(pts((cx-15*u,cy-11*u,cx+2*u,cy+3*u)),180,340,fill='#bed9ce',width=max(1,round(3*u)))
        spout=(cx+direction*21*u,cy-4*u)
        line((cx+direction*6*u,cy+2*u,*spout),'#acd0c7',4)
        if grip>.35:
            target=(anchor['x'],anchor['y']-3*u)
            line((*spout,(spout[0]+target[0])/2,target[1]-6*u,*target),'#b0daeaad',.8)
    elif action=='stir':
        tip=(anchor['x']+math.sin(phase)*6*u,anchor['y']+math.cos(phase)*2*u)
        line((hx,hy,*tip),'#c4a48e',2)
        oval((tip[0]-4*u,tip[1]-2*u,tip[0]+4*u,tip[1]+2*u),'#d1b6a1','#f0dac1')
    elif action=='write':
        tip=(anchor['x']+math.sin(phase*1.5)*6*u,anchor['y']-2*u)
        line((tip[0]-4*u,tip[1]-14*u,*tip),'#d6b87c',2)
        line((*tip,tip[0]+1*u,tip[1]+2*u),'#615b70',1)
    elif action in ('serve','unpack'):
        cx=anchor['x']+(hx-anchor['x'])*grip;cy=anchor['y']+(hy-anchor['y'])*grip
        oval((cx-13*u,cy-3*u,cx+13*u,cy+3*u),'#d6d9e3','#f2e3ec')
        for n in (-1,0,1):
            oval((cx+(n*6-3)*u,cy-7*u,cx+(n*6+3)*u,cy-1*u),'#d6ae81','#f0ce9d')
    elif action=='inspect':
        cx=hx;cy=hy+6*u
        line((cx,cy-14*u,cx,cy-6*u),'#cfbca1',1)
        rect((cx-5*u,cy-7*u,cx+5*u,cy+6*u),'#e9c586','#b69b85',2)
        line((cx-6*u,cy-7*u,cx+6*u,cy-7*u),'#ad9686',2)
    else:
        return
    layer=surface.resize((right-left,bottom-top),Image.Resampling.LANCZOS)
    if action not in ('read','sip'):
        alpha=round(grip*255)
        layer.putalpha(layer.getchannel('A').point([i*alpha//255 for i in range(256)]))
    # Pillow alpha_composite clips negative offsets without modulo addressing.
    canvas.alpha_composite(layer,(left,top))
