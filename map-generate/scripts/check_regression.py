#!/usr/bin/env python3
"""check_regression.py — re-render the Thirsty O'-Well (both states) and compare with the recorded hashes.

Run after changing core.py, features.py or a biome. The maps already in the Foundry world must keep
rendering the same, or a re-generated map won't match tokens, walls and notes placed on the old one.
Hashes depend on the Pillow/numpy/scipy versions in examples/regression.json; on other versions a
mismatch may only mean an encoder change: compare the previews by eye, then re-record with --update.
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

import numpy
import PIL
import scipy

HERE = pathlib.Path(__file__).resolve().parent
REC = HERE.parent / "examples" / "regression.json"
CASES = {"thirsty-well": [], "thirsty-well-cleared": ["--set", "well.state=cleared"]}


def main():
    update = "--update" in sys.argv
    versions = {"pillow": PIL.__version__, "numpy": numpy.__version__, "scipy": scipy.__version__}
    rec = json.loads(REC.read_text()) if REC.exists() else {}
    got, ok = {}, True
    with tempfile.TemporaryDirectory() as tmp:
        for name, extra in CASES.items():
            out = pathlib.Path(tmp) / name
            subprocess.run([sys.executable, HERE / "generate_map.py", HERE.parent / "examples" / "thirsty-well.json",
                            out, *extra], check=True, stdout=subprocess.DEVNULL)
            got[name] = hashlib.sha256((out / "thirsty-o-well.webp").read_bytes()).hexdigest()
            same = got[name] == rec.get("hashes", {}).get(name)
            ok &= same
            print(f"{name}: {'same' if same else 'DIFFERENT'}")
    if update:
        REC.write_text(json.dumps({"versions": versions, "hashes": got}, indent=1) + "\n")
        print("recorded", REC)
    elif not ok and rec.get("versions") != versions:
        print(f"library versions differ from the recording ({rec.get('versions')} vs {versions})")
    sys.exit(0 if ok or update else 1)


if __name__ == "__main__":
    main()
