# VTune MCP Server for Claude Code

将 Intel VTune Profiler CLI 封装为 MCP 工具，让 Claude Code 直接分析 VTune 采集结果、定位函数级性能热点、生成可交互的 HTML 对比报告。

## 前置条件

- Python 3.10+
- Intel VTune Profiler（默认路径 `C:\Program Files (x86)\Intel\oneAPI\vtune\2026.1`）

## 初始化虚拟环境

首次使用时执行一次：

```bash
cd E:\Git\vtune-mcp-server
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
```

验证安装：

```bash
venv\Scripts\python.exe -c "from mcp.server.fastmcp import FastMCP; print('OK')"
```

## 注册到 Claude Code

> 推荐使用项目自带的 `venv/` 虚拟环境，依赖隔离，避免与系统 Python 冲突。

### 方式 1：本地路径注册（推荐）

```bash
claude mcp add --scope user vtune-profiler -- "E:\Git\vtune-mcp-server\venv\Scripts\python.exe" "E:\Git\vtune-mcp-server\server.py"
```

### 方式 2：手动编辑配置文件

编辑 `~/.claude.json`（即 `C:\Users\<你的用户名>\.claude.json`），找到 `mcpServers` 节点，添加：

```json
"vtune-profiler": {
  "type": "stdio",
  "command": "E:/Git/vtune-mcp-server/venv/Scripts/python.exe",
  "args": ["E:/Git/vtune-mcp-server/server.py"],
  "env": {}
}
```

### 方式 3：项目级配置（`.mcp.json`）

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "vtune-profiler": {
      "command": "E:/Git/vtune-mcp-server/venv/Scripts/python.exe",
      "args": ["E:/Git/vtune-mcp-server/server.py"],
      "env": {}
    }
  }
}
```

> 注册后需要**重启 Claude Code**才能生效。

### 自定义 VTune 路径（VTUNE_PATH）

默认路径为 `C:\Program Files (x86)\Intel\oneAPI\vtune\2026.1\bin64\vtune.exe`。如果你的 VTune 安装在其他位置，通过 MCP 配置的 `env` 字段设置 `VTUNE_PATH` 环境变量即可覆盖：

```bash
claude mcp add --scope user vtune-profiler -e VTUNE_PATH="D:/Intel/vtune/bin64/vtune.exe" -- "E:\Git\vtune-mcp-server\venv\Scripts\python.exe" "E:\Git\vtune-mcp-server\server.py"
```

或手动配置：

```json
"vtune-profiler": {
  "type": "stdio",
  "command": "python",
  "args": ["E:/Git/vtune-mcp-server/server.py"],
  "env": {
    "VTUNE_PATH": "D:/Intel/vtune/bin64/vtune.exe"
  }
}
```

> `VTUNE_PATH` 必须指向 `vtune.exe` 的完整路径，不是目录。

## 提供的工具

| 工具 | 用途 |
|------|------|
| `vtune_report` | 通用报告生成（支持 hotspots/summary/top-down/callstacks/hw-events，CSV/text 格式） |
| `vtune_list_results` | 列出项目文件夹下所有 VTune 结果目录 |
| `vtune_compare` | 对比两次采集结果的性能差异 |
| `vtune_summary` | 快捷获取单次结果的摘要 |
| `vtune_hotspots` | 获取 Top N 热点函数（CSV 格式，AI 分析友好） |
| `vtune_function_tree` | **核心工具**：对比两个 VTune 结果中指定函数的 top-down 调用树，生成交互式 HTML 报告 |

## 核心用法 — 函数级性能热点对比

这是本项目的核心场景：给定两次 VTune 采集结果，分析某个函数在两版之间的性能变化及其调用树差异。

### 示例 1：对比两个版本中的 OnPhysScenePreStep

在 Claude Code 中直接说：

```
C:\Users\Ambition\Desktop\VTun\GSTM_DS_vtune r354hs r361hs OnPhysScenePreStep函数的性能热点是什么
```

Claude 会自动调用 `vtune_function_tree`，生成 HTML 报告到：

```
C:\Users\Ambition\Desktop\VTun\GSTM_DS_vtune\r354hs\r354hs_vs_r361hs_tree.html
```

打开后你可以看到：
- **Total%**：函数在整体 CPU 时间中的占比
- **Self%**：函数自身的 CPU 消耗（不含子调用）
- **Diff(Total/Self)**：r361hs 相对于 r354hs 的变化量
- **可折叠调用树**：点击 ▼/▶ 展开或收起子函数
- **暗色主题自适应**：跟随系统 dark mode
- **红绿高亮**：红色 = 消耗增加，绿色 = 消耗降低

### 示例 2：直接列出所有 VTune 结果

```
列出 C:\Users\Ambition\Desktop\VTun\GSTM_DS_vtune 下的所有 VTune 结果
```

### 示例 3：分析单次采集的热点函数

```
分析 C:\Users\Ambition\Desktop\VTun\GSTM_DS_vtune\r354hs 的热点函数，给出优化建议
```

### 示例 4：对比两次采集的性能差异

```
对比 r354hs 和 r361hs 的性能差异
```

## 路径简写

如果 MCP 配置了 `VTUNE_PROJECT_DIR` 环境变量（如 `C:\Users\Ambition\Desktop\VTun\GSTM_DS_vtune`），你可以只写 `r354hs` 而不用写完整路径。

例如设置环境变量后：
```json
"env": {
  "VTUNE_PROJECT_DIR": "C:/Users/Ambition/Desktop/VTun/GSTM_DS_vtune"
}
```

然后直接说：
```
r354hs r361hs OnPhysScenePreStep 的性能热点是什么
```

## 验证安装

重启 Claude Code 后，输入：

```
/mcp
```

应该能看到 `vtune-profiler` 服务器及其 6 个工具。

## 项目结构

```
vtune-mcp-server/
├── server.py              # MCP Server 主文件（单文件，无抽象层）
├── pyproject.toml         # 项目配置
├── templates/
│   └── function_tree.html # 交互式调用树对比报告的 HTML 模板
└── tests/
    ├── test_server.py     # 测试套件
    └── fixtures/          # （空，测试使用 mock 数据）
```
