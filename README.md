# shot-parser

**版本：2.0.2** · 分镜与剧本资产解析技能

从分镜或剧本提取角色、场景、道具，结合小说补充设定，撰写可直接用作文生图提示词的精细美术描述。资产名称与制作分镜逐项对应，描述不含真人、动漫、3D 等画风标签或渲染参数。

本仓库由 **ikun1946** 维护。公开供所有人查看、克隆和拉取；不向其他账号授予原仓库的直接写入权限。

## 功能

- 以制作分镜确定实际需求与调用名称，剧本、小说辅助稳定外貌和世界观。
- 场景只生成纯环境空镜，无人物、动物、群像、背影或角色倒影。
- 只独立解析信物、关键证据、特殊法器等重要剧情道具；普通茶盏、桌椅、工具等归入陈设或服饰。
- 用原文主名、明确别名、实体与版本区分同名人物、换装、成长、形态变化及道具状态。
- 详细描述五官骨相、发型、比例、衣着层次、材质工艺，以及空间、陈设、配色与光线。
- 在保留原文关键特征的前提下提升造型协调、辨识度与美术完成度。
- 默认同时交付完整 UTF-8 JSON 和三类 TXT，JSON 保留来源、实体、版本、需求映射及排除记录，TXT 同类资产之间以单独一行 `@` 分隔。

## 安装

这是 Agent Skill，不是独立生图程序。将本仓库放入支持 `SKILL.md` 的工具的技能目录。

Codex 的 Windows 安装示例：

```powershell
git clone https://github.com/ikun1946/shot-parser.git "$env:USERPROFILE\.codex\skills\shot-parser"
```

目标目录已有旧版时，先备份旧目录或选择新的空目录，避免覆盖自定义修改。

安装固定版本：

```powershell
git clone --branch v2.0.2 --depth 1 https://github.com/ikun1946/shot-parser.git "$env:USERPROFILE\.codex\skills\shot-parser"
```

## 使用

向支持本技能的助手提供制作分镜，并按需附上剧本或小说：

```text
使用 $shot-parser 解析这些分镜的角色、场景、道具。
资产名称要与分镜逐项对应，结合所附小说补充稳定外貌设定。
描述精细到可直接用于文生图，不加入任何画风标签，交付完整 JSON 和三类 TXT。
```

角色的 `【人设描述】` 为完整六项视觉描述，可以直接用于文生图；声线、别名和造型版本作为调度信息另列。场景和道具使用其完整视觉字段。

默认输出：

```text
项目名_资产_YYYYMMDD/
├── 资产.json
├── 角色资产/角色资产.txt
├── 场景资产/场景资产.txt
└── 道具资产/道具资产.txt
```

无需另行索取 JSON。`资产.json` 使用三类数组保留同名不同实体及版本，包含完整描述、来源、需求映射、道具重要性依据与普通物件排除理由，并与 TXT 逐条核对。没有资产的类型在 JSON 中保留空数组，但不生成对应 TXT 文件夹。完整规则见 [SKILL.md](SKILL.md)，精细描述示例见 [美术示例](references/05-examples.md)。

## 脚本与验证

使用 Python 3.10 或更高版本；脚本和行为测试仅使用 Python 标准库。

```powershell
python -B scripts/parse_storyboard.py "分镜.md"
python -B -m unittest discover -s tests -v
```

校验与导出支持从标准输入接收完整数据；导出仍默认生成 JSON 和 TXT：

```text
python -B scripts/check_assets.py - --source "分镜.md"
python -B scripts/to_txt.py - "本次资产交付目录" --source "分镜.md"
python -B scripts/check_assets.py "本次资产交付目录/资产.json" --source "分镜.md"
```

只有用户明确要求仅 TXT 或不保存 JSON 时，才追加 `--txt-only`，或调用 `export_txt(..., include_json=False)`。数据契约及调用方式见 [命名与输出规范](references/03-reuse-and-output.md)。扫描器只定位显式字段，画面、动作和对白中的资产仍需通读补查；自动校验不替代来源忠实度和美术质量复核。

## 版本

`VERSION`、`SKILL.md` 的 `metadata.version` 与 Git 标签保持一致。本次版本为 `2.0.2`，标签为 `v2.0.2`。版本记录见 [CHANGELOG.md](CHANGELOG.md)。

通过 Git 克隆且没有本地修改时，可以在仓库目录运行 `git pull --ff-only` 拉取更新；固定标签安装的副本需主动选择新的版本标签。
