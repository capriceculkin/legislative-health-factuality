
import re

path = 'scripts/dbpedia_batch_pipeline.py'
with open(path) as f:
    c = f.read()

old = '        subj_uris = spotlight_string(pred["subject"], SPOTLIGHT_LANG)\n        obj_uris  = spotlight_string(pred["object"],  SPOTLIGHT_LANG)\n\n        if not subj_uris or not obj_uris:\n            continue\n\n        all_uris = list(dict.fromkeys(subj_uris + obj_uris))'

new = '        full_text = pred.get("full_text", pred["subject"] + " " + pred["object"])\n        all_resources = spotlight_string(full_text, SPOTLIGHT_LANG)\n        if not all_resources or len(all_resources) < 2:\n            continue\n        all_uris = list(dict.fromkeys(all_resources))'

if old in c:
    c = c.replace(old, new)
    with open(path, 'w') as f:
        f.write(c)
    print('done')
else:
    print('not found - old text missing')
