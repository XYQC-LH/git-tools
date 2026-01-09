# Git 仓库管理工具

一个基于 Python tkinter 的 Git 仓库管理 GUI 工具，提供直观的界面来管理 Git 分支、Tag 和远程仓库。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## 功能特性

### 仓库管理
- 📁 选择并加载本地 Git 仓库
- 🕐 最近使用仓库快速访问
- 🔄 自动刷新和离线刷新模式
- 📥 一键 Fetch 拉取远程更新

### 分支管理
- 📋 显示本地和远程分支列表
- 🏷️ 状态标记：`[L]` 本地、`[R]` 远程、`[L+R]` 两者都有
- ⭐ 当前分支高亮显示（`*` 标记）
- 🔍 分支搜索/过滤功能
- 🔀 双击快速切换分支
- 🗑️ 删除分支（支持本地+远程同时删除）
- 📋 右键菜单快捷操作

### Tag 管理
- 📋 显示本地和远程 Tag 列表
- 🏷️ 状态标记：`[L]` 本地、`[R]` 远程、`[L+R]` 两者都有
- 🔍 Tag 搜索/过滤功能
- 🗑️ 删除 Tag（支持本地+远程同时删除）
- 📋 右键菜单快捷操作

### 推送功能
- 🚀 推送当前 HEAD 到指定远程分支
- ⚙️ 可选设置上游分支（`-u`）
- ⚠️ 支持强制推送（`--force-with-lease`）
- 🏷️ 可选同时创建并推送 Tag

### 远程仓库管理
- 📡 查看已配置的远程仓库
- ➕ 添加新远程（支持多种 URL 格式）
- ✏️ 编辑远程 URL
- 🗑️ 删除远程配置
- 🔄 HTTPS/SSH 协议快速切换
- 🔗 智能解析 GitHub URL（支持 `user/repo` 简写格式）

### 用户体验
- 📊 实时日志和进度显示
- ⚠️ 危险操作二次确认
- ⌨️ 快捷键支持
- 💾 配置持久化（窗口大小、最近仓库等）

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `F5` | 刷新仓库信息 |
| `Ctrl+P` | 开始推送 |
| `Ctrl+F` | 聚焦到分支搜索框 |
| `Delete` | 删除选中的分支/Tag |

## 安装

### 环境要求

- Python 3.10+
- Git（已安装并配置在系统 PATH 中）
- tkinter（Python 标准库，通常已包含）

### 安装步骤

1. 克隆仓库：
```bash
git clone https://github.com/your-username/auto-github.git
cd auto-github
```

2. 无需安装额外依赖，直接运行即可。

## 使用方法

### 启动应用

```bash
python start.py
```

或使用向后兼容入口：

```bash
python git_repo_manager_gui.py
```

### 基本操作流程

1. **选择仓库**：点击「选择...」按钮或从「最近」菜单选择仓库
2. **查看信息**：应用会自动加载分支、Tag 和远程信息
3. **管理分支**：
   - 双击分支切换
   - 右键菜单进行更多操作
   - 使用搜索框过滤分支
4. **推送代码**：
   - 选择远程和目标分支
   - 可选创建 Tag
   - 点击「开始推送」

## 项目结构

```
auto-github/
├── start.py                    # 入口文件
├── git_repo_manager_gui.py     # 向后兼容入口
├── README.md                   # 项目说明
└── app/                        # 应用包
    ├── __init__.py            # 包初始化
    ├── __main__.py            # python -m app 入口
    ├── config.py              # 配置管理
    ├── models.py              # 数据模型
    ├── git_utils.py           # Git 工具函数
    ├── dialogs.py             # 对话框类
    ├── services/              # Service 层（无 UI 依赖）
    ├── controllers/           # Controller 层（编排 UI 与 Service）
    ├── ui/                    # UI 层（Frame 组件）
    └── main.py                # 主应用类
```

### 模块说明

| 模块 | 说明 |
|------|------|
| [`start.py`](start.py) | 应用入口点 |
| [`app/config.py`](app/config.py) | 配置文件管理、AppConfig 类 |
| [`app/models.py`](app/models.py) | 数据模型（GitCommandError、RepoData） |
| [`app/git_utils.py`](app/git_utils.py) | Git 命令封装、URL 解析工具 |
| [`app/dialogs.py`](app/dialogs.py) | 对话框类（远程管理、确认对话框） |
| [`app/services/repo_data_service.py`](app/services/repo_data_service.py) | 仓库信息采集（RepoData） |
| [`app/services/git_stream.py`](app/services/git_stream.py) | Git 流式执行（进度/日志） |
| [`app/ui/main_view.py`](app/ui/main_view.py) | 主视图（组装各 Frame） |
| [`app/controllers/app_controller.py`](app/controllers/app_controller.py) | 控制器（事件编排、线程/队列） |
| [`app/main.py`](app/main.py) | 主应用类 GitRepoManagerApp |

## 配置文件

应用配置保存在用户主目录下：

- **Windows**: `C:\Users\<用户名>\.git_repo_manager_config.json`
- **macOS/Linux**: `~/.git_repo_manager_config.json`

配置内容包括：
- 最近使用的仓库列表（最多 10 个）
- 窗口大小和位置
- 上次打开的仓库路径

## 截图

*（待添加）*

## 开发

### 代码风格

- 使用 Python 类型注解
- 遵循 PEP 8 规范
- 使用 dataclass 定义数据结构

### 扩展开发

如需添加新功能：

1. **新增 Git 操作**：在 [`app/git_utils.py`](app/git_utils.py) 中添加函数
2. **新增对话框**：在 [`app/dialogs.py`](app/dialogs.py) 中添加类
3. **修改主界面**：在 [`app/ui/frames`](app/ui/frames) 中调整/新增 Frame，并在 [`app/ui/main_view.py`](app/ui/main_view.py) 组装
4. **接入业务逻辑**：在 [`app/controllers/app_controller.py`](app/controllers/app_controller.py) 中新增/调整事件处理与 Git 操作编排

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### v1.0.0
- 初始版本
- 支持分支和 Tag 管理
- 支持推送功能
- 支持远程仓库管理
- 模块化代码结构
