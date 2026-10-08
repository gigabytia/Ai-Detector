"""Writes the OpenAPI schema used to generate frontend types (ADR-018)."""

import argparse
import json
from pathlib import Path

from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    schema = create_app().openapi()
    args.output.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
