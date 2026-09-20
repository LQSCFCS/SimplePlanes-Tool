# SimplePlanes Tool — Unity TMP 富文本可视化编辑器

[English](README.md) | **中文**

![version](https://img.shields.io/badge/version-0.75-blue)
![python](https://img.shields.io/badge/python-3.7%2B-blue)
![pyqt5](https://img.shields.io/badge/PyQt5-5.15%2B-green)

一个面向 **Unity TextMeshPro** 的富文本可视化编辑器。
拖拽摆字符、写表达式绑定动画、实时预览、一键导出可直接粘进 Unity 的富文本。
无需美术资源，无需编程。

---

## 这是什么

在 Unity 里做 HUD 通常有两种做法：

- 画贴图 → 资源多、改起来烦
- 手写 TMP 富文本 + FunkyTree 表达式 → 效率低、调一次改一次代码

这个工具把第二种做法**可视化**：在画布上拖拽摆放字符的位置、尺寸、角度、颜色，
用表达式（`{Altitude*10}`、`{sin(Time*60)*5}`、`{clamp(Throttle,0,1)*100}` …）
绑定到飞行数据或控制变量上，实时预览效果，一键导出 TMP 富文本，直接粘进 SimplePlanes。

---

## 核心特性

### 画布可视化编辑
- 拖拽移动 / 缩放 / 旋转，带包围盒和旋转手柄
- 网格吸附 + 辅助对象吸附 + 辅助线吸附
- 多选、框选、批量编辑
- 标尺、网格、画布边框，均可开关
- 滚轮缩放、中键 / `Alt`+左键平移、适应窗口
- 支持 4K / 2K / 1080p / 720p ，兼容系统 DPI 缩放

### 表达式引擎（FunkyTree 风格）
- **内置变量**：`Throttle` `Yaw` `Brake` `Pitch` `Roll` `Heading` `VTOL` `Trim` `Activate1~8` `LandingGear`
- **飞行数据**：`Altitude` `GS` `IAS` `TAS` `Fuel` `AngleOfAttack` `PitchAngle` `RollAngle` `Time` `GForce` `Latitude` `Longitude` 等
- **函数库**：`sin` `cos` `clamp` `lerp` `smoothstep` `pingpong` `sqrt` `atan2` … 30+ 个
- **状态函数**：`sum()`（积分）、`rate()`（微分）、`smooth()`（平滑）、`PID()`
- **三元表达式**：`{Throttle>0.5?"ON":"OFF"}`
- **格式化后缀**：`{Altitude;0.0}` → 保留 1 位小数

### 控制面板
- 双摇杆：左杆（油门 / Yaw / 刹车）、右杆（俯仰 / 滚转）
- 姿态摇杆 + 姿态仪 + Pitch / Roll 实时数值
- Heading 旋钮、VTOL / Trim 滑块
- 8 个 Activate 按钮 + LandingGear + Brake
- **时间控制**：运行测试、速度倍率、归零重置
- 可**浮出为独立窗口**，也可合并回主窗口

### 辅助线系统
- 点 / 线段 / 圆
- 可绑定表达式，让辅助线本身也动起来
- 吸附到网格 / 吸附到辅助对象 / 整体锁定

### 吸附 / 绑定
- 字符吸附到字符、点、线、圆
- 三种控制方式：
  - **静态吸附**（保持相对位置与角度）
  - **沿辅助线滑动**（由控制变量驱动）
  - **沿辅助圆旋转**（支持切线朝向）
- 父对象以**紫色虚线高亮**
- 多选批量吸附、解除吸附、递归解除

### 字符选择表
- 树形文件夹结构、拖拽重排
- 单排 / 双排切换（切换后自动全部收起）
- 隐藏 / 显示、上下移、复制
- 分享为 JSON / 从 JSON 导入
- `Del` 删除、右键菜单（重命名 / 隐藏 / 删除）

### 自定义变量（Variable Outputs）
- 玩家起名、最小值 / 最大值 / 当前值、滑块实时调节
- 变量名冲突自动红框提示，非法字符无法输入

### 自定义函数（CSE 压缩）
- 自动提取公共子表达式，主输出大幅缩短
- **压缩程度**：低 / 中 / 高 三档
- **变量名前缀**可自定义（`V`、`abc`、`myVar`…）
- 无用定义剔除 + 融合 + 二次内联 + 连续重编号

### 导入导出
- 导入 Unity TMP 富文本、导出 PNG
- 保存 / 打开工程（JSON），支持拖拽加载
- **保存设置**：自动保存当前所有状态，下次启动一键恢复
  - 画布内容、吸附关系、辅助对象
  - 控制变量、飞行数据、自定义变量
  - 压缩程度、变量前缀、面板显隐、显示开关
  - 主窗口位置尺寸、独立面板 / 子窗口状态

### 多语言
- 中 / 英双语，一键切换无需重启
- **反向标签**：中文界面显示 `Language:`，英文界面显示 `语言:`

---

## 安装

### 方式一：直接下载 exe（Windows）

到 [Releases](https://github.com/LQSCFCS/SimplePlanes-Tool/releases) 页面下载 `TMPEditor.exe`，双击运行。

### 方式二：源码运行

```bash
# 需要 Python 3.7+
pip install PyQt5
python tmp_editor_0.75.py
```

### 方式三：自行打包

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name TMPEditor tmp_editor_0.75.py
```

生成的 exe 在 `dist/` 目录下。

---

## 快速上手

1. **添加字符** — 工具栏 `＋ 添加字符`，或画布右键 → 添加字符
2. **摆位置** — 拖拽移动；拖角上的小方块缩放；拖顶部的圆点旋转
3. **写表达式** — 右侧属性面板 → `文本内容` → `{Altitude;0.0}m`
4. **绑定动画** — 选中字符，右键 → `🔗 吸附到…`，点击另一个对象作为父级
5. **预览** — 勾选 `运行测试`，或拖动控制面板摇杆，画布实时更新
6. **导出** — 菜单 `更多 → 导出富文本`，复制后粘进 Unity TMP

---

## 快捷键

| 快捷键 | 作用 |
|--------|------|
| `Ctrl + C` / `Ctrl + V` | 复制 / 粘贴（粘到鼠标位置，开网格吸附时自动吸网格） |
| `Ctrl + Z` / `Ctrl + Y` | 撤销 / 重做（50 步） |
| `Ctrl + A` | 全选 |
| `Ctrl + D` | 复制选中 |
| `Del` / `Backspace` | 删除 |
| `← ↑ → ↓` | 微调（`Shift` 加速） |
| `Ctrl + =` / `Ctrl + -` | 缩放选中 |
| `Q` / `E` | 旋转 ∓5° |
| `B` | 切换显示包围盒 |
| 鼠标滚轮 | 缩放画布 |
| 中键 / `Alt` + 左键 | 平移画布 |

---

## 表达式速查

```text
简单变量      {Altitude}
带格式化      {Altitude;0.0}          → 保留 1 位小数
运算          {Throttle*100}
函数          {sin(Time*60)*5}
条件          {Activate1>0?"ARMED":"SAFE"}
积分          {sum(Throttle)}         → 油门随时间的积分
微分          {rate(Altitude)}        → 爬升率
平滑          {smooth(noise,10)}      → 每秒 10 单位平滑
PID           {PID(target,current,1,0,0)}
```

富文本标签（写在字符文本里）：

```text
<color=#FF0000>红字</color>
<alpha=#80>半透明</alpha>
<mark=#FFFF00FF>黄底</mark>
<b>粗</b> <i>斜</i> <u>下划线</u> <s>删除线</s>
<size=150%>大</size>
<rotate=45>旋转</rotate>
<br> 换行
<space=4> 可控空格
```

---

## 常见问题

**Q：导出的富文本超过 3072 字节怎么办？**
A：Unity TMP 单个文本块上限约 3072 字节。可以：
- 提高「自定义函数」的压缩程度到 **高**
- 让多个字符共享父对象引用
- 拆分为多个文本块

**Q：画布上的字符位置和 Unity 里不一致？**
A：确保 `画布 W` / `画布 H` 和 Unity 那边一致，且 TMP 组件用的是相同字体与字号。

**Q：为什么有些字符是空的？**
A：表达式语法错误。检查属性面板的预览行，非法表达式会显示为红色。

**Q：如何备份我的设置？**
A：菜单 `更多 → 保存设置`，选择一个 JSON 路径。之后每次编辑会自动写入，下次启动自动恢复。

---



## 依赖

- Python 3.7+
- PyQt5