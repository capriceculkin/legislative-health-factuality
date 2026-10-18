"""benepar_fix.py   Loads the Berkeley parser (benepar 0.2) so it works with current torch and transformers.
Three known breakages are handled here:
  1. torch 2 removed torch._six, which older helper packages still import.
  2. transformers 4.31 and later no longer keep 'embeddings.position_ids' in XLM-R's saved weights, so benepar's strict
     weight loading stops with "Unexpected key(s) in state_dict". The extra key is dropped (or copied in when missing);
     every other weight still has to match exactly.
  3. torch 2.6 and later load files in weights-only mode by default; the parser file is retried in the old mode only if
     that is the reason it failed.
  4. transformers 5 removed tokenizer.build_inputs_with_special_tokens, which benepar uses once to find where the start
     and end tokens sit. It is rebuilt from what the tokenizer itself does to a one-word input, with and without them.
get_parser() also falls back to downloading the French model straight from the parser's GitHub releases page when the
parser's own download index does not answer."""
import os, sys, types, zipfile
from pathlib import Path

MODEL = "benepar_fr2"
GITHUB_ZIP = os.environ.get("BENEPAR_FR2_ZIP") or "https://github.com/nikitakit/self-attentive-parser/releases/download/models/benepar_fr2.zip"
NOTES = []


def shim_torch_six():
    import torch
    if not hasattr(torch, "_six"):
        six = types.ModuleType("torch._six"); six.string_classes = (str, bytes); six.inf = float("inf")
        sys.modules["torch._six"] = six; torch._six = six
        NOTES.append("added torch._six (removed in torch 2)")
    return torch


def add_build_inputs(tok):
    cls = type(tok)
    try:
        getattr(tok, "build_inputs_with_special_tokens")
        return tok
    except AttributeError:
        pass

    def build_inputs_with_special_tokens(self, ids0, ids1=None):
        w = list(self("a")["input_ids"]); wo = list(self("a", add_special_tokens=False)["input_ids"])
        for i in range(len(w) - len(wo) + 1):
            if w[i:i + len(wo)] == wo:
                out = w[:i] + list(ids0) + w[i + len(wo):]
                return out if ids1 is None else out + list(ids1) + w[i + len(wo):]
        raise NotImplementedError("could not find the word inside the tokenizer's own output")

    cls.build_inputs_with_special_tokens = build_inputs_with_special_tokens
    NOTES.append(f"rebuilt build_inputs_with_special_tokens for {cls.__name__} (removed in transformers 5)")
    return tok


def prepare():
    torch = shim_torch_six()
    import benepar
    import benepar.parse_chart as pc
    orig_lsd = pc.ChartParser.load_state_dict

    def load_state_dict(self, sd, strict=True):
        own = self.state_dict()
        extra = [k for k in sd if k not in own and k.endswith("position_ids")]
        for k in extra:
            sd.pop(k)
        missing = [k for k in own if k not in sd and k.endswith("position_ids")]
        for k in missing:
            sd[k] = own[k]
        if extra or missing:
            NOTES.append(f"position_ids: dropped {len(extra)} extra, filled {len(missing)} missing (transformers change)")
        return orig_lsd(self, sd, strict=strict)

    pc.ChartParser.load_state_dict = load_state_dict
    orig_load = torch.load

    def load(*a, **k):
        try:
            return orig_load(*a, **k)
        except Exception as e:
            if "weights_only" in str(e) and k.get("weights_only") is not False:
                NOTES.append("loaded the parser file with weights_only=False (torch 2.6 default changed)")
                k["weights_only"] = False
                return orig_load(*a, **k)
            raise

    torch.load = load
    pc.torch.load = load
    import benepar.retokenization as rt
    AT = rt.transformers.AutoTokenizer
    orig_fp = AT.from_pretrained

    def from_pretrained(*a, **k):
        return add_build_inputs(orig_fp(*a, **k))

    AT.from_pretrained = staticmethod(from_pretrained)
    return benepar


def self_test(benepar, parser):
    """One short French sentence must come back as a tree whose leaves are exactly its words."""
    words = ["Le", "projet", "de", "loi", "est", "adopté", "."]
    tree = parser.parse(benepar.InputSentence(words=words))
    leaves = tree.leaves() if hasattr(tree, "leaves") else None
    if leaves is not None and list(leaves) != words:
        raise RuntimeError(f"test sentence came back with the wrong words: {leaves}")
    return tree


def _from_github(say):
    import urllib.request
    base = Path(os.environ.get("NLTK_DATA", str(Path.home() / "nltk_data"))) / "models"
    base.mkdir(parents=True, exist_ok=True)
    z = base / (MODEL + ".zip")
    say(f"   downloading {MODEL} from the parser's GitHub releases page")
    urllib.request.urlretrieve(GITHUB_ZIP, z)
    with zipfile.ZipFile(z) as f:
        f.extractall(base)
    for p in [base / MODEL] + list(base.rglob("benepar_model.bin")):
        d = p if p.is_dir() else p.parent
        if (d / "benepar_model.bin").exists():
            return str(d)
    raise LookupError(f"the GitHub zip unpacked into {base} but has no benepar_model.bin")


def get_parser(benepar, say=print):
    try:
        return benepar.Parser(MODEL)
    except LookupError:
        pass
    say(f"   downloading {MODEL} (once, about 100 MB) from the parser's own index")
    try:
        benepar.download(MODEL, quiet=True, raise_on_error=True)
    except Exception as e:
        say(f"   the parser's own index did not work ({type(e).__name__}: {str(e)[:200]})")
        return benepar.Parser(_from_github(say))
    try:
        return benepar.Parser(MODEL)
    except LookupError:
        say("   the parser's own index said it worked but the model is not where it should be")
        return benepar.Parser(_from_github(say))
