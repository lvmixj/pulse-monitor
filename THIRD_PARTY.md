# 第三方依赖与设计参考

Pulse项目代码和应用图标按[MIT许可证](LICENSE)提供。第三方依赖按各自许可证提供；通过依赖管理器独立安装。

| 依赖 | 用途 | 许可与来源 |
| --- | --- | --- |
| PySide6-Essentials、Shiboken6及Qt | 桌面窗口与绘图 | [Qt for Python许可说明](https://doc.qt.io/qtforpython-6/licenses.html)，包含LGPLv3/GPLv3与商业许可选项，具体组件见发行包许可文件 |
| psutil | 系统与进程采集 | [BSD-3-Clause](https://github.com/giampaolo/psutil/blob/master/LICENSE) |
| PyGObject、GTK3、Ayatana AppIndicator | 数字顶栏及菜单 | 由操作系统软件包提供，许可见对应软件包的copyright文件 |
| GNOME Shell、GJS | 原生图形顶栏运行环境 | 由操作系统提供，许可见对应软件包 |

界面与交互参考[Mission Center](https://missioncenter.io/)、[btop](https://github.com/aristocratos/btop)、[Conky](https://github.com/brndnmtthws/conky)和[nvtop](https://github.com/Syllo/nvtop)。采集口径参考[psutil文档](https://psutil.readthedocs.io/stable/)，窗口行为参考[EWMH标准](https://specifications.freedesktop.org/wm/latest/ar01s05.html)，顶栏集成参考[GNOME扩展开发指南](https://gjs.guide/extensions/)和[Ayatana API](https://lazka.github.io/pgi-docs/AyatanaAppIndicator3-0.1/classes/Indicator.html)。

仓库提供源码。重新分发包含Qt、字体或其他运行库的安装包时，应随实际包含的组件提供其许可、版权声明及相应材料。
