# 参与贡献

欢迎通过Issue报告问题或通过Pull Request提交修改。

报告问题时请提供Ubuntu、GNOME、X11/Wayland、Python和依赖版本，说明复现步骤、期望行为与实际结果。GPU相关问题附上驱动版本和`nvidia-smi`是否可用。日志、截图和进程列表中的个人信息请先移除。

提交代码前运行：

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

窗口交互、顶栏和后台生命周期修改还需要在GNOME42/X11测试桌面执行相应集成验收，操作说明见[开发文档](docs/DEVELOPMENT.md)。请说明验证环境与实际结果，将修改集中在当前问题。

提交的项目代码按仓库的MIT许可证提供；引用第三方代码或素材时保留其来源与许可证。
