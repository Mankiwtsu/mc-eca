"""Print the CHANGELOG.md section of one version (used by the release workflow).

    python tools/release_notes.py 0.5.0
"""

import re
import sys
from pathlib import Path

version = sys.argv[1]
text = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
match = re.search(rf"^## {re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
if not match:
    sys.exit(f"No section for {version} in CHANGELOG.md")
print(match.group(1).strip())
print("\n---\n**Install:** see the [install guide](../../blob/main/docs/01-install.md). "
      "Easiest: import `mc-eca-" + version + ".mrpack` in Prism Launcher or the Modrinth App.")
