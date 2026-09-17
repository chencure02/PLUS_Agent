# PLUS 模块参考

本参考与当前项目 `agent/tools/` 中的封装保持一致。构造 tmp 文件、选择 bat 文件或定位输出时使用本文件。

## 后端通用约定

所有依赖 bat 的模块均遵循以下过程：定位本地 `plus-backend` 目录；确认完整路径仅包含 ASCII 字符；将精确的 tmp 内容写入 `plus-backend`；以该目录为工作目录执行匹配的 bat 文件；捕获 stdout/stderr 并设置超时；检查预期输出。若原始工具将结果从共享后端目录移到调用方输出目录，后续封装也必须在下一项任务开始前完成该操作。

当前项目通过锁串行运行任务，因为 PLUS 使用共享 tmp 文件和共享输出位置。

完整的未来土地利用模拟优先采用：

`convert -> expansion -> leas -> markov -> neighborhood_weight -> cars -> validation`

`linear` 可作为替代性的需求预测工具，`diverse` 用于比较或整合多个模拟结果。

## convert

- 工具：`agent/tools/convert.py`；tmp：`PLUS_Convert.tmp`；bat：`convert.bat`。
- 用途：将 LULC 或约束栅格转换为 PLUS 兼容的无符号字符格式。
- 参数：`input_paths` 为输入栅格绝对路径；`output_paths` 为输出栅格绝对路径，二者数量必须一致。
- 预期结果：即传入的每个 `output_paths` 路径。
- 注意：源栅格不是无符号字符格式时，应先执行此模块；LULC 编码应从 1 开始且保持连续。

```text
<Input number>
N
<Input LULC series>
input_path_1
input_path_2
...
<Output LULC series>
output_path_1
output_path_2
...
```

## expansion

- 工具：`agent/tools/expansion.py`；tmp：`PLUS_Expansion.tmp`；bat：`expansion.bat`。
- 用途：从早期和晚期 LULC 栅格提取土地利用扩张/变化。
- 参数：`early_lulc`、`late_lulc` 和 `output_change`。
- 预期结果：PLUS 通常将 `output_change.tif` 重命名为 `<basename>_landuse_1to2.tif`。
- 注意：该结果通常同时供 `leas` 和 `neighborhood_weight` 使用。

```text
<Input number>
2
<Input LULC series>
early_lulc
late_lulc
<Output change>
output_change
```

## leas

- 工具：`agent/tools/leas.py`；tmp：`PLUS_LEAS.tmp`；bat：`leas.bat`。
- 用途：土地利用扩张分析策略（LEAS）。以扩张图和驱动因子训练随机森林，生成各类别出现概率和因子贡献表。
- 参数：`input_lulc` 为扩张图；`feature_folder` 为驱动因子栅格目录；`output_probability` 为概率输出基础名。PLUS 会生成 `<basename>_band_*.tif`。
- 可选参数默认值：`sampling_rate=0.01`、`m_try=16`、`n_trees=20`、`thread_count=8`。
- 预期结果：调用方输出目录中的概率波段，以及从 `plus-backend` 移出的 `accuracy_record_rf.txt`、`imageminmax.txt` 和 `Contribution*.csv`。
- 注意：全部驱动因子栅格应与扩张图对齐；行列数、范围或投影不一致可能导致 LEAS 失败。

```text
<Input LULC>
input_lulc
<Input Featrue folder>
feature_folder
<Output probability>
output_probability
<Is net exit?>
0
<Input sampling rate>
sampling_rate
<mTry>
m_try
<Input the number of trees>
n_trees
<Is balance?>
0
<Input thread count>
thread_count
<High precision>
0
<Update Number>
0
<Update Variable>
0
```

## markov

- 工具：`agent/tools/markov.py`；tmp：`PLUS_Markov.tmp`；bat：`markov.bat`。
- 用途：由起止期土地利用图及年份预测未来土地利用需求。
- 参数：`start_map`、`end_map`、`start_year`、`end_year`、`predict_year`、`output_dir`。
- 预期结果：PLUS 原始结果为 `plus-backend/cpp/output/markov.csv`，当前封装将其移至 `<output_dir>/markov.csv`。
- 需求量提取：读取 `markov.csv` 的 `[Predict amount]` 段，找首列等于 `predict_year` 的行，并格式化为供 CARS 使用的 `1,demand_c1,demand_c2,...`。

```text
<StartMap>
start_map
<EndMap>
end_map
<Start Year>
start_year
<End Year>
end_year
<Predict Year>
predict_year
```

## neighborhood_weight（本地 GIS 辅助工具）

