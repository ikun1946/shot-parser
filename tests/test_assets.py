import copy
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from assets_core import export_txt, load_data, validate
from parse_storyboard import scan


def role_text(name="阿月", aliases="姑娘", variant="基础", voice="清亮女音"):
    return "\n".join([
        "【姓名】: " + name, "【别名】: " + aliases,
        "【颜值定位】: 造型版本：" + variant + "；清秀灵动，轮廓协调",
        "【人设描述】: 面部特征：鹅蛋脸，左眉保留陈旧伤痕，瞳色深褐；发型：乌黑长发低束；"
        "发饰：无发饰，发束自然收拢；身材比例：身形纤细，肩腰比例自然；"
        "衣着：内外层均为棉布，平纹哑光，领袖细密锁边，灰蓝外层与米白内层协调；气质：目光清亮，仪态自然",
        "【声线类型】: " + voice,
    ])


def scene_text(name="刘家正厅", variant="基础", time="白天（清晨）"):
    return (f"场景名称：{name}；别名：无；版本：{variant}；时间：{time}；场景类型：室内；"
            "时代与地域：古代乡村；空间结构：长方形正厅，门在南侧，东窗通风；"
            "视觉陈设与标志物：木桌靠北，窗框内局部可见院子与天空；材质与工艺：夯土墙和哑光木梁；"
            "色彩体系：暖灰与木褐为主；光影：清晨东窗柔光，地面影子向西；"
            "氛围与情绪：安静朴素；视觉记忆点：窗下窄木台；美术控制：纯环境空镜，无人物、无动物，保持行动通道和清晰层次")


