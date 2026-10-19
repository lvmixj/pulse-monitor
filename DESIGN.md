# Pulse界面设计

采用已安装的Anthropic frontend-design流程，先确定本机监控任务、设计变量和布局，再按实际截图复查。

## 设计变量

- 背景：深海蓝`#101b2b`；表面：蓝灰`#172538`。
- 主文字：冷白`#e6edf7`；次级文字：灰蓝`#a2b3c8`。
- CPU蓝`#62b5ff`、内存紫`#bc9bff`、GPU青绿`#59d9be`；资源颜色同时配文字标签。
- 中文字体使用本机Noto Sans CJK SC，标题26px、主要读数32px、正文13px。
- 内容左对齐；导航190px，主区域28px边距，面板间距16px。

## 布局与复查

```
导航     总览标题                       暂停 / 小组件
         CPU             内存             GPU
         三资源同轴趋势                   本机硬件
         磁盘活动                        网络活动
```

让时间趋势成为主要视觉元素，百分比保持同轴对照。详细页把趋势与原始硬件数据分开；进程页使用可排序表格。小组件压缩成三资源数值、一幅趋势和网络速率。

按任务复查：资源监控需要同时看占用与变化，保留指标卡和趋势图；去掉装饰性动画、宣传图和渐变背景。仅曲线下方使用淡色面积，帮助辨识不同资源。所有数据来自实际采样，启动前的历史为空白。核验默认窗口、最小窗口和小组件截图。

参考资料：

- https://github.com/anthropics/skills/tree/main/skills/frontend-design
- https://missioncenter.io/
- https://github.com/aristocratos/btop
- https://github.com/brndnmtthws/conky/wiki/FAQ
- https://psutil.readthedocs.io/stable/
- https://doc.qt.io/qt-6/qt.html#WindowType-enum
- https://docs.nvidia.com/deploy/nvidia-smi/index.html

## 交互与资源图更新

CPU详情与小组件按操作系统CPU编号显示每个逻辑核心，固定0–100%负载条，高负载使用琥珀色。GPU环图表达当前利用率，显存条表达容量占比，趋势保留时间变化。小组件默认普通悬浮，桌面下层为可选模式，保持utility窗口接收真实鼠标操作。

## 顶栏图形与设置

范围限定于顶栏组件及其设置。保留主窗口和桌面小组件原有图形。顶栏默认左侧，CPU蓝、GPU青绿、内存紫；图形与数字并排。趋势图使用真实60秒时间轴、0–100%固定刻度；负载条模式用CPU逐逻辑核心小柱和GPU占用条；纯数字模式压缩横向空间。资源项目可逐项隐藏，全部隐藏时保留菜单入口。参考Mission Center、btop与nvtop的监控表达，保留Pulse现有视觉语言。

## 2026-10-19界面与分层修复

本轮按ui-ux-pro-max的桌面监控设计流程检索：`system monitoring desktop dashboard --design-system --density 8`返回实时运营模式，采用其真实更新时间、暂停控制和语义颜色建议；补充`operations dashboard dense minimal --domain style`命中Minimalism & Swiss Style，采用紧凑网格、清晰层级与低动画。工具不含PySide6栈，Qt实现依据官方文档。

布局保留资源导航与总览网格，统一使用10px面板圆角、16px面板间距、20px内容内边距和一套SVG线性导航图标。详情页将当前读数、固定上限250px的趋势图及硬件详情分层显示。设置页整体滚动，适配980×740最小桌面窗口。三套主题使用同一份字体、布局和交互规则，正文与状态色按4.5:1检查。

- `collector.py`与`Sampler`负责真实采样，不导入主题。
- `state.py::MonitorState`只保存最新采样、历史、暂停快照，不依赖Qt或主题。
- `ui.py`负责数据绑定、导航和用户操作。主题选择只调用换肤并保存`theme`偏好。
- `theme.py`只提供不可变的具名颜色、统一QSS和重绘入口。删除全控件遍历、内联样式缓存、十六进制颜色替换以及全局可变主题变量。
- 图表仅在绘制时读取`cpu`、`memory`、`surface`等语义颜色，数值和历史来自监控状态层。

空白页复现路径：首个采样到达前暂停，将None保存为冻结快照，后续接收采样时主窗口持续保持空状态。修复为首个采样前禁用暂停按钮，状态层也拒绝冻结空数据。暂停后切换页面始终绑定冻结快照，继续显示后恢复最新采样。暂停快捷键使用Ctrl+Space，普通空格交还下拉框和搜索框。

验证包含暂停前启动、暂停中换肤、所有资源页导航、小组件实时更新、恢复显示、重新启动、三主题文字对比度和超过2GiB的进程内存排序；报告位于`artifacts/theme-verification.json`。Qt默认跨Int/LongLong排序在本机进程内存超过2GiB时出现错序，采用官方`lessThan`接口按Python数值比较。

参考：
- https://doc.qt.io/qt-6/model-view-programming.html
- https://doc.qt.io/qtforpython-6/PySide6/QtGui/QShortcut.html
- https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSortFilterProxyModel.html
- https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