- 项目工具：`agent/tools/neighborhood_weight.py`；交付 Skill 脚本：`scripts/neighborhood_weight.py`；无 tmp 文件和 bat 文件。
- 用途：从扩张栅格计算 CARS 邻域权重。
- 依赖：Python、NumPy、GDAL/OSGeo；不依赖 `plus-backend`、`cpp/PLUS.exe` 或任何 `*.bat` 文件。
- 参数：`expansion_raster`、`num_classes`；可选 `background_values`，默认 `0,255`。
- 逻辑：使用 GDAL 打开扩张栅格，统计排除背景值后的有效像元；对 `1..num_classes` 的每类，返回其像元数除以全部有效扩张像元数的比例。
- 输出格式：供 CARS 使用的逗号分隔权重，例如 `0.100000,0.200000,0.700000`。

命令行调用示例：

```powershell
python scripts\neighborhood_weight.py `
  --expansion-raster "C:\data\expansion.tif" `
  --num-classes 3
```

## cars

- 工具：`agent/tools/cars.py`；tmp：`PLUS_CARS.tmp`；bat：`cars.bat`。
- 用途：基于 LEAS 概率、Markov 需求、邻域权重、转移规则和可选策略约束，执行 CA 斑块生成模拟。
- 参数：`input_classes`、`input_lulc`、`probability_paths`（每个类别一个概率波段）、`output_simulation`、`neighborhood_weights`、`transition_matrix`、`yearly_demands`。
- `transition_matrix` 的 API 输入以分号分隔行，写入 tmp 时改为换行；`yearly_demands` 必须是 Markov 的 `1,demand_c1,demand_c2,...` 格式。
- 可选参数默认值：`policy_path` 为空、`neighborhood=3`、`thread_count=8`、`patch_generation=0.2`、`expansion_coefficient=0.2`、`seed_percentage=0.1`。
- 预期结果：PLUS 通常在 `output_simulation` 同级目录生成 `<basename>Simulation_*.tif`。
- 注意：当前封装中 `<How many years>` 固定为 `1`。

```text
<Input classes>
input_classes
<Input LULC>
input_lulc
<Input Probability Folder>
probability_path_1
probability_path_2
...
<Output simulation>
output_simulation
<Input Policy>
policy_path
<Input Neighborhood>
neighborhood
<How many years>
1
<Input thread count>
thread_count
<Patch generation>
patch_generation
<Expansion coefficient>
expansion_coefficient
<Neighborhood Weight>
neighborhood_weights
<Transition matrix>
matrix_row_1
matrix_row_2
...
<Years and corresponding demands>
yearly_demands
<Percentage of seeds>
seed_percentage
<Development type exist>
0
<Development type>
0
<Development weight>
0.5
```

## validation

- 工具：`agent/tools/validation.py`；tmp：`PLUS_Validation.tmp`；bat：`validate.bat`。
- 用途：比较模拟与真实 LULC 栅格，输出 Kappa 或 FoM 统计值。
- 参数：`simulated_map`、`real_map`、`start_map`；可选 `is_fom=0`、`sampling_rate=0.1`、`output_dir`（默认模拟图所在目录）。
- `is_fom=0` 计算 Kappa，`is_fom=1` 计算 FoM。
- 预期结果：`Kappa.csv` 或 `FoM.csv`，由当前封装从 `plus-backend` 移到 `output_dir`。

```text
<IsFom>
is_fom
<Sampling rate>
sampling_rate
<Simulated Map>
simulated_map
<Real Map>
real_map
<Start Map>
start_map
```

## linear

- 工具：`agent/tools/linear.py`；tmp：`PLUS_Linear.tmp`；bat：`linear.bat`。
- 用途：以多期历史土地利用图进行线性回归，预测未来需求。
- 参数：`predict_amount` 为需预测的年份数量；`image_paths` 为按时间顺序排列的历史 LULC 栅格。
- 预期结果：当前工具将标准输出作为结果信息，不收集结果文件。

```text
<Image Amount>
image_amount
<Predict Amount>
predict_amount
<Images Path>
image_path_1
image_path_2
...
```

## diverse

- 工具：`agent/tools/diverse.py`；tmp：`PLUS_Diverse.tmp`；bat：`diverse.bat`。
- 用途：整合或比较多幅模拟栅格，生成情景多样性结果。
- 参数：`image_paths` 为模拟结果栅格；`output_path` 为输出多样性图。
- 预期结果：`output_path`。

```text
<Image Amount>
image_amount
<Images Path>
image_path_1
image_path_2
...
<Output Path>
output_path
```
