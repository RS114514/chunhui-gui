# Agent 开发指南与规范 (chunhui-gui)

本项目（chunhui-gui）供 AI Agent 协同开发维护时遵循以下规范：

## 1. CLI 依赖维护规范 (`ch_cli.py`)

- **上游源码仓库**: [https://github.com/RS114514/chunhui-cil](https://github.com/RS114514/chunhui-cil)
- **本地开发路径（若在同一开发机）**: `../chunhui-cli`（即同级目录下的 `chunhui-cli` 仓库）

### ⚠️ 重要原则
1. **统一源头**：`ch_cli.py` 是独立 CLI 仓库（`chunhui-cil`）的核心模块。所有关于 CLI 协议、接口、解析逻辑、网络请求、会话管理的新特性与修复，均以 `https://github.com/RS114514/chunhui-cil` 为开发源头。
2. **禁止单向修改**：任何 Agent **严禁**在 `chunhui-gui` 项目中单独修改 `ch_cli.py` 却不同步回 `chunhui-cil`。如需修改 CLI 相关逻辑，必须先在 `chunhui-cil` 中完成开发并验证，再同步至本仓库。
3. **版本同步流程**：
   - 当 `chunhui-cil` 发布新版本或产生更新时，应将最新的 `ch_cli.py` 同步覆盖至本仓库根目录。
   - 同步后必须执行语法与兼容性验证：
     ```bash
     python3 -m py_compile ch_cli.py main_gui.py
     ```
   - 确认无误后在 `chunhui-gui` 创建提交并推送。

## 2. 界面与构建验证规范
- 本项目主要界面入口为 `main_gui.py`，离线排版测试工具为 `test_gui.py`。
- 推送 `main` 分支会自动触发 GitHub Actions 执行 Windows（.exe）与 macOS（.app / .zip）的自动打包发布流程。