def prop_text(name="双鱼玉佩", variant="基础"):
    return (f"道具名称：{name}；别名：无；版本：{variant}；道具类别：信物佩饰；美学定位：温润协调；"
            "外形：长约五厘米，两条弧形鱼身首尾相接；纹样与工艺：细阴线刻鳞，边缘细磨；"
            "特征：顶部小穿孔系素绳；材质：青白玉与棉绳；色彩与光泽：青白柔光；"
            "使用状态：玉体完整，穿孔有轻微磨痕；美术控制：保持鱼身轮廓清楚，不添加原文未有的铭文")


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix=".asset-test-", dir=Path.cwd())
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "分镜.md"
        self.source.write_text(
            "## 第1集\n段落1｜总时长12秒\n**场景：** 刘家正厅 清晨 室内\n"
            "出场人物：阿月\n道具：双鱼玉佩、白瓷茶盏\n"
            "画面：姑娘端起白瓷茶盏，阿月站在东窗前，窗框内可见院子与天空。\n"
            "台词：阿月：双鱼玉佩是母亲留下的认亲信物。\n",
            encoding="utf-8",
        )
        self.data = {"schema_version": 2, "assets": {"role": [], "scene": [], "prop": []},
                     "requirements": []}
        specs = [("role", "阿月", role_text(), 4, ["姑娘"]),
                 ("scene", "刘家正厅", scene_text(), 3, []),
                 ("prop", "双鱼玉佩", prop_text(), 5, [])]
        for asset_type, name, desc, line, aliases in specs:
            asset_id = asset_type + "-001"
            self.data["assets"][asset_type].append({
                "id": asset_id, "entity_id": asset_id, "name": name, "aliases": aliases,
                "variant": "基础", "description": desc,
                "sources": [{"source": str(self.source), "line": line}],
            })
            if asset_type == "prop":
                self.data["assets"][asset_type][-1]["importance"] = {
                    "category": "身份信物", "reason": "原文明确双鱼玉佩是母亲留下的认亲信物",
                    "sources": [{"source": str(self.source), "line": 7}],
                }
            self.data["requirements"].append({
                "type": asset_type, "name": name, "source": str(self.source), "line": line,
                "status": "mapped", "asset_ids": [asset_id],
            })
        self.data["requirements"].append({
            "type": "role", "name": "姑娘", "source": str(self.source), "line": 6,
            "status": "mapped", "asset_ids": ["role-001"],
        })
        self.data["requirements"].append({
            "type": "prop", "name": "白瓷茶盏", "source": str(self.source), "line": 5,
            "status": "excluded", "reason": "普通饮具，仅作场景陈设或镜头交互，不独立建立特殊道具",
        })

    def report(self, data=None):
        return validate(self.data if data is None else data, [str(self.source)])

    def test_valid_names_alias_scar_single_material_no_hair_accessory(self):
        report = self.report()
        self.assertTrue(report.ok, report.errors)

    def test_source_scan_includes_full_interior_label_and_line(self):
        result = scan(self.source)
        self.assertEqual([r["name"] for r in result["requirements"]], ["刘家正厅", "阿月", "双鱼玉佩", "白瓷茶盏"])
        self.assertEqual(result["blocks"][0]["fields"][0]["space"], "室内")
        self.assertEqual(result["requirements"][0]["line"], 3)
        self.assertEqual(result["diagnostics"], [])

    def test_scene_name_with_hyphen_and_time_character_preserved(self):
        self.source.write_text("场景：夜晚酒馆-东厅｜夜｜内\n", encoding="utf-8")
        result = scan(self.source)
        self.assertEqual(result["requirements"][0]["name"], "夜晚酒馆-东厅")

    def test_table(self):
        self.source.write_text("| 镜号 | 场景 | 出场人物 | 道具 |\n| --- | --- | --- | --- |\n"
                               "| 1 | 正厅 日 内 | 阿月、掌柜 | 茶盏 |\n", encoding="utf-8")
        self.assertEqual([r["name"] for r in scan(self.source)["requirements"]],
                         ["正厅", "阿月", "掌柜", "茶盏"])

    def test_screenplay_numbered_scene_chinese_commas_and_period(self):
        self.source.write_text("### 场景二：老景家竹筏棚内，入夜前，内。\n"
                               "出场人物：丫丫、噬天凤（鸟形态）。\n", encoding="utf-8")
        result = scan(self.source)
        self.assertEqual([r["name"] for r in result["requirements"]],
                         ["老景家竹筏棚内", "丫丫", "噬天凤（鸟形态）"])
        self.assertEqual(result["blocks"][0]["fields"][0]["time"], "入夜前")
        self.assertEqual(result["diagnostics"], [])

    def test_parenthetical_commas_do_not_split_character(self):
        self.source.write_text("出场人物：阿月（画外音）、掌柜（圆脸，短须）\n", encoding="utf-8")
        self.assertEqual([r["name"] for r in scan(self.source)["requirements"]],
                         ["阿月", "掌柜（圆脸，短须）"])

    def test_combined_interior_exterior_not_in_scene_name(self):
        self.source.write_text("场景：宅院门内外 日内外\n镜1｜中景\n画面：阿月推门。\n", encoding="utf-8")
        result = scan(self.source)
        self.assertEqual(result["requirements"][0]["name"], "宅院门内外")
        self.assertTrue(result["diagnostics"])
        self.assertEqual(result["blocks"][1]["shot"], "镜1｜中景")

    def test_relative_time_and_space_transition_not_in_name(self):
        self.source.write_text("### 场景二：大丫家竹筏边，次日清晨，外转内。\n"
                               "### 场景三：张宅后厅，稍后，内。\n", encoding="utf-8")
        result = scan(self.source)
        self.assertEqual([r["name"] for r in result["requirements"]], ["大丫家竹筏边", "张宅后厅"])
        self.assertEqual(len(result["diagnostics"]), 2)

    def test_same_name_different_version(self):
        role = self.data["assets"]["role"][0]
        role["aliases"] = []
        role["description"] = role_text(aliases="无")
        self.data["requirements"] = [r for r in self.data["requirements"] if r["name"] != "姑娘"]
        second = copy.deepcopy(role)
        second.update(id="role-002", variant="嫁衣", description=role_text(aliases="无", variant="嫁衣"))
        second["sources"] = [{"source": str(self.source), "line": 6}]
        self.data["assets"]["role"].append(second)
        self.data["requirements"].append({"type": "role", "name": "阿月", "source": str(self.source),
                                         "line": 6, "status": "mapped", "asset_ids": ["role-002"]})
        self.assertTrue(self.report().ok, self.report().errors)

    def test_same_name_different_entities(self):
        role = self.data["assets"]["role"][0]
        role["aliases"] = []
        role["description"] = role_text(aliases="无")
        self.data["requirements"] = [r for r in self.data["requirements"] if r["name"] != "姑娘"]
        second = copy.deepcopy(role)
        second.update(id="role-002", entity_id="other-person")
        second["sources"] = [{"source": str(self.source), "line": 6}]
        self.data["assets"]["role"].append(second)
        self.data["requirements"].append({"type": "role", "name": "阿月", "source": str(self.source),
                                         "line": 6, "status": "mapped", "asset_ids": ["role-002"]})
        self.assertTrue(self.report().ok, self.report().errors)

    def test_two_versions_in_same_source_line_need_explicit_usage(self):
        role = self.data["assets"]["role"][0]
        second = copy.deepcopy(role)
        second.update(id="role-002", variant="嫁衣", description=role_text(variant="嫁衣"))
        second["sources"].append({"source": str(self.source), "line": 6})
        self.data["assets"]["role"].append(second)
        self.data["requirements"][0]["asset_ids"] = ["role-001", "role-002"]
        self.assertTrue(any("usage" in e for e in self.report().errors))
        self.data["requirements"][0]["usage"] = "此行在制作中明确需要两个造型版本，分别用于转场前后"
        self.assertTrue(self.report().ok, self.report().errors)

    def test_wrong_alias_or_renamed_asset_rejected(self):
        role = self.data["assets"]["role"][0]
        role["name"] = "清秀少女"
        role["description"] = role["description"].replace("【姓名】: 阿月", "【姓名】: 清秀少女")
        self.assertFalse(self.report().ok)
        self.assertTrue(any("精确命中" in e for e in self.report().errors))

    def test_invented_primary_name_with_real_alias_rejected(self):
        role = self.data["assets"]["role"][0]
        role["name"], role["aliases"] = "刘小姐", ["阿月", "姑娘"]
        role["description"] = role_text(name="刘小姐", aliases="阿月、姑娘")
        self.assertTrue(any("没有对应制作来源" in e for e in self.report().errors))

    def test_missing_explicit_requirement(self):
        self.data["requirements"] = [r for r in self.data["requirements"] if r["type"] != "prop"]
        self.assertTrue(any("制作字段未处理" in e for e in self.report().errors))

    def test_bad_reference_line(self):
        self.data["requirements"][0]["line"] = 2
        self.assertTrue(any("来源行" in e for e in self.report().errors))

    def test_novel_cannot_prove_production_need(self):
        novel = self.root / "小说.txt"
        novel.write_text("阿月和姑娘是同一人", encoding="utf-8")
        self.data["assets"]["role"][0]["sources"] = [{"source": str(novel), "line": 1}]
        self.assertTrue(any("非本轮制作来源" in e for e in self.report().errors))

    def test_pending_and_unreasoned_exclusion_rejected(self):
        self.data["requirements"][0]["status"] = "pending"
        self.assertFalse(self.report().ok)
        self.data["requirements"][0]["status"] = "excluded"
        self.assertTrue(any("必须说明理由" in e for e in self.report().errors))

    def test_duplicate_id_and_entity_version_rejected(self):
        self.data["assets"]["role"].append(copy.deepcopy(self.data["assets"]["role"][0]))
        report = self.report()
        self.assertTrue(any("重复资产 ID" in e for e in report.errors))
        self.assertTrue(any("同实体同版本" in e for e in report.errors))

    def test_wrong_top_type_cleanly_reported(self):
        self.data["assets"]["role"] = []
        self.assertFalse(self.report().ok)
        self.data["assets"]["role"] = {}
        self.assertFalse(self.report().ok)
        self.assertFalse(validate({"role": [], "scene": {}, "prop": {}}).ok)

    def test_duplicate_json_keys_rejected(self):
        with patch("sys.stdin", io.StringIO('{"prop":{"玉佩":"一","玉佩":"二"}}')):
            with self.assertRaisesRegex(ValueError, "重复"):
                load_data("-")

    def test_missing_prop_fields_rejected(self):
        self.data["assets"]["prop"][0]["description"] = "白瓷茶盏，白色"
        self.assertFalse(self.report().ok)

    def test_style_and_placeholder_all_types(self):
        for asset_type in ("role", "scene", "prop"):
            for bad in ("PBR", "未设定"):
                with self.subTest(asset_type=asset_type, bad=bad):
                    data = copy.deepcopy(self.data)
                    data["assets"][asset_type][0]["description"] += bad
                    self.assertFalse(self.report(data).ok)

    def test_style_labels_excluded_but_physical_texture_and_taoist_title_allowed(self):
        for banned in ("真人画风", "真人实拍", "写实风格", "动漫风格", "照片级",
                       "3D", "CG质感", "国漫", "二次元", "油画风", "photorealistic"):
            data = copy.deepcopy(self.data)
            data["assets"]["role"][0]["description"] += "，" + banned
            self.assertFalse(self.report(data).ok, banned)
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("阿月", "玄清真人"),
                               encoding="utf-8")
        data = copy.deepcopy(self.data)
        data["assets"]["role"][0]["name"] = "玄清真人"
        data["assets"]["role"][0]["description"] = role_text(name="玄清真人")
        data["requirements"][0]["name"] = "玄清真人"
        self.assertTrue(self.report(data).ok, self.report(data).errors)

    def test_material_checks_cannot_be_bypassed_by_punctuation(self):
        desc = self.data["assets"]["role"][0]["description"]
        self.data["assets"]["role"][0]["description"] = desc.replace("；", "，").replace(
            "无发饰，发束自然收拢", "蓝带").replace(
            "内外层均为棉布，平纹哑光，领袖细密锁边，灰蓝外层与米白内层协调", "长衫")
        report = self.report()
        self.assertTrue(any("发饰缺少具体材质" in e for e in report.errors))
        self.assertTrue(any("衣着缺少具体材质" in e for e in report.errors))

    def test_invalid_time_tier_and_actual_period(self):
        for bad in ("上午", "白天（深夜）"):
            data = copy.deepcopy(self.data)
            data["assets"]["scene"][0]["description"] = scene_text(time=bad)
            self.assertFalse(self.report(data).ok)

    def test_window_view_and_empty_room_not_banned(self):
        self.assertTrue(self.report().ok, self.report().errors)

    def test_scene_rejects_characters_background_figures_animals(self):
        for presence in ("阿月坐在窗下", "窗边的阿月", "门口站着侍卫", "远处有模糊人群", "窗外出现人影",
                         "墙上挂着人物画像", "地面映出人物倒影", "阴影里浮现人脸", "窗台卧着一只猫", "天空有飞鸟"):
            with self.subTest(presence=presence):
                data = copy.deepcopy(self.data)
                data["assets"]["scene"][0]["description"] = scene_text().replace(
                    "窗下窄木台；美术控制", "窗下窄木台，" + presence + "；美术控制")
                report = self.report(data)
                self.assertTrue(any("角色" in error or "动物" in error for error in report.errors), report.errors)

    def test_scene_requires_explicit_empty_environment_control(self):
        self.data["assets"]["scene"][0]["description"] = scene_text().replace("纯环境空镜，无人物、无动物，", "")
        self.assertTrue(any("无人物、无动物" in e for e in self.report().errors))

    def test_architectural_human_character_and_owner_name_are_not_actors(self):
        self.data["assets"]["scene"][0]["description"] = scene_text().replace(
            "木桌靠北", "人字梁位于顶面，阿月的木桌靠北")
        self.assertTrue(self.report().ok, self.report().errors)

    def test_special_prop_requires_reason_category_and_real_evidence(self):
        for bad in (None, {}, {"category": "普通用品", "reason": "端起过", "sources": []},
                    {"category": "身份信物", "reason": "", "sources": [{"source": str(self.source), "line": 7}]}):
            data = copy.deepcopy(self.data)
            data["assets"]["prop"][0]["importance"] = bad
            self.assertTrue(any("importance" in e for e in self.report(data).errors))

    def test_prop_importance_rejects_invalid_evidence(self):
        for line in (2, 999):
            data = copy.deepcopy(self.data)
            data["assets"]["prop"][0]["importance"]["sources"][0]["line"] = line
            self.assertFalse(self.report(data).ok)

    def test_prop_importance_allows_linked_multiline_evidence(self):
        self.source.write_text(self.source.read_text(encoding="utf-8") +
                               "台词：这就是母亲留下的认亲信物。\n", encoding="utf-8")
        self.data["assets"]["prop"][0]["importance"]["sources"] = [
            {"source": str(self.source), "line": 5}, {"source": str(self.source), "line": 8}]
        self.assertTrue(self.report().ok, self.report().errors)

    def test_ordinary_prop_interaction_does_not_require_prop_asset(self):
        self.data["assets"]["prop"] = []
        for req in self.data["requirements"]:
            if req["type"] == "prop":
                req.update(status="excluded", reason="本次仅核对角色与环境，普通物件归入环境陈设")
                req.pop("asset_ids", None)
        self.source.write_text(self.source.read_text(encoding="utf-8").replace(
            "双鱼玉佩、白瓷茶盏", "白瓷茶盏").replace(
            "台词：阿月：双鱼玉佩是母亲留下的认亲信物。\n", ""), encoding="utf-8")
        self.data["requirements"] = [r for r in self.data["requirements"] if r["name"] != "双鱼玉佩"]
        self.assertTrue(self.report().ok, self.report().errors)
        output = self.root / "没有特殊道具"
        export_txt(self.data, output, [str(self.source)])
        self.assertFalse((output / "道具资产").exists())

    def test_ordinary_shaped_object_can_be_special_with_explicit_plot_role(self):
        prop = self.data["assets"]["prop"][0]
        prop["name"] = "白瓷茶盏"
        prop["description"] = (
            "道具名称：白瓷茶盏；别名：无；版本：基础；道具类别：涉案饮器；美学定位：素净温润；"
            "外形：薄口浅腹，小圈足；纹样与工艺：素面无纹样，口沿细磨；"
            "特征：内壁局部残留浅褐沉积；材质：细密白瓷；色彩与光泽：温白柔光；"
            "使用状态：器身完整，内底保留原文所述残迹；美术控制：保留关键残迹，不添加新铭文")
        prop["importance"] = {"category": "关键证据", "reason": "原文明说它留有毒物残迹，是毒案证据",
                              "sources": [{"source": str(self.source), "line": 7}]}
        self.source.write_text(self.source.read_text(encoding="utf-8").replace("双鱼玉佩", "白瓷茶盏").replace(
            "白瓷茶盏、白瓷茶盏", "白瓷茶盏").replace("是母亲留下的认亲信物", "留有毒物残迹，是毒案证据"), encoding="utf-8")
        self.data["requirements"] = [r for r in self.data["requirements"] if r["name"] not in ("白瓷茶盏", "双鱼玉佩")]
        self.data["requirements"].append({"type": "prop", "name": "白瓷茶盏", "source": str(self.source),
                                         "line": 5, "status": "mapped", "asset_ids": ["prop-001"]})
        self.assertTrue(self.report().ok, self.report().errors)

    def test_legacy_prop_cannot_bypass_special_prop_evidence(self):
        report = validate({"role": {}, "scene": {}, "prop": {"双鱼玉佩": prop_text()}})
        self.assertTrue(any("importance" in e for e in report.errors))

    def test_voice_only_system_no_mascot_required(self):
        self.source.write_text("出场人物：系统\n声音：系统发出提示音。\n", encoding="utf-8")
        desc = "\n".join([
            "【姓名】: 系统", "【别名】: 无", "【颜值定位】: 造型版本：声音；无可见形体",
            "【人设描述】: 面部特征：不具可见面部；发型：不具毛发；发饰：无发饰；"
            "身材比例：不具可见形体；衣着：无衣着；气质：冷静清晰",
            "【声线类型】: 电子音",
        ])
        data = {"schema_version": 2, "assets": {"role": [{
            "id": "system", "entity_id": "system", "name": "系统", "aliases": [],
            "variant": "声音", "kind": "voice", "description": desc,
            "sources": [{"source": str(self.source), "line": 1}],
        }], "scene": [], "prop": []}, "requirements": [{
            "type": "role", "name": "系统", "source": str(self.source), "line": 1,
            "status": "mapped", "asset_ids": ["system"],
        }]}
        self.assertTrue(self.report(data).ok, self.report(data).errors)

    def test_export_txt_exact_roundtrip_no_json(self):
        output = self.root / "交付"
        report, written = export_txt(self.data, output, [str(self.source)])
        self.assertTrue(report.ok)
        self.assertEqual(sum(n for _, n in written), 3)
        files = list(output.rglob("*.*"))
        self.assertEqual(len(files), 3)
        self.assertTrue(all(f.suffix == ".txt" for f in files))
        self.assertEqual((output / "角色资产" / "角色资产.txt").read_text(encoding="utf-8"),
                         role_text() + "\n")

    def test_export_multi_asset_separator_and_empty_types(self):
        role = self.data["assets"]["role"][0]
        role["aliases"] = []
        role["description"] = role_text(aliases="无")
        self.data["requirements"] = [r for r in self.data["requirements"] if r["name"] != "姑娘"]
        second = copy.deepcopy(role)
        second.update(id="role-002", variant="嫁衣", description=role_text(aliases="无", variant="嫁衣"))
        second["sources"] = [{"source": str(self.source), "line": 6}]
        self.data["assets"]["role"].append(second)
        self.data["requirements"].append({"type": "role", "name": "阿月", "source": str(self.source),
                                         "line": 6, "status": "mapped", "asset_ids": ["role-002"]})
        self.data["assets"]["scene"] = []
        self.data["assets"]["prop"] = []
        for req in self.data["requirements"]:
            if req["type"] != "role":
                req.update(status="excluded", reason="测试中仅交付已指定的角色资产")
                req.pop("asset_ids", None)
        output = self.root / "角色交付"
        export_txt(self.data, output, [str(self.source)])
        text = (output / "角色资产" / "角色资产.txt").read_text(encoding="utf-8")
        self.assertEqual(len(text.rstrip("\n").split("\n@\n")), 2)
        self.assertFalse((output / "场景资产").exists())
        self.assertFalse((output / "道具资产").exists())
        self.assertFalse(text.startswith("@"))
        self.assertFalse(text.rstrip().endswith("@"))

    def test_export_preserves_old_directory_and_rejects_invalid_before_writes(self):
        output = self.root / "旧交付"
        output.mkdir()
        old = output / "旧资产.txt"
        old.write_text("保留", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "非空"):
            export_txt(self.data, output, [str(self.source)])
        self.assertEqual(old.read_text(encoding="utf-8"), "保留")
        self.data["assets"]["prop"][0]["description"] = ""
        target = self.root / "不应生成"
        with self.assertRaises(ValueError):
            export_txt(self.data, target, [str(self.source)])
        self.assertFalse(target.exists())

    def test_at_separator_in_asset_rejected(self):
        self.data["assets"]["prop"][0]["description"] += "\n@\n"
        self.assertFalse(self.report().ok)

    def test_documented_full_visual_examples_validate_without_warnings(self):
        reference = (SCRIPTS.parent / "references" / "05-examples.md").read_text(encoding="utf-8")
        for asset_type, heading in (("role", "角色示例"), ("scene", "场景示例"), ("prop", "道具示例")):
            description = re.search(r"### " + heading + r"\s+```text\n(.*?)\n```", reference, re.S).group(1)
            self.data["assets"][asset_type][0]["description"] = description
        self.data["assets"]["scene"][0]["variant"] = "清晨"
        report = self.report()
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.warnings, [])

    def test_cli_stdin_success_and_failure(self):
        command = [sys.executable, "-B", str(SCRIPTS / "check_assets.py"), "-", "--source", str(self.source)]
        result = subprocess.run(command, input=json.dumps(self.data, ensure_ascii=False),
                                encoding="utf-8", capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run(command, input='{"schema_version":2,"assets":null}',
                                encoding="utf-8", capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
