import sys
from pathlib import Path

GEN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GEN))
import _bootstrap  # noqa: E402,F401
