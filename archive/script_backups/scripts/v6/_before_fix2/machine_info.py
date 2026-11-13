"""machine_info.py   What machine and software the parses ran on (David asked). Writes outputs/machine.txt. Reads only."""
import platform, subprocess, sys, importlib.metadata as md
from pathlib import Path
def sh(c):
    try:
        return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""
L = []
hw = sh('system_profiler SPHardwareDataType 2>/dev/null | grep -E "Model Name|Chip|Memory" | sed "s/^ *//"').replace("\n", "; ")
L.append("computer      " + sh("sysctl -n hw.model") + "  (" + hw + ")")
L.append(f"processor     {sh('sysctl -n machdep.cpu.brand_string') or platform.processor()}, {sh('sysctl -n hw.ncpu')} cores")
mem = sh("sysctl -n hw.memsize")
L.append(f"memory        {int(mem) / 2**30:.0f} GB" if mem.isdigit() else "memory        ?")
L.append(f"system        macOS {sh('sw_vers -productVersion')} ({platform.machine()})")
L.append(f"python        {sys.version.split()[0]}  ({sys.executable})")
for p in ("spacy", "en_core_web_lg", "fr_core_news_lg", "stanza", "benepar", "torch", "transformers", "isanlp_rst"):
    try:
        L.append(f"{p:13s} {md.version(p)}")
    except Exception:
        L.append(f"{p:13s} not installed in this python")
try:
    import torch
    L.append(f"GPU (Apple MPS) available to torch: {torch.backends.mps.is_available()}; CUDA: {torch.cuda.is_available()}")
except Exception:
    pass
out = Path("outputs/machine.txt"); out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
