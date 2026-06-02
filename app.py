"""Streamlit entry point (run from project root: streamlit run app.py)."""

import sys
from pathlib import Path

# Streamlit Cloud installs requirements.txt but may not install this repo as a package.
# Ensure src/ is on the path so `import sampletracker` works.
_SRC_DIR = Path(__file__).resolve().parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from sampletracker.app import main

if __name__ == "__main__":
    main()
