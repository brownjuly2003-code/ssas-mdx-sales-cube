"""Prepare the MDX statements for Mondrian 3.2 and report its answers.

Mondrian is the substitute engine of the lab, not SSAS. The MDX files stay the SSAS text.
Two changes are made on the way to Mondrian 3.2, both visible in the statements folder:
the final ';' (a client statement terminator, rejected by the Mondrian 3.2 scanner) is
dropped, and a query Mondrian 3.2 does not accept gets an exact, listed text replacement.
"""

import argparse
import json
from pathlib import Path

from .cellset import read_cells

# query -> [(SSAS text, Mondrian 3.2 text, reason)]; every pair must match exactly once.
ADAPTATIONS: dict[str, list[tuple[str, str, str]]] = {
    "09_top_products": [
        (
            '.Properties("KEY0", TYPED)',
            '.Properties("KEY0")',
            "the Mondrian 3.2 parser has no TYPED flag and reads it as a member name;"
            " KEY0 is declared in cube/mondrian.xml as a numeric property of the"
            " ProductKey column, so the tie-break gets the same number",
        )
    ]
}


def strip_terminator(text: str) -> str:
    body = text.rstrip()
    return body[:-1].rstrip() + "\n" if body.endswith(";") else text


def adapt(name: str, text: str) -> str:
    for old, new, _ in ADAPTATIONS.get(name, []):
        if text.count(old) != 1:
            raise ValueError(f"{name}: expected one occurrence of {old!r}")
        text = text.replace(old, new)
    return text


def write_statements(queries: Path, output: Path) -> tuple[list[str], int]:
    """Write the Mondrian text of every .mdx file into a new folder.

    Returns the names of the queries changed by ADAPTATIONS and the number of dropped ';'.
    """
    files = sorted(queries.glob("*.mdx"))
    unknown = set(ADAPTATIONS) - {path.stem for path in files}
    if unknown:
        raise ValueError(f"adaptations for missing queries: {sorted(unknown)}")
    output.mkdir(parents=True, exist_ok=False)
    changed, terminators = [], 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        base = strip_terminator(text)
        terminators += base != text
        statement = adapt(path.stem, base)
        if statement != base:
            changed.append(path.stem)
        (output / path.name).write_text(statement, encoding="utf-8", newline="\n")
    return changed, terminators


def report(expected: dict, answers: Path, engine: str = "Mondrian") -> list[str]:
    """One line per query: expected rows, rows received from the engine, match.

    The same table serves the answers of SSAS (scripts/Compare-Cube.ps1, engine="SSAS").
    """
    lines = []
    for name, rows in expected.items():
        path = answers / f"{name}.xml"
        try:
            received = read_cells(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            received = f"error: {exc}"
        verdict = "yes" if received == rows else "NO"
        lines.append(
            f"{name} | expected {rows} | {engine} {received} | match {verdict}"
        )
    matched = sum(line.endswith("match yes") for line in lines)
    lines.append(f"{matched}/{len(expected)} {engine} answers match the reference")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("statements", help="write the Mondrian MDX texts")
    prepare.add_argument("--queries", type=Path, default=Path("mdx"))
    prepare.add_argument("--output", type=Path, required=True)
    summary = commands.add_parser("report", help="print the comparison table")
    summary.add_argument("expected", type=Path)
    summary.add_argument("answers", type=Path)
    summary.add_argument(
        "--engine", default="Mondrian", help="label of the answering engine"
    )
    args = parser.parse_args()
    if args.command == "statements":
        changed, terminators = write_statements(args.queries, args.output)
        print(
            f"statements written to {args.output}; final ';' dropped in {terminators}"
        )
        print(f"changed for Mondrian: {changed}")
        for name in changed:
            for old, new, reason in ADAPTATIONS[name]:
                print(f"{name}: {old!r} -> {new!r} ({reason})")
        return
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    lines = report(expected, args.answers, args.engine)
    print("\n".join(lines))
    if not lines[-1].startswith(f"{len(expected)}/{len(expected)} "):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
