import json, re, os, csv, random
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load training data
pos, neg = [], []
with open(os.path.join(REPO, "data/us/health_bills_final_matched.csv")) as f:
    for row in csv.DictReader(f):
        t = row.get("dtl_desc") or row.get("vote_desc", "")
        if t:
            pos.append(t)

with open(os.path.join(REPO, "data/canada/ontario/ontario_bill_index.json")) as f:
    on = json.load(f)

random.seed(42)
non_h = [v["title"] for v in on.values() if not v.get("health_tag") and v.get("title")]
on_h  = [v["title"] for v in on.values() if v.get("health_tag") and v.get("title")]
pos.extend(on_h)
neg = random.sample(non_h, min(len(pos), len(non_h)))
print(f"Training: {len(pos)} health, {len(neg)} non-health")

device = "mps" if torch.backends.mps.is_available() else "cpu"
print(f"Device: {device}")
tokenizer = AutoTokenizer.from_pretrained("xlm-roberta-base")
model = AutoModel.from_pretrained("xlm-roberta-base").to(device)
model.eval()

def embed(texts, bs=32):
    out = []
    for i in range(0, len(texts), bs):
        batch = texts[i:i+bs]
        enc = tokenizer(batch, padding=True, truncation=True,
                        max_length=128, return_tensors="pt").to(device)
        with torch.no_grad():
            emb = model(**enc).last_hidden_state[:, 0, :].cpu().numpy()
        out.append(emb)
        if i % 200 == 0:
            print(f"  embedded {i+len(batch)}/{len(texts)}")
    return np.vstack(out)

print("Embedding training data...")
X = embed(pos + neg)
y = [1]*len(pos) + [0]*len(neg)
clf = Pipeline([
    ("s", StandardScaler()),
    ("lr", LogisticRegression(max_iter=1000, solver="lbfgs", C=1.0))
])
clf.fit(X, y)
print("Classifier trained")

with open(os.path.join(REPO, "data/canada/quebec_bills/quebec_health_bills_combined.json")) as f:
    qc = json.load(f)

qc_titles = [b.get("title", "") for b in qc]
print(f"Embedding {len(qc_titles)} Quebec bills...")
Xqc = embed(qc_titles)
preds = clf.predict(Xqc).tolist()
probs = clf.predict_proba(Xqc)[:, 1].tolist()

results = {}
for b, pred, prob in zip(qc, preds, probs):
    s = b.get("session", "")
    m = re.search(r"n[°o\xa0]\s*(\d+)", b.get("title", ""))
    num = m.group(1) if m else ""
    if s and num:
        results[f"{s}-{num}"] = {"pred": int(pred), "prob": round(prob, 3)}

out_path = os.path.join(REPO, "data/dbpedia_pipeline/xlmr_predictions.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"Saved {len(results)} predictions to {out_path}")
