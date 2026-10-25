"""Shared validation and verified TXT export; no model or third-party dependency."""
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from parse_storyboard import scan

TYPES = ("role", "scene", "prop")
FOLDERS = {"role": "角色资产", "scene": "场景资产", "prop": "道具资产"}
ROLE_LABELS = ["姓名", "别名", "颜值定位", "人设描述", "声线类型"]
DIMENSIONS = ["面部特征", "发型", "发饰", "身材比例", "衣着", "气质"]
SCENE_LABELS = ["场景名称", "别名", "版本", "时间", "场景类型", "时代与地域", "空间结构",
                "视觉陈设与标志物", "材质与工艺", "色彩体系", "光影", "氛围与情绪",
                "视觉记忆点", "美术控制"]
PROP_LABELS = ["道具名称", "别名", "版本", "道具类别", "美学定位", "外形", "纹样与工艺",
               "特征", "材质", "色彩与光泽", "使用状态", "美术控制"]
STYLE_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:PBR|CG|[23]D)(?![A-Za-z0-9])|"
    r"真人(?:画风|风格|实拍|质感|电影)|照片级|摄影级|超写实|写实(?:风格|画风|国漫)|"
    r"动漫(?:风格|画风)|国漫|二次元|油画风|水彩风|卡通风|赛璐璐|画风|"
    r"虚幻引擎|Unreal\s*Engine|Octane|Redshift|"
    r"photoreal(?:istic|ism)?|live[\s-]?action|anime\s*style|realistic\s*style|"
    r"--(?:ar|stylize|style|seed|v)\s+\S+"
)
PLACEHOLDER_RE = re.compile(r"未明|未指明|不详|未设定|视剧情而定|整体平面未明|按身份与年代统一设计|按场景功能统一设计")
RELATIONAL_RE = re.compile(r"同上|同前|(?:沿用|参照)[^，。；\n]{0,16}(?:场景|正厅|东屋|院子|正屋)|与[^，。；\n]{0,16}(?:场景|正厅|东屋|院子|正屋)[^，。；\n]{0,8}(?:一致|相同|一样)")
TIME_GROUPS = {
    "白天": {"白天", "清晨", "上午", "中午", "午后", "下午", "黎明", "微明"},
    "傍晚": {"傍晚", "黄昏", "日落", "入夜", "微明"},
    "夜晚": {"夜晚", "深夜", "子夜", "凌晨", "黎明"},
}
MATERIAL_RE = re.compile(r"棉|麻|丝|绸|缎|皮|毡|绒|纱|毛呢|羊毛|羊绒|锦|布|木|竹|银|金|铜|铁|钢|珠|玉|骨|角|草|陶|瓷|塑料|树脂|玻璃|金属|合金|合成纤维|聚酯|尼龙|鳞|羽")
SURFACE_RE = re.compile(r"纹|织|光|磨|缝|绣|编|雕|抛|拉丝|起毛|粗|细|透|软|厚|薄|挺|垂|包边|锁边|补丁|接缝")
ABSENCE_RE = re.compile(r"无(?:发饰|衣着|服装|衣物|佩饰|配饰|覆盖物|任何)|不(?:具|佩|穿)|未佩|没有")


@dataclass
class Report:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    assets: dict = field(default_factory=lambda: {k: [] for k in TYPES})
    legacy: bool = False

    @property
    def ok(self):
        return not self.errors

    def print(self):
        for message in self.warnings:
            print("警告: " + message)
        for message in self.errors:
            print("错误: " + message)
        print(f"自动检查{'通过' if self.ok else '失败'}：{len(self.errors)} 错误，{len(self.warnings)} 警告")
        print("范围：结构、已提供的名称映射及指定制作来源；自由叙述覆盖、事实忠实与美术质量仍须人工复核。")


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复 JSON 键：{key}")
        result[key] = value
    return result


def load_data(source):
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8-sig")
    return json.loads(raw, object_pairs_hook=_unique_object,
                      parse_constant=lambda word: (_ for _ in ()).throw(ValueError("非法数值：" + word)))


