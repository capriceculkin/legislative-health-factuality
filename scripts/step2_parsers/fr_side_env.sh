#!/bin/bash
# fr_side_env.sh   Second route for part 1. Builds a small side environment (~/.benepar_side_venv) that sees every package of
# the venv you run from, but with transformers 4.30.2 in front of it: the last version from before the changes that broke
# benepar. Your own venv is not changed. Prints the side python's path on its last line when it worked.
SIDE="$HOME/.benepar_side_venv"
LOG="${OCT15_OUT:-$HOME/Desktop/next_steps/oct15}/pip_side_log.txt"
PARENT_SP=$(python3 -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
if [ ! -x "$SIDE/bin/python" ]; then
  python3 -m venv "$SIDE" || { echo "   could not make the side environment at $SIDE"; exit 1; }
fi
SIDE_SP=$("$SIDE/bin/python" -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")
echo "$PARENT_SP" > "$SIDE_SP/zz_parent_venv.pth"
if ! "$SIDE/bin/python" -c "import transformers, sys; sys.exit(0 if transformers.__version__ == '4.30.2' else 1)" 2>/dev/null; then
  echo "   installing transformers 4.30.2 into the side environment only (full output in $LOG)"
  if ! "$SIDE/bin/python" -m pip install "transformers==4.30.2" > "$LOG" 2>&1; then
    echo "   pip stopped. Its last lines:"; grep -v '^\s*$' "$LOG" | tail -12 | sed 's/^/      /'
    exit 1
  fi
fi
"$SIDE/bin/python" -c "import transformers, tokenizers, torch, spacy; print('   side environment: transformers', transformers.__version__, 'tokenizers', tokenizers.__version__, 'torch', torch.__version__)" || exit 1
echo "$SIDE/bin/python"
