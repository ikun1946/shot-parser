#!/usr/bin/env python3
"""Check complete v2 assets via stdin or the delivered JSON package."""
import argparse
import sys

from assets_core import load_data, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="交付的资产.json，或 - 从标准输入读取完整数据")
    parser.add_argument("--source", action="append", default=[], help="制作分镜或剧本，可重复")
    parser.add_argument("--detail-level", choices=["cinematic"], help="兼容旧参数；详细美术已为默认规范")
    args = parser.parse_args()
    try:
        report = validate(load_data(args.input), args.source)
    except (OSError, UnicodeError, ValueError) as exc:
        print("检查失败：" + str(exc), file=sys.stderr)
        return 1
    report.print()
    return 0 if report.ok else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