def labeled(text, labels, bracket=False):
    if bracket:
        pattern = r"^\s*【(" + "|".join(map(re.escape, labels)) + r")】\s*[:：]\s*(.*?)\s*$"
        parsed, order = {}, []
        for line in text.splitlines():
            m = re.match(pattern, line)
            if not m or m.group(1) in parsed:
                return {}, []
            parsed[m.group(1)] = m.group(2)
            order.append(m.group(1))
        return parsed, order
    pattern = r"(?:^|[；;\n])\s*(" + "|".join(map(re.escape, labels)) + r")\s*[:：]\s*"
    matches = list(re.finditer(pattern, text))
    parsed, order = {}, []
    for i, match in enumerate(matches):
        key = match.group(1)
        if key in parsed:
            return {}, []
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parsed[key] = text[match.end():end].strip().rstrip("；;")
        order.append(key)
    return parsed, order


def body_aliases(value):
    return [] if value == "无" else [x.strip() for x in value.split("、") if x.strip()]


def _legacy(data, report):
    report.legacy = True
    report.warnings.append("旧版字典缺少实体、版本和来源；仅兼容检查，不能证明与分镜对应。")
    for asset_type in TYPES:
        items = data.get(asset_type)
        if not isinstance(items, dict):
            report.errors.append(f"{asset_type} 必须为映射对象")
            continue
        for number, (name, desc) in enumerate(items.items(), 1):
            if not nonempty(desc):
                report.errors.append(f"{asset_type}:{name} 描述必须为非空文本")
                continue
            if asset_type == "role":
                fields, _ = labeled(desc, ROLE_LABELS + ["群像"], bracket=True)
            else:
                fields, _ = labeled(desc, SCENE_LABELS if asset_type == "scene" else PROP_LABELS)
            report.assets[asset_type].append({
                "id": f"{asset_type}-{number}", "entity_id": f"{asset_type}-{number}",
                "name": fields.get("场景名称", fields.get("道具名称", name)),
                "aliases": body_aliases(fields.get("别名", "无")),
                "variant": fields.get("版本", "基础"), "description": desc, "sources": [],
                "kind": "group" if "群像" in fields else "individual",
            })


