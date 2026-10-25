#!/usr/bin/env python3
"""Scan explicit production fields; narrative asset discovery remains a human task."""
import argparse
import json
import re
import sys
from pathlib import Path

TYPES = {"场景": "scene", "地点": "scene", "出场人物": "role", "人物": "role",
         "角色": "role", "主要人物": "role", "道具": "prop", "主要道具": "prop"}
FIELDS = list(TYPES) + ["画面", "运镜", "台词/声音", "台词", "声音", "动作"]
FIELD_RE = re.compile(r"^(" + "|".join(map(re.escape, sorted(FIELDS, key=len, reverse=True))) + r")(?:[零一二三四五六七八九十百\d]+)?\s*[:：]\s*(.*)$")
SPACE = {"内": "室内", "外": "室外", "内景": "室内", "外景": "室外",
         "室内": "室内", "室外": "室外", "半室外": "半室外"}
MIXED_SPACE = {"内外", "日内外", "夜内外", "外转内", "内转外", "内外连续"}
TIMES = {"日", "夜", "昼", "白天", "清晨", "黎明", "微明", "上午", "中午", "午后",
         "下午", "黄昏", "日落", "傍晚", "入夜", "入夜前", "夜晚", "深夜", "子夜", "凌晨",
         "时空不定", "稍后", "接续", "连续", "片刻后", "晚饭前", "接近正午"}
EMPTY = {"无", "无人", "无道具", "无出场人物", "无人物", "不适用", "—", "-", ""}


def clean(text):
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text.strip())
    text = re.sub(r"^\s*[-+]\s+", "", text)
    return re.sub(r"\*\*|__|`", "", text).strip()


def names(value):
    result = []
    parts, start, depth = [], 0, 0
    for i, char in enumerate(value):
        if char in "(（[【":
            depth += 1
        elif char in ")）]】":
            depth = max(0, depth - 1)
        elif char in "、,，;；" and depth == 0:
            parts.append(value[start:i])
            start = i + 1
    parts.append(value[start:])
    for part in parts:
        part = re.sub(r"[（(](?:画外(?:音)?|OS|VO|O\.S\.|V\.O\.)[）)]", "", part, flags=re.I).strip().rstrip("。.")
        if part not in EMPTY and part not in result:
            result.append(part)
    return result


def scene_parts(value):
    value = value.strip().rstrip("。.")
    explicit = re.fullmatch(r"(.*)[，,|｜;；]\s*([^，,|｜;；]+)[，,|｜;；]\s*([^，,|｜;；]+)", value)
    if explicit:
        name, time, spatial = [part.strip() for part in explicit.groups()]
        if spatial in SPACE or spatial in MIXED_SPACE:
            return name, time, SPACE.get(spatial, "内外混合")
    # Only consume delimited known annotations at the right edge of the field.
    tokens = re.split(r"[\s|｜·/（）(),，;；]+", value)
    end = len(tokens)
    while end and not tokens[end - 1]:
        end -= 1
    space, time = None, None
    consumed = []
    while end > 1:
        token = tokens[end - 1]
        if token in SPACE:
            space = SPACE[token]
        elif token in TIMES or re.fullmatch(r"(?:次日|当日|翌日)?(?:清晨|上午|中午|午后|下午|傍晚|夜晚|深夜|凌晨)", token):
            time = token
        elif token in {"日内", "日外", "夜内", "夜外"}:
            time = "白天" if token[0] == "日" else "夜晚"
            space = "室内" if token[-1] == "内" else "室外"
        elif token in MIXED_SPACE:
            space = "内外混合"
            if token in {"日内外", "夜内外"}:
                time = "白天" if token[0] == "日" else "夜晚"
        else:
            break
        consumed.insert(0, token)
        end -= 1
    name = value
    if consumed:
        suffix = r"[\s|｜·/（）(),，;；]+".join(map(re.escape, consumed))
        name = re.sub(r"[\s|｜·/（(,，;；]+" + suffix + r"[\s）)]*$", "", value).strip()
    return name, time, space


