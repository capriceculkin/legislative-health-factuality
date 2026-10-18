#!/usr/bin/env python3
"""fr_setup.py   Checks, one by one, what the Berkeley parser needs, installs only what is missing, and says exactly
what went wrong if something cannot be installed. Exit 0 means the parser imports and part 1 can run."""
import importlib, os, subprocess, sys, sysconfig
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
NEEDS = [("torch", "torch"), ("transformers", "transformers"), ("tokenizers", "tokenizers"), ("sentencepiece", "sentencepiece"),
         ("google.protobuf", "protobuf"), ("nltk", "nltk"), ("torch_struct", "torch-struct"), ("benepar", "benepar")]
LOG = Path(os.environ.get("OCT15_OUT", str(Path.home() / "Desktop" / "next_steps" / "oct15"))) / "pip_log.txt"

in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
managed = (Path(sysconfig.get_paths()["stdlib"]) / "EXTERNALLY-MANAGED").exists()
print(f"   python: {sys.executable} (version {sys.version.split()[0]}; {'inside a venv' if in_venv else 'not a venv'})")


def probe():
    missing = []
    for mod, pipname in NEEDS:
        try:
            if mod in ("torch_struct", "benepar"):
                import benepar_fix
                benepar_fix.shim_torch_six()
            m = importlib.import_module(mod)
            print(f"   ok       {mod} {getattr(m, '__version__', '')}")
        except Exception as e:
            print(f"   missing  {mod}  ({type(e).__name__}: {str(e)[:160]})")
            missing.append(pipname)
    return missing


missing = probe()
if missing:
    if managed and not in_venv:
        sys.exit("   This python is managed by Homebrew or the system, so pip will refuse to install into it. Activate the venv\n"
                 "   the earlier runs used (source <venv>/bin/activate), then run the bundle again. Missing: " + " ".join(missing))
    if "torch" in missing:
        print("   torch is missing, so pip will download it too (several hundred MB)")
    print("   installing:", " ".join(missing), f"(full pip output goes to {LOG})", flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, "-m", "pip", "install", *missing], capture_output=True, text=True)
    LOG.write_text(r.stdout + "\n" + r.stderr, encoding="utf-8")
    if r.returncode != 0:
        tail = [l for l in (r.stdout + r.stderr).splitlines() if l.strip()][-15:]
        print("   pip stopped. Its last lines:\n      " + "\n      ".join(tail))
        if "torch-struct" in missing:
            print("   trying torch-struct and benepar without their pinned extras")
            r2 = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "torch-struct", "benepar"],
                                capture_output=True, text=True)
            with LOG.open("a", encoding="utf-8") as f:
                f.write("\n--- no-deps retry\n" + r2.stdout + "\n" + r2.stderr)
    importlib.invalidate_caches()
    print("   checking again:")
    missing = probe()
if missing:
    sys.exit("   Still missing: " + " ".join(missing) + f". Part 1 is skipped. Attach {LOG} to the chat.")
import benepar_fix
benepar_fix.prepare()
print("   the Berkeley parser imports and is patched for current torch and transformers", "; ".join(benepar_fix.NOTES))
