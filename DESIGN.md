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
