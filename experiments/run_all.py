from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parent))

import background_postprocessing  # noqa: E402
import expression_consistency  # noqa: E402
import runtime_manual_placeholder  # noqa: E402


def main() -> int:
    expression_consistency.main()
    background_postprocessing.main()
    runtime_manual_placeholder.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
