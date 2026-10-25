#!/usr/bin/env python3
"""Validate and export the complete JSON package and classified TXT files."""
import argparse
import sys
from pathlib import Path

from assets_core import export_txt, load_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="- 从标准输入读取完整数据；默认仍交付 JSON")
    parser.add_argument("output", help="不存在或为空的本次交付目录")
    parser.add_argument("--source", action="append", default=[], help="制作分镜或剧本，可重复")
    parser.add_argument("--txt-only", action="store_true",
                        help="仅用户明确要求仅 TXT 或不保存 JSON 时使用")
    args = parser.parse_args()
    try:
        report, written = export_txt(load_data(args.input), args.output, args.source,
                                     include_json=not args.txt_only)
    except (OSError, UnicodeError, ValueError) as exc:
        print("导出失败：" + str(exc), file=sys.stderr)
        return 1
    report.print()
    for label, count in written:
        print(f"{label}：{count} 条")
    if args.txt_only:
        print("按明确的仅 TXT 要求导出；TXT 已回读核对。输出目录：" + args.output)
    else:
        print("JSON：" + str(Path(args.output).resolve() / "资产.json"))
        print("完整 JSON 与分类 TXT 已回读核对。输出目录：" + args.output)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