def _check_description(asset_type, asset, report):
    tag = f"{asset_type}:{asset['id']}"
    desc = asset["description"]
    if any(line.strip() == "@" for line in desc.splitlines()):
        report.errors.append(f"{tag} 正文含独立 @ 行，会破坏 TXT 分隔")
    if STYLE_RE.search(desc):
        report.errors.append(f"{tag} 含画风或渲染参数，应交给下游模板")
    if PLACEHOLDER_RE.search(desc):
        report.errors.append(f"{tag} 含未完成设计的占位句")
    if RELATIONAL_RE.search(desc):
        report.errors.append(f"{tag} 含跨资产指代，须独立写全")
    if asset_type == "role":
        expected = ROLE_LABELS.copy()
        if asset.get("kind") == "group":
            expected[0] = "群像"
        fields, order = labeled(desc, expected, bracket=True)
        if order != expected or not all(nonempty(fields.get(k)) for k in expected):
            report.errors.append(f"{tag} 必须为非空五行且字段顺序正确")
            return
        if fields[expected[0]] != asset["name"]:
            report.errors.append(f"{tag} 正文姓名与记录名称不一致")
        dimensions = fields["人设描述"]
        # Delimit on labels rather than punctuation, so comma/semicolon choices cannot bypass checks.
        matches = list(re.finditer(r"(" + "|".join(DIMENSIONS) + r")\s*[:：]", dimensions))
        if [m.group(1) for m in matches] != DIMENSIONS:
            report.errors.append(f"{tag} 人设必须恰好包含按序六项")
        else:
            dimension_values = {}
            for i, match in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(dimensions)
                value = dimensions[match.end():end].strip("，,；;。 \t")
                dimension_values[match.group(1)] = value
                if not value:
                    report.errors.append(f"{tag} {match.group(1)}为空")
            for label in ("发饰", "衣着"):
                value = dimension_values[label]
                if asset.get("kind") != "voice" and not ABSENCE_RE.search(value):
                    if not MATERIAL_RE.search(value):
                        report.errors.append(f"{tag} {label}缺少具体材质")
                    if not SURFACE_RE.search(value):
                        report.errors.append(f"{tag} {label}缺少工艺或表面质感")
        if re.search(r"(身份|关系|年龄|性别|经历|动作习惯|依据|画面|运镜)\s*[:：]", dimensions):
            report.errors.append(f"{tag} 人设含非外观字段")
        if not report.legacy:
            version = re.search(r"造型版本\s*[:：]\s*([^；;\n]+)", fields["颜值定位"])
            if not version or version.group(1).strip() != asset["variant"]:
                report.errors.append(f"{tag} 颜值定位须包含匹配的造型版本")
        if len(dimensions) < 450 and asset.get("kind") != "voice":
            report.warnings.append(f"{tag} 人设较短，请复核五官、轮廓、层次、材质及辨识度")
    else:
        expected = SCENE_LABELS if asset_type == "scene" else PROP_LABELS
        fields, order = labeled(desc, expected)
        legacy_expected = [x for x in expected if x not in ("版本",)]
        permitted = (expected, legacy_expected) if report.legacy else (expected,)
        if order not in permitted or not all(nonempty(fields.get(k)) for k in order) or not order:
            report.errors.append(f"{tag} 描述字段缺失、重复、为空或顺序错误，应为 {'、'.join(expected)}")
            return
        name_label = "场景名称" if asset_type == "scene" else "道具名称"
        if fields[name_label] != asset["name"]:
            report.errors.append(f"{tag} 正文名称与记录名称不一致")
        if not report.legacy and fields["版本"] != asset["variant"]:
            report.errors.append(f"{tag} 正文版本与记录不一致")
        if asset_type == "scene":
            if fields["场景类型"] not in {"室内", "室外", "半室外"}:
                report.errors.append(f"{tag} 场景类型必须明确为室内/室外/半室外")
            time = re.fullmatch(r"(白天|傍晚|夜晚)(?:[（(]([^（）()]+)[）)])?", fields["时间"])
            if not time:
                report.errors.append(f"{tag} 时间须为白天/傍晚/夜晚，可附实际时段")
            elif time.group(2):
                units = re.split(r"[、,，]", time.group(2))
                if any(unit.strip() not in TIME_GROUPS[time.group(1)] for unit in units):
                    report.errors.append(f"{tag} 实际时段与时间档位不一致")
        minimum = 450 if asset_type == "scene" else 250
        if len(desc) < minimum:
            report.warnings.append(f"{tag} 描述较短，请复核结构、工艺、色彩和视觉记忆点")
    if body_aliases(fields.get("别名", "")) != asset["aliases"]:
        report.errors.append(f"{tag} 正文别名与记录别名不一致")


def _path_key(value):
    return os.path.normcase(str(Path(value).resolve()))


