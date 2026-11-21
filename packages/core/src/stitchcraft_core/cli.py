"""Command line: stitchcraft validate | preview | gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stitchcraft_core.params import Params


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="stitchcraft")
    sub = ap.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="check a pattern, print diagnostics as JSON")
    v.add_argument("file", type=Path)
    v.add_argument("--dialect", default="de")

    p = sub.add_parser("preview", help="simulate a pattern, write yarn.bin, model.glb, shape.json")
    p.add_argument("file", type=Path)
    p.add_argument("--dialect", default="de")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--fill", type=float, default=Params.fill)
    p.add_argument("--hook-mm", type=float, default=Params.hook_mm)
    p.add_argument("--yarn-mm", type=float, default=Params.yarn_mm)

    g = sub.add_parser("gate", help="run the M1 acceptance measurements and write the report")
    g.add_argument("--reference", type=Path, default=Path("tests/reference"))
    g.add_argument("--report", type=Path, default=Path("docs/evaluation/m1.md"))

    args = ap.parse_args(argv)
    if args.cmd == "validate":
        from stitchcraft_core.serialize import validation_dict
        from stitchcraft_core.validate import validate

        result = validate(args.file.read_text(encoding="utf-8"), dialect=args.dialect)
        json.dump(validation_dict(result), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0 if result.ok else 1
    if args.cmd == "preview":
        from stitchcraft_core.export import encode_yarn_bin, glb_bytes, shape_json
        from stitchcraft_core.pipeline import PreviewError, preview
        from stitchcraft_core.serialize import validation_dict

        params = Params(fill=args.fill, hook_mm=args.hook_mm, yarn_mm=args.yarn_mm)
        try:
            made = preview(args.file.read_text(encoding="utf-8"), args.dialect, params)
        except PreviewError as exc:
            json.dump(validation_dict(exc.validation), sys.stderr, ensure_ascii=False, indent=2)
            sys.stderr.write("\n")
            return 1
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "yarn.bin").write_bytes(encode_yarn_bin(made.yarn))
        (args.out / "model.glb").write_bytes(glb_bytes(made.yarn))
        (args.out / "shape.json").write_text(json.dumps(shape_json(made)), encoding="utf-8")
        return 0
    if args.cmd == "gate":
        from stitchcraft_core.gate import write_report

        report = write_report(args.reference, args.report)
        print(report)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
