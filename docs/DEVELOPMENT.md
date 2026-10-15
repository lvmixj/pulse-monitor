# 开发与验证

## 源码入口

| 文件 | 职责 |
| --- | --- |
| `pulse/collector.py` | 只读资源采集与速率计算 |
| `pulse/__main__.py` | 采样线程、单实例命令、顶栏监督和本地摘要 |
| `pulse/ui.py`、`pulse/charts.py` | 主窗口、设置、进程列表、资源图与小组件 |
| `pulse/panel_config.py` | 顶栏偏好及序列化契约 |
| `pulse/desktop.py` | 应用菜单与登录自启动条目 |
| `pulse/indicator.py` | 系统Python、GTK3与Ayatana数字顶栏 |
| `desktop/pulse-panel@local/` | GNOME42原生图形顶栏 |
| `desktop/pulse-monitor.service` | 安装脚本使用的服务模板 |
| `install.py` | 用户级桌面集成安装与卸载 |

## 基础测试

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

覆盖实际系统采样、GPU不可用与驱动异常、进程数值排序、无GPU的页面绘制，以及临时目录内的安装、迁移启动与卸载。桌面集成命令在这些测试中使用替身，避免影响正在使用的桌面服务。

GitHub Actions在Ubuntu22.04/Python3.10上执行这组检查，并校验Python语法、GNOME JavaScript语法及依赖一致性。

## 真实桌面验收

在测试桌面中安装依赖、桌面入口并启动Pulse。X11验收还需要`x11-utils`与`xdotool`。

```sh
.venv/bin/python tests/verify.py
/usr/bin/python3 tests/verify_background.py
```

第一组验收会创建窗口、移动真实鼠标、切换页面并执行短时CPU与回环网络工作负载。后台集成验收会切换Pulse窗口、模拟Pulse异常退出，验证服务重启与主动退出。在原生顶栏健康时自动转到`tests/verify_panel.py`，使用项目虚拟环境。

这些验收顺序执行，需要已登录的GNOME/X11桌面。输出写入被Git忽略的`artifacts/`，其中可能包含桌面截图和本机信息。

2026-10-14本机记录：Ubuntu22.04.5、GNOME42/X11、Python3.10.12、PySide6-Essentials6.11.2、psutil7.2.2；界面与采集验收56项，原生顶栏验收13项。原始报告与截图保存在开发者本地。发布整理移除了顶栏验收中依赖历史源码备份的比较项。

## PySide6版本

当前依赖固定在6.11.2。本机Python3.10/Linux环境曾在6.12.0遇到`none_dealloc`崩溃；1000次QTimer调用探针中None引用计数减少1002，同环境6.11.2差值为0。公开相近问题见[运行库问题记录](https://github.com/MerZlin/dsh-pet-indesktop/pull/245)。`verify.py`保留引用计数探针与连续趋势绘制检查。

升级PySide6时，先执行基础测试，再在隔离桌面执行实际入口与持续采样验收。

## 桌面集成参考

- [GNOME扩展目录与元数据](https://gjs.guide/extensions/overview/anatomy.html)：用户扩展目录、版本范围及GNOME45前后的模块差异。
- [systemd服务命令规则](https://github.com/systemd/systemd/blob/main/man/systemd.service.xml)：ExecStart引号、美元符号与命令执行。
- [Desktop Entry Exec规则](https://specifications.freedesktop.org/desktop-entry-spec/latest/exec-variables.html)：应用启动命令的两层转义。
- [systemd桌面会话集成](https://github.com/systemd/systemd/blob/main/docs/DESKTOP_ENVIRONMENTS.md)：用户服务与图形会话生命周期。
