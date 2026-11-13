# edu_trace_stages.py RULES PARSES.json EDU_TREES.json N1,N2,... OUT.json   For the sentences named, the full output
# at each stage of the rules (no repair rules, rounds 1 to 5, round 6, 6b, 7), so a claim can be followed step by step.
import sys,json,copy
V6=sys.argv[1]; sys.path.insert(0,V6)
import edu_pipeline as E
R=json.load(open(sys.argv[2]))['rows']; ET=json.load(open(sys.argv[3])); want=sys.argv[4].split(','); out=sys.argv[5]
base=dict(E.OPT)
r6=[k for k in base if k.startswith('r6_') and not k.startswith('r6b')]; r6b=[k for k in base if k.startswith('r6b')]; r7=[k for k in base if k.startswith('r7')]
orig=[k for k in base if k not in r6+r6b+r7+['units_only','reanchor','r6_purpose_np']]
def run(row,on):
    for k in base: E.OPT[k]=False
    E.OPT['units_only']=True; E.OPT['reanchor']=True
    for k in on: E.OPT[k]=base[k]
    return E.process(copy.deepcopy(row),[[t for t in u] for u in ET[row['n']]])
stages=[("Read from each unit's own tree, no repair rules",[]),("Rules from rounds 1 to 5",orig),("Round 6",orig+r6),("Round 6b",orig+r6+r6b),("Round 7 (current)",orig+r6+r6b+r7)]
res={}
for row in R:
    if row['n'] not in want: continue
    res[row['n']]={'row':row,'stages':[{'name':nm,'flags':fl,'out':run(row,fl)} for nm,fl in stages]}
json.dump({'groups':{'orig':orig,'r6':r6,'r6b':r6b,'r7':r7},'res':res},open(out,'w'),ensure_ascii=False)
print(len(res))