def scan(path):
    source = str(Path(path).resolve())
    text = Path(path).read_text(encoding="utf-8-sig")
    requirements, blocks, diagnostics = [], [], []
    episode, paragraph, shot = None, None, None
    current, table_headers = None, None
    fence = None

    def field(label, value, line):
        nonlocal current
        record = {"field": label, "text": value, "line": line,
                  "episode": episode, "paragraph": paragraph, "shot": shot}
        if current is None:
            current = {"episode": episode, "paragraph": paragraph, "shot": shot, "fields": []}
            blocks.append(current)
        current["fields"].append(record)
        if label not in TYPES:
            return
        asset_type = TYPES[label]
        if asset_type == "scene":
            if value in EMPTY:
                diagnostics.append({"line": line, "message": "场景为空，需人工核对"})
                return
            name, time, space = scene_parts(value)
            candidates = [name]
            record.update(name=name, time=time, space=space)
            if not time or not space:
                diagnostics.append({"line": line, "message": "场景时段或内外属性缺失，需上下文复核"})
            if space == "内外混合" or time == "时空不定":
                diagnostics.append({"line": line, "message": "混合空间或意象时段，须按镜头明确空间与版本"})
            if time in {"稍后", "接续", "连续", "片刻后"}:
                diagnostics.append({"line": line, "message": "相对时段，须核对前文实际时间"})
        else:
            candidates = names(value)
            if not value:
                diagnostics.append({"line": line, "message": label + "栏为空，需人工核对"})
        for name in candidates:
            requirements.append({"type": asset_type, "name": name, "source": source, "line": line,
                                 "status": "pending",
                                 "reason": ("仅为候选；须确认特殊剧情作用，普通物件归入陈设、服饰或镜头状态"
                                            if asset_type == "prop" else "需通读确认并映射"),
                                 "episode": episode, "paragraph": paragraph, "shot": shot})

    for number, raw in enumerate(text.splitlines(), 1):
        line = clean(raw)
        if not line:
            continue
        marker = re.match(r"^\s*(`{3,}|~{3,})", raw)
        if marker:
            token = marker.group(1)[0]
            fence = None if fence == token else token
            diagnostics.append({"line": number, "message": "发现代码围栏，其内容未扫描，需确认是否含有效分镜"})
            continue
        if fence:
            continue
        m = re.match(r"^第\s*([^\s集]+)\s*集", line)
        if m:
            episode, paragraph, shot, current = m.group(1), None, None, None
            table_headers = None
            continue
        if re.match(r"^(段落|段|镜头|镜号|镜)\s*[零一二三四五六七八九十百\d]", line):
            current = None
            if line.startswith(("段落", "段")):
                paragraph, shot = line, None
            else:
                shot = line
        if raw.lstrip().startswith("|") and "|" in raw[1:]:
            cells = [clean(c) for c in raw.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c.replace(" ", "")) for c in cells):
                continue
            if any(c.rstrip(":：") in TYPES for c in cells):
                table_headers = [c.rstrip(":：") for c in cells]
                continue
            if table_headers and len(cells) == len(table_headers):
                current = None
                shot = next((value for label, value in zip(table_headers, cells) if label in ("镜号", "镜头")), shot)
                for label, value in zip(table_headers, cells):
                    if label in FIELDS:
                        field(label, value, number)
                continue
            if table_headers:
                diagnostics.append({"line": number, "message": "表格列数不匹配，未读取此行"})
            else:
                diagnostics.append({"line": number, "message": "未识别表格标题，需人工核对"})
            continue
        table_headers = None
        m = FIELD_RE.match(line)
        if m:
            if m.group(1) in ("场景", "地点"):
                current = None
            field(m.group(1), m.group(2).strip(), number)
        elif re.match(r"^(场景|出场人物|主要道具|道具|地点)", line):
            diagnostics.append({"line": number, "message": "疑似资产字段未识别，需人工核对", "text": line})
    return {"source": source, "blocks": blocks, "requirements": requirements,
            "diagnostics": diagnostics,
            "limitations": ["只扫描显式字段，须通读画面、对白、动作补充实际所需资产",
                            "不自动完成身份归并、美术设计或版本选择"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    args = parser.parse_args()
    try:
        result = scan(args.source)
    except (OSError, UnicodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
