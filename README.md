# 春晖中学校园网图形界面客户端 (chunhui-gui)

[![Platform-Windows](https://img.shields.io/badge/platform-Windows-blue)](https://github.com/RS114514/chunhui-gui/releases/tag/latest)
[![Platform-macOS](https://img.shields.io/badge/platform-macOS-lightgrey)](https://github.com/RS114514/chunhui-gui/releases/tag/latest)
[![Language-Python](https://img.shields.io/badge/language-Python-3776AB)](https://www.python.org/)
[![UI-CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-blueviolet)](https://github.com/TomSchimansky/CustomTkinter)
[![License-MIT](https://img.shields.io/badge/license-MIT-green)](https://github.com/RS114514/chunhui-gui/blob/main/LICENSE)

本项目是专为春晖中学校园网打造的现代化、高质感跨平台桌面图形界面（GUI）客户端。基于 Python 3 与 **CustomTkinter** 现代美学界面库开发，具备轻量化、圆角扁平卡片设计与高 DPI 自适应特性。

客户端内置了独立的 Python 运行时，解压即可运行，**免除配置开发环境的烦恼**。

---

## 🎨 核心界面特色

1. **🔑 账户会话面板**：一键导入 Cookie 并具备自动在线状态心跳检验，绿/红颜色清晰指示当前与校园网的连线状态。
2. **✉️ 收件箱消息通知**：以精美卡片列表分页展现，点击可直接弹窗阅读消息正文。系统能智能解析通知内含的所有压缩包、课件等附件，支持图形化一键下载至指定目录。
3. **📄 校内资讯与公告**：支持下拉选择通知公告、校内公示、值周小结等多栏目，免去浏览器层层点击，正文及链接完好排版展示。
4. **🧹 纪律卫生与考评**：图形化查询各日期内的违纪记录与扣分明细，支持点击按钮直接下载现场的违纪多媒体照片。
5. **🏠 寝室分配与楼宇考评**：
   * **班级寝室**：输入年级和班级一键拉取分配使用的寝室列表。
   * **宿舍扣分**：下拉选择 1-10 号楼宇并设定任意查询天数，一键按寝室号生成考评汇总卡片。
6. **📅 教师值周排班**：高亮展示当前星期的行政值周及小组老师，并提供总排班表供全学期按姓名模糊搜索。
7. **🔍 失物招领**：红绿色彩明确区分丢失与捡到状态，卡片式展示失物详情及招领联系电话，支持一键下载物品照片。
8. **📁 文件临时寄存寄取**：
   * **寄存上传**：支持本地拖拽或选择文件，显示文件元数据，**图形化进度条**显示分片上传进度。合并成功后高亮显示 6 位文件提取码，支持一键复制。
   * **安全提取**：输入提取码即可将临时文件安全高速拉取到本地任意选择的目录中。

---

## 🚀 下载与使用

### 1. 从 Releases 页面直接下载（推荐，无需任何环境配置）
每次向 GitHub 仓库推送代码时，自动化构建工作流（GitHub Actions）会同时在 Windows 和 macOS 虚拟机上为客户端进行独立封装。
- 前往 GitHub 仓库的 **Releases** 页面。
- 根据您的系统下载对应的最新发布产物：
  - **Windows 用户**：下载 **`chunhui-gui-win.exe`**，双击即可直接运行（无任何 Python 依赖）。
  - **macOS 用户**：下载 **`chunhui-gui-mac.zip`**，解压后双击包内的 `chunhui-gui-mac.app` 即可运行。

### 2. 在本地手动运行（开发调试）
如果您的电脑安装了 Python 3 运行时，可以直接克隆项目在本地运行：
1. 安装 CustomTkinter 核心 UI 依赖与 Pillow 图像处理库：
   ```bash
   pip install customtkinter Pillow
   ```
2. 运行 GUI 客户端：
   ```bash
   python3 main_gui.py
   ```

### 3. 免联线本地离线测试工具
我们提供了一个独立的离线 UI 测试工具 **`test_gui.py`**。
- 您可以在没有内网或未登录校园网的情况下，直接运行该脚本：
  ```bash
  python3 test_gui.py
  ```
- 该工具支持左侧实时输入/编辑网页 HTML 源码，右侧直接预览 Markdown 富文本表格与各种格式的排版效果，方便开发与调试。

---

## 📅 更新日志

### [v1.2.0] - 2026-06-17
#### 🎨 客户端全面 Markdown 富文本升级
- **富文本展示**：公告消息、资讯公告、违纪明细和失物招领四大详情窗口全面接入原生 Markdown 渲染，自动吃掉原生语法标记（如 `**` 等），支持粗体高亮、下划线链接、大标题样式展示。
- **表格完美像素对齐**：统一表格内部所有常规文本、表头加粗文本、以及分割竖线（`table_sep`）的字号大小为基准 **14 号字**，结合中英文真实字符视觉宽度（`get_visual_width`）空格填充，彻底解决等宽表格歪斜错位的 Bug。
- **解决 Tag 缩放限制报错**：绕过 customtkinter 直接修改底层的 `_textbox.tag_config`，解决了 CTkTextbox 自带的 tag_config 与 scaling 机制冲突导致的 AttributeError 闪退报错。
- **新增工具**：新增免联线本地离线测试程序 `test_gui.py`。

---

## 📄 开源协议

本项目基于 **[MIT License](LICENSE)** 协议开源。
