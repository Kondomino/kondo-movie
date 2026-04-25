"""
Make `src/` importable for all test modules.

Without this, `from movie_maker.edl_manager import EDLManager` fails because
the source layout is `src/movie_maker/...` but the project has no top-level
package and pytest does not add `src/` automatically.

Existing tests do `sys.path.append(...)` per file; this conftest replaces
that pattern (those manual appends become redundant but harmless).
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
