# 使用方法

此文件夹是独立的 Agent Skill，不会修改或替换当前 PLUS Agent 应用。

## Skill 位置与内容

当前位置：

```text
PLUS_Agent/agent_skills/plus-model-tools
```

主要文件：

- `SKILL.md`：Skill 入口和模块路由规则。
- `references/module-reference.md`：全部 PLUS 模块的 tmp 标签、bat 文件、参数、输出与工作流说明。
- `scripts/plus_runner.py`：可复用的 tmp 读写与 bat 执行封装。

## 方式一：在本项目中作为本地参考使用

请 Agent 调用 PLUS 后端时，可明确指定此目录：

```text
使用 PLUS_Agent/agent_skills/plus-model-tools 中的 Skill，执行或修改 PLUS 模块调用。
```

Agent 应先读取 `SKILL.md`，再只打开所请求模块对应的参考内容。

## 方式二：作为 Codex 项目级 Skill 使用

将该 Skill 放入项目根目录的 `.agents/skills/plus-model-tools`。Codex 打开该项目时会自动发现此路径中的 Skill：

```powershell
Copy-Item -Recurse `
  "C:\GIS\PLUS_Agent\agent_skills\plus-model-tools" `
  ".agents\skills\plus-model-tools"
```

重新打开项目或刷新 Skills 后，可显式调用：

```text
$plus-model-tools 帮我运行 PLUS convert，把 A.tif 转成 A_uc.tif
```

对于 PLUS 模型模块执行类请求，系统也可自动选中该 Skill。若希望安装为个人全局 Skill，则使用 `$env:USERPROFILE\.agents\skills\plus-model-tools`。

## 运行 Convert 示例

在项目根目录中执行：

```powershell
cd "C:\GIS\PLUS_Agent"
python agent_skills\plus-model-tools\scripts\plus_runner.py `
  --plus-backend plus-backend `
  show-convert-tmp `
  --input-path "C:\ascii_path\input_2003.tif" `
  --output-path "C:\ascii_path\input_2003_uc.tif"
```

该命令仅输出 tmp 文件内容，不会运行 PLUS。

要实际运行 PLUS Convert：

```powershell
python agent_skills\plus-model-tools\scripts\plus_runner.py `
  --plus-backend plus-backend `
  convert `
  --input-path "C:\ascii_path\input_2003.tif" `
  --output-path "C:\ascii_path\input_2003_uc.tif"
```

处理多幅栅格时，按一一对应的顺序重复传入 `--input-path` 和 `--output-path`。

## 运行环境要求

- 随附的 `*.bat` 文件需在 Windows 中运行。
- `plus-backend` 以及所有输入/输出路径应只包含 ASCII 字符。
- 不要同时运行两项 PLUS bat 任务。
- 实际模型任务必须使用绝对路径。
- 使用 `neighborhood_weight` 或栅格验证辅助函数前，需安装 GDAL/OSGeo。

## 扩展模块命令行

如需为更多模块补充 CLI 子命令，可在 `scripts/plus_runner.py` 中复用已有构造函数：

- `build_expansion_tmp`
- `build_leas_tmp`
- `build_markov_tmp`
- `build_cars_tmp`
- `build_validation_tmp`
- `build_linear_tmp`
- `build_diverse_tmp`

应保持 `SKILL.md` 简短，将模块细节留在 `references/module-reference.md`，这样后续 Agent 只会加载当前任务所需的信息。
