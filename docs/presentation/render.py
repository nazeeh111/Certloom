"""Recorded-certificate figure. Artwork uses Matplotlib; Certloom remains stdlib-only."""
from pathlib import Path
from fractions import Fraction
import json,hashlib,sys,xml.etree.ElementTree as ET
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent;ROOT=P.parents[1];sys.path.insert(0,str(ROOT))
from certloom.engine import decimal_bound
raw=json.loads((ROOT/'examples/fipy-transient400.json').read_text());r=json.loads((P/'results.json').read_text())['cases']['fipy-transient400']['result']
def q(v):return Fraction(int(v['numerator']),int(v['denominator']))
x=[Fraction.from_float(float.fromhex(v)) for v in raw['x']];w=[Fraction.from_float(float.fromhex(v)) for v in raw['weights']];b=[Fraction.from_float(float.fromhex(v)) for v in raw['b']];A=raw['A'];gaps=[];res=[]
for i in range(400):
 row={A['indices'][k]:Fraction.from_float(float.fromhex(A['data'][k])) for k in range(A['indptr'][i],A['indptr'][i+1])};gaps.append(abs(row.get(i,0))*w[i]-sum(abs(v)*w[j] for j,v in row.items() if j!=i));res.append(b[i]-sum(v*x[j] for j,v in row.items()))
tau=max(abs(v)/d for v,d in zip(res,gaps));assert min(gaps)==q(r['minimum_gap']) and tau==q(r['tau'])
lower=[];upper=[]
for i,e in enumerate(r['enclosures']):
 lo=q(e['lower']);hi=q(e['upper']);assert lo==x[i]-w[i]*tau and hi==x[i]+w[i]*tau;lower.append(float(lo));upper.append(float(hi))
