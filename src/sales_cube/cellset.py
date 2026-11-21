"""Compare single-measure, zero/one-row-axis MDX cellsets from the lab."""

import argparse
import json
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path

NS = {"m": "urn:schemas-microsoft-com:xml-analysis:mddataset"}


def read_cells(xml: str) -> list[list]:
    root = ET.fromstring(xml)
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] in {"Error", "Fault"}:
            raise ValueError(element.get("Description") or "XMLA error")
    axes = root.find(".//m:Axes", NS)
    if axes is None:
        raise ValueError("Multidimensional cellset expected")
    names = [axis.get("name") for axis in axes.findall("m:Axis", NS)]
    data_axes = [name for name in names if name != "SlicerAxis"]
    if data_axes not in (["Axis0"], ["Axis0", "Axis1"]):
        raise ValueError(f"Unexpected axes: {names}")
    columns = axes.findall("m:Axis[@name='Axis0']/m:Tuples/m:Tuple", NS)
    if len(columns) != 1 or len(columns[0].findall("m:Member", NS)) != 1:
        raise ValueError("One measure expected")
    rows = [[]]
    if "Axis1" in data_axes:
        rows = []
        for item in axes.findall("m:Axis[@name='Axis1']/m:Tuples/m:Tuple", NS):
            captions = item.findall("m:Member/m:Caption", NS)
            if len(captions) != 1 or captions[0].text is None:
                raise ValueError("One row caption expected")
            rows.append([captions[0].text])
    values = {}
    for cell in root.findall(".//m:CellData/m:Cell", NS):
        ordinal = int(cell.attrib["CellOrdinal"])
        raw = cell.findtext("m:Value", namespaces=NS)
        try:
            value = Decimal(raw or "")
        except InvalidOperation as exc:
            raise ValueError(f"Invalid numeric cell: {raw}") from exc
        if (
            not value.is_finite()
            or value != value.to_integral_value()
            or ordinal in values
        ):
            raise ValueError(f"Invalid cell at {ordinal}: {raw}")
        values[ordinal] = int(value)
    if set(values) != set(range(len(rows))):
        raise ValueError("Missing or extra cells")
    return [row + [values[i]] for i, row in enumerate(rows)]


def compare(expected: dict, actual: Path, queries: Path | None = None) -> int:
    """Compare every expected cellset; the query and answer file sets must be exact."""
    folders = [("answer", actual, "*.xml")]
    if queries is not None:
        folders.append(("query", queries, "*.mdx"))
    for kind, folder, pattern in folders:
        found = {path.stem for path in folder.glob(pattern)}
        if found != set(expected):
            missing, extra = (
                sorted(set(expected) - found),
                sorted(found - set(expected)),
            )
            raise ValueError(
                f"{kind} files differ from the reference: missing {missing}, extra {extra}"
            )
    for name, rows in expected.items():
        received = read_cells((actual / f"{name}.xml").read_text(encoding="utf-8-sig"))
        if rows != received:
            raise ValueError(f"{name}: expected {rows}, received {received}")
    return len(expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected", type=Path)
    parser.add_argument("actual", type=Path)
    parser.add_argument(
        "--queries", type=Path, help="folder with the .mdx files that were executed"
    )
    args = parser.parse_args()
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    try:
        count = compare(expected, args.actual, args.queries)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"{count} MDX cellsets match the reference")


if __name__ == "__main__":
    main()
