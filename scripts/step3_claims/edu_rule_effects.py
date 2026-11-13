# edu_rule_effects.py RULES PARSES.json EDU_TREES.json OUT.json   What each repair rule changes.
# For every sentence: the claims with all rules on, the claims with each rule switched off one at a time (kept only
# when they differ), and the claims at each stage of the rules (no rules, rounds 1 to 5, round 6, 6b, 7).
import sys,json,copy,time
V6=sys.argv[1]; sys.path.insert(0,V6)
import edu_pipeline as E
R=json.load(open(sys.argv[2]))['rows']; ET=json.load(open(sys.argv[3])); out=sys.argv[4]
base=dict(E.OPT); base['units_only']=True
def run(row,opt):
    E.OPT.update(opt); return E.process(copy.deepcopy(row),[[t for t in u] for u in ET[row['n']]])
f=lambda o:[(l['unit'],l['subject'],l['verb'],l['object']) for l in o['lines']]
flags=[k for k in base if k not in ('units_only','r6_purpose_np')]
r6=[k for k in base if k.startswith('r6_') and k!='r6_purpose_np' and not k.startswith('r6b')]; r6b=[k for k in base if k.startswith('r6b')]; r7=[k for k in base if k.startswith('r7')]
orig=[k for k in flags if k not in r6+r6b+r7+['reanchor']]
stages=[[],orig,orig+r6,orig+r6+r6b,orig+r6+r6b+r7]
res={'flags':flags,'loo':{},'stage':{}}
t=time.time()
for row in R:
    n=row['n']; full=f(run(row,base))
    d={}
    for k in flags:
        o=f(run(row,dict(base,**{k:False})))
        if o!=full: d[k]=o
    res['loo'][n]={'full':full,'off':d}
    st=[]
    for on in stages:
        opt={k:False for k in flags}; opt.update({k:base[k] for k in on}); opt['reanchor']=True; opt['units_only']=True
        st.append(f(run(row,opt)))
    res['stage'][n]=st
    E.OPT.update(base)
json.dump(res,open(out,'w'),ensure_ascii=False); print(time.time()-t)
