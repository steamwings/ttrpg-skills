import json, math, numpy as np
def arc(c, r, p0, p1, through, step=25):
    a0=math.atan2(p0[1]-c[1],p0[0]-c[0]); a1=math.atan2(p1[1]-c[1],p1[0]-c[0]); at=math.atan2(through[1]-c[1],through[0]-c[0])
    def norm(x): return x%(2*math.pi)
    d=norm(a1-a0); dt=norm(at-a0)
    if dt>d: d=d-2*math.pi
    n=max(2,int(abs(d)*r/step))
    return [(c[0]+r*math.cos(a0+d*i/n), c[1]+r*math.sin(a0+d*i/n)) for i in range(n+1)]
def tower_x(c,r,x,side):  # intersections with vertical line x; side: +1 bulge east, -1 west
    dy=math.sqrt(r*r-(x-c[0])**2); return (x,c[1]-dy),(x,c[1]+dy),(c[0]+side*r,c[1])
def tower_y(c,r,y):       # bulge south
    dx=math.sqrt(r*r-(y-c[1])**2); return (c[0]+dx,y),(c[0]-dx,y),(c[0],c[1]+r)
def build(seq):
    pts=[]
    for item in seq:
        if item[0]=='p': pts.append(item[1])
        else: pts+=item[1]
    segs=[]
    for a,b in zip(pts,pts[1:]):
        if math.hypot(b[0]-a[0],b[1]-a[1])>2: segs.append([round(a[0]),round(a[1]),round(b[0]),round(b[1]),1])
    return segs
P={}
# L1
ap=arc((1952,380),240,(1712,380),(2192,380),(1952,140))
b1,b2,bt=tower_x((3088,2500),312,3224,1)
se1,se2,st=tower_y((2656,3132),176,3212)
sw1,sw2,swt=tower_y((1248,3132),176,3212)
w_top,w_bot,wt=tower_x((800,2500),320,688,-1)
P['L1']=build([('p',(680,380)),('p',(1344,380)),('p',(1344,348)),('p',(1456,348)),('p',(1456,380)),('a',ap),
 ('p',(3224,380)),('p',(3224,1292)),('p',(3408,1292)),('p',(3408,1900)),('p',(3224,1900)),('p',b1),('a',arc((3088,2500),312,b1,b2,bt)),
 ('p',(3224,3212)),('p',se1),('a',arc((2656,3132),176,se1,se2,st)),('p',sw1),('a',arc((1248,3132),176,sw1,sw2,swt)),
 ('p',(688,3212)),('p',w_bot),('a',arc((800,2500),320,w_bot,w_top,wt)),('p',(688,1100)),('p',(488,1004)),('p',(488,580)),('p',(680,380))])
# L2
ap=arc((1952,372),240,(1712,372),(2192,372),(1952,132))
se1,se2,st=tower_y((2656,3140),152,3228); sw1,sw2,swt=tower_y((1248,3140),152,3228)
w_top,w_bot,wt=tower_x((800,2500),304,680,-1)
main=build([('p',(3224,2892)),('p',(3224,3228)),('p',se1),('a',arc((2656,3140),152,se1,se2,st)),('p',sw1),('a',arc((1248,3140),152,sw1,sw2,swt)),
 ('p',(680,3228)),('p',w_bot),('a',arc((800,2500),304,w_bot,w_top,wt)),('p',(680,1084)),('p',(480,996)),('p',(480,596)),('p',(680,492)),('p',(680,372)),
 ('p',(1328,372)),('p',(1328,332)),('p',(1456,332)),('p',(1456,372)),('p',(1712,372)),('p',(1712,330)),('p',(2192,330)),('p',(2192,372)),('p',(3224,372)),('p',(3224,2108))])
P['L2']=main+[[3224,2108,3224,2892,4]]
W=json.load(open('walls-palace3.json'))
for k in ('L1','L2'):
    ops=[((s[0]+s[2])/2,(s[1]+s[3])/2,max(abs(s[2]-s[0]),abs(s[3]-s[1]))/2) for s in W[k] if s[4] in (2,3)]
    add=[]
    for s in P[k]:
        A=np.array(s[:2],float); B=np.array(s[2:4],float); L=np.linalg.norm(B-A); n=max(1,int(L//25))
        cur=None
        for i in range(n):
            u=A+(B-A)*i/n; v=A+(B-A)*(i+1)/n; m=(u+v)/2
            blocked=any(math.hypot(m[0]-ox,m[1]-oy)<hl+12 and (abs(m[0]-ox)<20 or abs(m[1]-oy)<20) for ox,oy,hl in ops)
            if blocked:
                if cur: add.append(cur); cur=None
            else:
                if cur is None: cur=[u,v]
                else: cur[1]=v
        if cur: add.append(cur)
        add_k=[[round(u[0]),round(u[1]),round(v[0]),round(v[1]),s[4]] for u,v in add]; add=[]
        W[k]+=add_k
    print(k,len(W[k]))
json.dump(W,open('walls-palace4.json','w'),separators=(',',':'))
from PIL import Image, ImageDraw
for k,f in [('L1','palace-l1-lower.webp'),('L2','palace-l2-upper.webp')]:
    im=Image.open(f).convert('RGB'); d=ImageDraw.Draw(im)
    for s in W[k]: d.line(s[:4],fill=(255,0,0) if s[4]==1 else (0,80,255) if s[4]==2 else (0,220,220) if s[4]==3 else (255,200,0),width=6)
    for s in P[k]: d.line(s[:4],fill=(0,255,0),width=3)
    im.crop((300,0,3700,3500)).resize((1000,1030)).save(f'per-{k}.png')