assert q(r['decision']['lower'])>q(r['decision']['above'])
plt.rcParams.update({'path.simplify':False,'font.family':'Arial','svg.fonttype':'none','font.size':13,'axes.labelcolor':'#c4c9d3','text.color':'#f1f0ec','xtick.color':'#c4c9d3','ytick.color':'#c4c9d3','axes.edgecolor':'#646e7d','svg.hashsalt':'certloom-stored-system'})
ink='#f1f0ec';muted='#c4c9d3';gold='#edbd69';paper='#0c0d10'
for mobile in [False,True]:
 name='proof-mobile' if mobile else 'proof';W,H=(480,1280) if mobile else (1280,800);fig=plt.figure(figsize=(W/96,H/96),dpi=96,facecolor=paper)
 def text(xp,yp,s,size=14,color=ink,weight='normal'):fig.text(xp/W,1-yp/H,s,fontsize=size,color=color,fontweight=weight,va='top')
 text(32,28,'CERTLOOM / STORED EQUATIONS, PORTABLE EVIDENCE',10 if mobile else 13,muted,'bold')
 text(32,74,'400 equations.' if mobile else '400 equations. A claim you can carry.',28 if mobile else 36,weight='bold')
 if mobile:text(32,118,'A claim you can carry.',27,weight='bold')
 text(32,172 if mobile else 138,'Captured FiPy final transient · verified without its solver',12 if mobile else 18,muted)
 if mobile:ax=fig.add_axes([.14,.53,.79,.27])
 else:ax=fig.add_axes([.075,.37,.55,.35])
 ax.set_facecolor(paper);ax.spines[['top','right']].set_visible(False);ids=list(range(400));ax.fill_between(ids,lower,upper,color=gold,alpha=.5);ax.plot(ids,[float(v) for v in x],color='#abc2ff',lw=1.15);ax.scatter([19],[float(x[19])],s=32,facecolor=gold,edgecolor=paper,zorder=5);ax.set(xlim=(0,399),ylim=(0,1.05),xlabel='Stored component index',ylabel='Candidate x');ax.set_xticks([0,100,200,300,399]);ax.set_yticks([0,.5,1]);ax.tick_params(labelsize=10 if mobile else 12);ax.grid(axis='y',color='#363d49',linewidth=.6);ax.set_axisbelow(True)
 text(32 if mobile else 96,650 if mobile else 568,'All 400 candidate components; no smoothing or exclusions.',12 if mobile else 15,muted)
 text(32 if mobile else 96,676 if mobile else 591,'Bounds are subpixel here. Exact fractions are authoritative.',10 if mobile else 14,muted)
 sx,sy=(32,745) if mobile else (864,238)
 text(sx,sy,'The selected claim',21,gold,'bold');text(sx,sy+42,'Component 19 > stored 0.98',15 if mobile else 17,weight='bold');text(sx,sy+79,'Guaranteed lower bound',12 if mobile else 14,muted);text(sx,sy+105,decimal_bound(r['decision']['lower'],18,'lower'),16 if mobile else 18,weight='bold');text(sx,sy+145,'Guaranteed upper bound',12 if mobile else 14,muted);text(sx,sy+171,decimal_bound(r['decision']['upper'],18,'upper'),16 if mobile else 18,weight='bold');text(sx,sy+212,'Both endpoints round outward.',12 if mobile else 13,muted)
 fy=1034 if mobile else 634
 text(32,fy,'A different answer can be certified' if mobile else 'A valid enclosure and a useful threshold are different outcomes.',17 if mobile else 25,weight='bold')
 if mobile:text(32,fy+31,'while its threshold stays undecidable.',17,weight='bold')
 text(32,fy+75 if mobile else fy+49,'Steady controls: changed answer → undecidable.' if mobile else 'Steady controls: altered answer → certified, threshold undecidable. Unit weights → proof premise fails.',11 if mobile else 16,muted)
 if mobile:text(32,fy+101,'Unit weights → proof premise fails.',12,muted)
 text(32,H-58,'Stored binary64 equations only; not physical accuracy.',11 if mobile else 16,gold)
 text(32,H-30,'FiPy / NIST source and terms retained · exact JSON and checker included',9 if mobile else 13,muted)
 fig.savefig(P/(name+'.svg'),format='svg',facecolor=paper,metadata={'Date':None});plt.close(fig)
 ET.register_namespace('', 'http://www.w3.org/2000/svg');ET.register_namespace('xlink','http://www.w3.org/1999/xlink');t=ET.parse(P/(name+'.svg'));e=t.getroot();e.set('width',str(W));e.set('height',str(H));e.set('role','img');e.set('aria-labelledby',name+'-title '+name+'-desc');title=ET.Element('{http://www.w3.org/2000/svg}title',{'id':name+'-title'});title.text='Certloom: stored equations and a portable claim';desc=ET.Element('{http://www.w3.org/2000/svg}desc',{'id':name+'-desc'});desc.text='All400 candidate components of a captured FiPy result with subpixel certified bounds and a separate strict threshold decision for component19.';e.insert(0,title);e.insert(1,desc);t.write(P/(name+'.svg'),encoding='unicode');svg=(P/(name+'.svg')).read_text();(P/(name+'.html')).write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Certloom proof handoff</title><style>body{margin:0}.diagram-container{overflow-x:auto}svg{display:block;min-width:'+str(W)+'px}</style><div class="diagram-container">'+svg+'</div></html>')

(P/'figure-data.json').write_text(json.dumps({'source':'../../examples/fipy-transient400.json','all_components':400,'nonzeros':len(A['data']),'minimum_gap_exact':r['minimum_gap'],'tau_exact':r['tau'],'independent_all_400_enclosures_exact':True,'transform':'Stored index on horizontal axis, dimensionless stored value on vertical axis; common0..399and0..1.05limits. No physical distance, filtering, smoothing, downsampling or expanded error bands. Gold dot marks component19,not interval width. Binary64 plotting coordinates only; exact rational endpoints remain authoritative.','lower':lower,'upper':upper,'x':[float(v) for v in x]},indent=2)+'\n')
files=['render.py','results.json','figure-data.json','proof.svg','proof-mobile.svg','proof.html','proof-mobile.html'];(P/'figure-manifest.json').write_text(json.dumps({'source_revision':'0c7728c9af019b60209a9f7c557a97fbd5b197f7','matplotlib_version':matplotlib.__version__,'input_certificates':{str(v.relative_to(ROOT)):{'bytes':v.stat().st_size,'sha256':hashlib.sha256(v.read_bytes()).hexdigest()} for v in [ROOT/'examples'/n for n in ['fipy-transient400.json','fipy-steady400.json','fipy-uniform-refusal.json','fipy-altered-answer.json']]},'files':{n:{'bytes':(P/n).stat().st_size,'sha256':hashlib.sha256((P/n).read_bytes()).hexdigest()} for n in files}},indent=2)+'\n')