def validate(data, source_paths=()):
    report = Report()
    if not isinstance(data, dict):
        report.errors.append("顶层必须为对象")
        return report
    legacy = "schema_version" not in data and "assets" not in data
    if legacy:
        _legacy(data, report)
    elif data.get("schema_version") != 2 or not isinstance(data.get("assets"), dict):
        report.errors.append("必须使用 schema_version=2 和 assets 对象")
        return report
    else:
        for asset_type in TYPES:
            items = data["assets"].get(asset_type)
            if not isinstance(items, list):
                report.errors.append(f"assets.{asset_type} 必须为数组")
            else:
                report.assets[asset_type] = items
    index, signatures = {}, set()
    for asset_type in TYPES:
        valid_items = []
        for asset in report.assets[asset_type]:
            if not isinstance(asset, dict):
                report.errors.append(f"{asset_type} 资产记录必须为对象")
                continue
            required = ["id", "entity_id", "name", "variant", "description"]
            if not all(nonempty(asset.get(k)) for k in required):
                report.errors.append(f"{asset_type} 缺少非空 id/entity_id/name/variant/description")
                continue
            aliases = asset.get("aliases")
            if not isinstance(aliases, list) or any(not nonempty(a) for a in aliases):
                report.errors.append(f"{asset_type}:{asset['id']} aliases 必须为非空文本的数组")
                continue
            if len(set(aliases)) != len(aliases) or asset["name"] in aliases:
                report.errors.append(f"{asset_type}:{asset['id']} 别名重复或与主名重复")
            if asset.get("kind", "individual") not in {"individual", "group", "voice"}:
                report.errors.append(f"{asset_type}:{asset['id']} kind 无效")
            if asset["id"] in index:
                report.errors.append("重复资产 ID：" + asset["id"])
            index[asset["id"]] = (asset_type, asset)
            signature = (asset_type, asset["entity_id"], asset["variant"])
            if signature in signatures:
                report.errors.append(f"{asset_type}:{asset['id']} 同实体同版本重复建档")
            signatures.add(signature)
            valid_items.append(asset)
            _check_description(asset_type, asset, report)
        report.assets[asset_type] = valid_items
    if not index:
        report.errors.append("没有可导出的有效资产")
    if report.legacy:
        if source_paths:
            report.errors.append("旧版数据不支持制作来源覆盖检查，请补为 v2")
        return report
    requirements = data.get("requirements")
    if not isinstance(requirements, list):
        report.errors.append("requirements 必须为数组")
        return report
    if not requirements:
        report.errors.append("缺少需求映射，不能验证制作名称对应")
    source_cache, supplied = {}, {}

    def read_source(value):
        if not nonempty(value):
            return None
        try:
            key = _path_key(value)
            if key not in source_cache:
                source_cache[key] = Path(value).read_text(encoding="utf-8-sig").splitlines()
            return source_cache[key]
        except (OSError, UnicodeError, ValueError) as exc:
            report.errors.append(f"无法读取来源 {value}：{exc}")
            return None

    for path in source_paths:
        key = _path_key(path)
        supplied[key] = str(path)
        read_source(str(path))
    if not supplied:
        report.warnings.append("未指定 --source，未独立扫描完整制作文件；只能检查已提供需求和引用")

    def check_ref(ref, names, label):
        if not isinstance(ref, dict):
            report.errors.append(label + " 来源引用必须为对象")
            return False
        path, line = ref.get("source"), ref.get("line")
        if not nonempty(path) or type(line) is not int or line < 1:
            report.errors.append(label + " 来源必须含 source 与从1开始的整数 line")
            return False
        if supplied and _path_key(path) not in supplied:
            report.errors.append(label + " 引用了非本轮制作来源，辅助小说不能单独证明资产需求")
            return False
        lines = read_source(path)
        if lines is None:
            return False
        if line > len(lines) or not any(name in lines[line - 1] for name in names):
            report.errors.append(label + " 来源行未出现对应主名/别名")
            return False
        return True

    handled, mapped_ids, mapped_refs = set(), set(), {}
    for req in requirements:
        if not isinstance(req, dict):
            report.errors.append("需求记录必须为对象")
            continue
        asset_type, name = req.get("type"), req.get("name")
        if asset_type not in TYPES or not nonempty(name):
            report.errors.append("需求缺少有效 type/name")
            continue
        good_ref = check_ref(req, [name], f"需求:{name}")
        if good_ref:
            key = (_path_key(req["source"]), req["line"], asset_type, name)
            if key in handled:
                report.errors.append(f"重复需求记录：{name}，行 {req['line']}")
            handled.add(key)
        if req.get("status") == "excluded":
            if not nonempty(req.get("reason")):
                report.errors.append(f"排除需求 {name} 必须说明理由")
            continue
        if req.get("status") != "mapped":
            report.errors.append(f"需求 {name} 未完成明确映射")
            continue
        ids = req.get("asset_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or x not in index for x in ids):
            report.errors.append(f"需求 {name} 必须指向存在的具体资产 ID")
            continue
        if len(set(ids)) != len(ids):
            report.errors.append(f"需求 {name} 重复引用同一资产 ID")
        if len(ids) > 1 and not nonempty(req.get("usage")):
            report.errors.append(f"需求 {name} 同时使用多个资产时须说明 usage，不得保留歧义候选")
        for asset_id in ids:
            mapped_type, asset = index[asset_id]
            if mapped_type != asset_type or name not in [asset["name"], *asset["aliases"]]:
                report.errors.append(f"需求 {name} 未精确命中同类型资产主名或别名")
            else:
                mapped_ids.add(asset_id)
                mapped_refs.setdefault(asset_id, []).append(req)
    for asset_id, (asset_type, asset) in index.items():
        if asset_id not in mapped_ids:
            report.errors.append(f"{asset_type}:{asset_id} 没有映射的制作需求")
        refs = asset.get("sources")
        if not isinstance(refs, list) or not refs:
            report.errors.append(f"{asset_type}:{asset_id} 缺少制作来源")
        else:
            for ref in refs:
                check_ref(ref, [asset["name"], *asset["aliases"]], f"{asset_type}:{asset_id}")
            naming_lines = []
            for ref in refs:
                if isinstance(ref, dict) and nonempty(ref.get("source")) and type(ref.get("line")) is int:
                    lines = read_source(ref["source"])
                    if lines and 1 <= ref["line"] <= len(lines):
                        naming_lines.append(lines[ref["line"] - 1])
            for req in mapped_refs.get(asset_id, []):
                if nonempty(req.get("source")) and type(req.get("line")) is int:
                    lines = read_source(req["source"])
                    if lines and 1 <= req["line"] <= len(lines):
                        naming_lines.append(lines[req["line"] - 1])
            for name in [asset["name"], *asset["aliases"]]:
                if not any(name in line for line in naming_lines):
                    report.errors.append(f"{asset_type}:{asset_id} 主名或别名“{name}”没有对应制作来源")
    for path in supplied.values():
        try:
            scanned = scan(path)
        except (OSError, UnicodeError) as exc:
            report.errors.append(f"扫描来源失败：{exc}")
            continue
        for diag in scanned["diagnostics"]:
            report.warnings.append(f"{path}:{diag['line']} {diag['message']}")
        for req in scanned["requirements"]:
            key = (_path_key(req["source"]), req["line"], req["type"], req["name"])
            if key not in handled:
                report.errors.append(f"制作字段未处理：{req['type']}:{req['name']}，{path}:{req['line']}")
    return report


def export_txt(data, output, source_paths=()):
    report = validate(data, source_paths)
    if not report.ok:
        raise ValueError("\n".join(report.errors))
    output = Path(output).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("输出目录已存在且非空，请使用新的交付目录，保留旧包")
    output.parent.mkdir(parents=True, exist_ok=True)
    written = []
    with tempfile.TemporaryDirectory(prefix=".shot-assets-", dir=output.parent) as temporary:
        staging = Path(temporary)
        for asset_type in TYPES:
            items = report.assets[asset_type]
            if not items:
                continue
            folder = staging / FOLDERS[asset_type]
            folder.mkdir()
            target = folder / (FOLDERS[asset_type] + ".txt")
            expected = [item["description"].replace("\r\n", "\n").rstrip("\r\n") for item in items]
            target.write_bytes(("\n@\n".join(expected) + "\n").encode("utf-8"))
            actual = target.read_text(encoding="utf-8").rstrip("\n").split("\n@\n")
            if actual != expected:
                raise ValueError("TXT 回读校验失败：" + asset_type)
            written.append((FOLDERS[asset_type], len(items)))
        if not output.exists():
            staging.rename(output)
            # TemporaryDirectory safely tolerates the staging path having been moved.
        else:
            for folder in staging.iterdir():
                folder.rename(output / folder.name)
    return report, written
