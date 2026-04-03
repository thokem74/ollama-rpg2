#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def is_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def format_compact_json(value: object, indent: int = 0) -> str:
    indent_text = " " * indent
    next_indent = indent + 2
    next_indent_text = " " * next_indent

    if isinstance(value, dict):
        if all(is_scalar(item) for item in value.values()):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

        lines = ["{"]
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            formatted_item = format_compact_json(item, next_indent)
            suffix = "," if index < len(items) - 1 else ""
            lines.append(f'{next_indent_text}{json.dumps(key, ensure_ascii=False)}: {formatted_item}{suffix}')
        lines.append(f"{indent_text}}}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            return "[]"

        lines = ["["]
        for index, item in enumerate(value):
            formatted_item = format_compact_json(item, next_indent)
            suffix = "," if index < len(value) - 1 else ""
            lines.append(f"{next_indent_text}{formatted_item}{suffix}")
        lines.append(f"{indent_text}]")
        return "\n".join(lines)

    return json.dumps(value, ensure_ascii=False)


def normalize_record(record: object) -> object:
    if isinstance(record, dict):
        normalized: dict[object, object] = {}
        for key, value in record.items():
            if key == "responseText" and isinstance(value, str):
                try:
                    normalized[key] = format_compact_json(json.loads(value))
                except json.JSONDecodeError:
                    normalized[key] = value
            else:
                normalized[key] = normalize_record(value)
        return normalized

    if isinstance(record, list):
        return [normalize_record(item) for item in record]

    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a JSONL file into a pretty-printed JSON array."
    )
    parser.add_argument("input", type=Path, help="Path to the input .jsonl file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Path to the output .json file. Defaults to <input>.pretty.json.",
    )
    return parser.parse_args()


def default_output_path(input_path: Path) -> Path:
    if input_path.suffix:
        return input_path.with_suffix(".pretty.json")
    return input_path.with_name(f"{input_path.name}.pretty.json")


def load_jsonl(input_path: Path) -> list[object]:
    records: list[object] = []
    for line_number, raw_line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(
                f"Invalid JSON on line {line_number} of {input_path}: {exc.msg}"
            ) from exc
    return records


def main() -> None:
    args = parse_args()
    input_path = args.input
    output_path = args.output or default_output_path(input_path)

    records = normalize_record(load_jsonl(input_path))
    pretty_text = json.dumps(records, ensure_ascii=False, indent=2)
    pretty_text = pretty_text.replace("\\n", "\n")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        pretty_text + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} records to {output_path}")


if __name__ == "__main__":
    main()
