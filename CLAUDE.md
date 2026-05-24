# PLUS Agent

基于 PLUS 模型（Patch-generating Land Use Simulation）的土地利用模拟平台。运行包位于 `plus-backend/`，包含 PLUS 核心可执行文件（C++）、各模块批处理脚本（.bat）和参数配置模板（.tmp）。

## 目录结构

```
plus-backend/
├── cpp/                    # PLUS C++ 核心程序及依赖 DLL（GDAL, HDF5, GEOS, PROJ 等）
│   ├── PLUS.exe            # 主程序入口
│   └── output/             # 部分模块默认输出目录
├── *.bat                   # 各模块运行脚本（共8个）
├── PLUS_*.tmp              # 各模块参数模板（与 bat 一一对应）
├── src/                    # Spring Boot 后端服务（Java）
├── imageminmax.txt         # LEAS 模块运行记录
└── accuracy_record_rf.txt  # LEAS 随机森林精度记录
```

## 运行方式

所有模块的运行都需要先配置对应的参数文件（tmp文件）中的参数，参数文件中的有关路径的参数均以绝对路径的方式写入，再运行其对应的批处理脚本（bat文件）

```

每个 `.bat` 文件就是模块功能的快捷封装，双击或在终端中执行 bat 即可运行对应模块，并且可以在终端中看到相应的运行信息。

---

## 模块说明

### 1. Convert — LULC 重分类/转换

**功能**：对 LULC 系列栅格进行重分类编码转换，转换成PLUS模型能够处理的格式，这是执行PLUS模型其他模块前所必须的工作。

**批处理脚本**：`convert.bat`

**参数文件** `PLUS_Convert.tmp`：

| 参数 | 说明 |
|------|------|
| `Input number` | 输入栅格文件的数量 n|
| `Input LULC series` | 输入 LULC 栅格文件路径列表，列表行数等于n 。|
| `Output LULC series` | 输出（重分类后）栅格文件路径列表，列表行数等于n|

**批处理脚本运行后的产物**：
- n张栅格数据图，与输出（重分类后）栅格文件路径列表一致

---

### 2. Expansion — 用地扩张提取

**功能**：基于两期 LULC 数据提取用地变化区域（扩张/收缩图）。

**批处理脚本** `expansion.bat`

**参数文件** `PLUS_Expansion.tmp`：
| 参数 | 说明 |
|------|------|
| `Input number` | 输入的 LULC 图数量（通常为 2） |
| `Input LULC series` | 两期 LULC 栅格路径（第一期、第二期）|
| `Output change` | 输出变化图的路径 |

**批处理脚本运行后的产物**：
- 1张土地扩张图，但是批处理脚本运行后会改变输出文件的命名，在原有命名的基础上加上后缀_landuse_1to2。例如当参数文件中写定的结果输出文件路径为：C:\Users\10421\Desktop\testdata\t1\expansion.tif，批处理脚本运行完毕后将在t1文件夹内输出1个命名为expansion_landuse_1to2.tif的概率图。
---

### 3. LEAS — 用地扩张分析策略（Land Expansion Analysis Strategy）

**功能**：提取两期 LULC 之间的用地扩张区域，结合驱动因子通过随机森林（Random Forest）模型计算各用地类型的发生概率。

**批处理脚本** `leas.bat`

**参数文件** `PLUS_LEAS.tmp`：
| 参数 | 说明 |
|------|------|
| `Input LULC` | 用地扩张提取结果图,一般采用`expansion`模块的输出 |
| `Input Featrue folder` | 驱动因子文件夹路径 |
| `Output probability` | 输出的概率图文件路径（多波段，每波段对应一种用地类型的发生概率） |
| `Is net exit?` | 是否计算净变化（0=总变化, 1=净变化），默认为0，该参数任何时候都不做改动 |
| `Input sampling rate` | 随机森林采样率（默认 0.01 = 1%） |
| `mTry` | 随机森林每棵树的特征采样数（默认 16） |
| `Input the number of trees` | 随机森林决策树数量 |
| `Is balance?` | 是否对样本进行平衡处理（0=不平衡），默认为0，该参数任何时候都不做改动 |
| `Input thread count` | 并行线程数，默认为8 |
| `High precision` | 是否高精度模式（0=否） ，默认为0，该参数任何时候都不做改动|
| `Update Number` | 更新迭代次数 ，默认为0，该参数任何时候都不做改动|
| `Update Variable` | 是否更新变量（0=否），默认为0，该参数任何时候都不做改动 |

**批处理脚本运行后的产物**：
- n张概率图，n代表所运行的数据有n种土地利用类型。例如当写定输出的概率图文件路径为：C:\Users\10421\Desktop\testdata\t1\potential.tif，此时将在t1文件夹内输出n个命名为potential_band_n.tif的概率图
- `accuracy_record_rf.txt` — 各用地类型的 RF 精度
- `imageminmax.txt` — 驱动因子归一化范围记录

---

### 4. Markov — 马尔科夫链预测

**功能**：基于两期 LULC 数据构建土地利用转移概率矩阵，通过马尔科夫链预测未来各地类需求量。

**批处理脚本** `markov.bat`

**参数文件** `PLUS_Markov.tmp`：

| 参数 | 说明 |
|------|------|
| `StartMap` | 起始年份 LULC 栅格文件路径 |
| `EndMap` | 终止年份 LULC 栅格文件路径 |
| `Start Year` | 起始年份 |
| `End Year` | 终止年份 |
| `Predict Year` | 预测目标年份 |

**批处理脚本运行后的产物**：
`cpp/output/markov.csv` — 记录预测得到的目标年份各用地类型需求量（一般为表格的最后一行）以及其他信息。

---

### 5. Linear — 线性预测

**功能**：基于多期历史 LULC 数据，用线性回归预测未来 LULC 分布。

**批处理脚本** `linear.bat`

**参数文件** `PLUS_Linear.tmp`：

| 参数 | 说明 |
|------|------|
| `Image Amount` | 历史 LULC 图数量 |
| `Predict Amount` | 预测的年份数 |
| `Images Path` | 历史 LULC 栅格文件路径列表 |

**批处理脚本运行后的产物**：
无直接产物，批处理脚本运行后在cmd中会直接输出信息
---

### 6. CARS — 基于 CA 的斑块生成模拟（CA-based Patch Generation）

**功能**：核心模拟模块。结合 LEAS 概率图、Markov/Linear 需求量、转换规则和约束条件，通过元胞自动机 + 自适应斑块生成机制模拟未来土地利用格局。

**批处理脚本** `cars.bat`

**参数文件** `PLUS_CARS.tmp`：

| 参数 | 说明 |
|------|------|
| `Input classes` | 土地利用类型数量，可以由LEAS模块输出的概率图数量得出 |
| `Input LULC` | 起始年份 LULC 栅格文件路径 ，一般为Expansion模块的中输入的第一期土地利用数据|
| `Input Probability Folder` | LEAS 输出的各类型概率图文件路径列表（每个波段或文件对应一种地类） |
| `Output simulation` | 结果的输出路径 |
| `Input Policy` | 限制性约束图的路径（如水域保护范围，范围内不发生转换），该参数为非必要参数，可以为空 |
| `Input Neighborhood` | 邻域窗口大小（默认 3，即 3×3） |
| `How many years` | 模拟年数，该参数默认为1，并且任何时候都不做改动 |
| `Input thread count` | 并行线程数，默认为8 |
| `Patch generation` | 斑块生成阈值（0~1，控制新斑块生成强度），默认为0.2 |
| `Expansion coefficient` | 扩张系数（控制随机斑块种子的扩散程度，0~1） ，默认为0.2|
| `Neighborhood Weight` | 各用地类型的邻域权重（逗号分隔，数量=用地类型数）， |
| `Transition matrix` | 转换矩阵（n×n的矩阵，n为土地利用类型数量，1=允许转换，0=禁止转换），默认全为1， |
| `Years and corresponding demands` | 逐年需求量（格式：1,地类1需求量,地类2需求量,...），第一个数字默认为1且任何时候不做改动，后面的用地需求量一般由Markov模块计算得出 |
| `Percentage of seeds` | 种子比例（斑块生成中随机种子的比例） ,默认为0.1|
| `Development type exist` | 是否存在发展类型（0=无），该参数默认为0，并且任何时候都不做改动|
| `Development type` | 发展类型编号，该参数默认为0，并且任何时候都不做改动 |
| `Development weight` | 发展类型权重，该参数默认为0.5，并且任何时候都不做改动 |

**批处理脚本运行后的产物**：
- 1张结果图，但是批处理脚本运行后会改变输出文件的命名，在原有命名的基础上加上后缀Simulation_1。例如当参数文件中写定的结果输出文件路径为：C:\Users\10421\Desktop\testdata\t1\cars.tif，批处理脚本运行完毕后将在t1文件夹内输出1个命名为carsSimulation_1.tif的概率图
---

### 7. Validation — 模拟精度验证

**功能**：对比模拟结果与真实 LULC，计算 Kappa 系数和 FoM（Figure of Merit）精度指标。

**批处理脚本** `validate.bat`

**参数文件** `PLUS_Validation.tmp`：

| 参数 | 说明 |
|------|------|
| `IsFom` | 是否切换为计算 FoM 指标（0=计算 Kappa, 1=计算FoM） |
| `Sampling rate` | 验证采样率，默认为0.1 |
| `Simulated Map` | 模拟结果 LULC 栅格，一般为CARS模块输出的结果图 |
| `Real Map` | 真实参考 LULC 栅格 |
| `Start Map` | 模拟起始年份 LULC 栅格 |

**批处理脚本运行后的产物**：
计算kappa系数时生成Kappa.csv表格，计算Fom系数时生成FoM.csv表格。表格了里面记录了结果

---

### 8. Diverse — 多模拟结果集成

**功能**：将多次模拟（如 Markov 和 Linear 驱动结果）进行集成/对比分析。

**批处理脚本** `diverse.bat`

**参数文件** `PLUS_Diverse.tmp`：

| 参数 | 说明 |
|------|------|
| `Image Amount` | 需要集成的模拟结果数量 |
| `Images Path` | 模拟结果栅格列表 |
| `Output Path` | 结果的输出文件路径 |

**批处理脚本运行后的产物**：
一张多样性图，和输出文件路径一致
---



## 标准运行流程

```
[数据准备] → 两期LULC栅格数据（起始年份土地利用数据以及结束年份土地利用数据） + 驱动因子数据文件夹
[1. Convert] 两期LULC栅格数据 → 两期转换后的数据
  ↓
[2. Expansion] 两期转换后的数据 → 一张土地扩张图
  ↓
[3. LEAS]     一张土地扩张图 + 设定随机森林参数 + 驱动因子数据文件夹 → 各类型发生概率图
  ↓
[4. Markov]   起始年份土地利用数据+结束年份土地利用数据+设定相关年份（起始年份、结束年份、预测目标年份） → 预测年各地类需求量 (markov.csv)
  ↓
[5. CARS]     设定土地利用类型数量 + 起始年份土地利用数据 + 各类型发生概率图 + 限制性约束图（可选项）+设定其它模拟参数→ 未来 LULC 模拟图

```

## 注意事项

- 所有路径在 tmp 文件中涉及到路径的编写均使用绝对路径
- 栅格数据需保持一致的投影、分辨率和范围

