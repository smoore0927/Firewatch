"""Dump the FastAPI OpenAPI spec to disk for frontend type generation.

Run from firewatch-backend/ with the venv active:
  python scripts/dump_openapi.py

Writes to ../firewatch-frontend/openapi.json (the consumer location).
The frontend's `npm run generate:types` reads this file to produce
`src/types/generated.ts`.
"""

import json
import sys
from pathlib import Path

# Make `from main import app` work when running from firewatch-backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app


def main() -> None:
    output_path = (
        Path(__file__).resolve().parent.parent.parent
        / "firewatch-frontend"
        / "openapi.json"
    )
    spec = app.openapi()
    output_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rel = output_path.relative_to(Path.cwd().parent) if output_path.is_absolute() else output_path
    print(f"Wrote {len(json.dumps(spec))} bytes to {rel}")


if __name__ == "__main__":
    main()
