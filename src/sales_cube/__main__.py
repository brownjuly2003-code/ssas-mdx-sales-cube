import argparse
import json
from pathlib import Path

from .data import build_star, write_inserts
from .reference import reference


def main():
    parser = argparse.ArgumentParser(
        description="Build the SQL seed and expected MDX cellsets."
    )
    parser.add_argument("--output", type=Path, default=Path("reports"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    star = build_star()
    answers = reference(star)
    write_inserts(star, args.output / "seed.sql")
    (args.output / "expected.json").write_text(
        json.dumps(answers, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    summary = [
        "seed=64",
        *(f"{table}: {len(frame)}" for table, frame in star.items()),
        *(f"{name}: {rows}" for name, rows in answers.items()),
    ]
    (args.output / "summary.txt").write_text(
        "\n".join(summary) + "\n", encoding="utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
