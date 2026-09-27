
---

## `README.zh-CN.md`（中文）

```markdown
# SimplePlanes Tool — Unity TMP 富文本可视化编辑器

[English](README.md) | **中文**

![version](https://img.shields.io/badge/version-0.75-blue)
![python](https://img.shields.io/badge/python-3.7%2B-blue)
![pyqt5](https://img.shields.io/badge/PyQt5-5.15%2B-green)

一个面向 **Unity TextMeshPro** 的富文本可视化编辑器。
拖拽摆字符、写表达式绑定动画、实时预览、一键导出可直接粘进游戏的富文本。
无需美术资源，无需编程。

![程序图](https://s1.imagehub.cc/images/2026/09/27/ac6c87fd578ecb506639776283fc9f6e.md.png)

---

## 它是什么

SimplePlanes 的 Label 零件使用 Unity TMP（TextMeshPro）富文本系统。想要让文字改变大小、颜色、位置、旋转，或者在飞行中实时显示油门、速度、高度，你必须在 Label 里手写一串东西，再加表达式、变量、条件判断、动画函数……很快就会变成一坨没人看得懂的字符汤。

**这个工具把这一切可视化了。**

在画布上拖拽、缩放、旋转字符，实时看到效果，下方输出栏同步生成可以直接粘贴进简飞 Label 零件的 TMP 富文本代码。

---

## 核心功能

- **可视化编辑**：画布上直接拖拽、缩放、旋转，带包围盒和旋转手柄；网格 / 辅助对象 / 辅助线吸附；多选、框选、批量编辑
- **完整样式控制**：`pos` / `voffset` / `size` / `rotate` / `color` 全部可视化调节；标尺、网格、画布边框可开关
- **表达式引擎（FunkyTree 风格）**：内置控制变量（`Throttle` `Yaw` `Pitch` `Roll` `Heading` `VTOL` `Trim` `Activate1~8` `LandingGear`）、完整飞行数据、30+ 数学函数、状态函数（`sum()` `rate()` `smooth()` `PID()`）、三元表达式、格式化后缀（`{Altitude;0.0}`）
- **控制面板**：双摇杆、姿态摇杆 + 姿态仪、Heading 旋钮、VTOL / Trim 滑块、8 个 Activate 按钮、时间控制；可浮出为独立窗口
- **辅助线与吸附**：创建点 / 线 / 圆；字符可静态吸附、沿线滑动、绕圆旋转；父对象紫色虚线高亮；支持批量与递归解除
- **字符选择表**：树形文件夹、拖拽重排、单双排切换、隐藏显示、分享为 JSON
- **自定义变量**：玩家起名、范围与滑块实时调节；重名或非法名自动红框提示
- **表达式压缩（CSE）**：自动提取公共子表达式；低 / 中 / 高三档；变量名前缀可自定义
- **导入导出**：导入 TMP 富文本、导出 PNG、保存 / 打开工程 JSON、自动保存设置并在下次启动恢复
- **中英文双语**：界面一键切换，无需重启

---

## 运行环境

- 语言：Python 3.7+
- 界面：PyQt5
- 依赖：`pip install PyQt5`
- 运行：直接运行脚本即可，无需编译
- 平台：Windows / macOS / Linux

---

## 操作注意事项

**画布**：滚轮缩放｜中键/Alt+左键平移｜左键选中、拖动移动｜右键弹菜单、右键拖动框选｜双击改文字｜Delete 删除｜Ctrl+Z/Y 撤销重做｜Ctrl+C/V 复制粘贴｜方向键微调｜Q/E 旋转

**功能**：支持 FunkyTree 表达式、飞行数据、辅助线吸附、自定义变量、表达式压缩、工程保存与自动恢复、中英文切换等

**⚠️⚠️⚠️ 最重要的一点**：
把输出粘贴进游戏 Label 零件时，**务必先点开文本输入框旁边的小铅笔图标 ![铅笔图标](https://s1.imagehub.cc/images/2026/09/27/598e71c05746174ae47fce1f17220d8f.png)，把输入框彻底展开后再粘贴**。否则游戏会在折叠状态下反复重排超长文本，造成严重卡顿，甚至白屏闪退。

---

## 安装

**方式一 — 直接下载 exe（Windows）**：到 [Releases](https://github.com/LQSCFCS/SimplePlanes-Tool/releases) 页面下载 `TMPEditor.exe`，双击运行。

**方式二 — 源码运行**：

```bash
pip install PyQt5
python tmp_editor_0.75.py
