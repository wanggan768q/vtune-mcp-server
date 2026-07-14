# VTune MCP Server for Claude Code

将 Intel VTune Profiler CLI 封装为 MCP 工具，让 Claude Code 直接分析性能数据。

## 安装

### 前置条件

- Python 3.10+（已安装 `mcp` SDK）
- Intel VTune 2026.1（默认路径 `C:\Program Files (x86)\Intel\oneAPI\vtune\2026.1`）

### 安装 MCP SDK（如未安装）

```bash
pip install "mcp>=1.2.0"
```

## 注册到 Claude Code

### 方式 1：命令行注册（推荐）

```bash
claude mcp add --scope user vtune-profiler -- python "E:\Git\vtune-mcp-server\server.py"
```

### 方式 2：手动编辑配置文件

编辑 `~/.claude.json`（即 `C:\Users\<你的用户名>\.claude.json`），找到 `mcpServers` 节点，添加：

```json
"vtune-profiler": {
  "type": "stdio",
  "command": "python",
  "args": ["E:/Git/vtune-mcp-server/server.py"],
  "env": {}
}
```

### 方式 3：项目级配置

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "vtune-profiler": {
      "command": "python",
      "args": ["E:/Git/vtune-mcp-server/server.py"],
      "env": {}
    }
  }
}
```

> 注册后需要**重启 Claude Code**才能生效。

## 自定义 VTune 路径（VTUNE_PATH）

默认路径为 `C:\Program Files (x86)\Intel\oneAPI\vtune\2026.1\bin64\vtune.exe`。如果你的 VTune 安装在其他位置，通过 MCP 配置的 `env` 字段设置 `VTUNE_PATH` 环境变量即可覆盖。

### 命令行注册时指定

```bash
claude mcp add --scope user vtune-profiler -e VTUNE_PATH="D:/Intel/vtune/bin64/vtune.exe" -- python "E:\Git\vtune-mcp-server\server.py"
```

### 手动配置时指定

在 `~/.claude.json` 或 `.mcp.json` 中的 `env` 字段里添加：

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

## 使用示例

注册成功后，在 Claude Code 对话中直接说：

```
列出 C:\Users\Ambition\Desktop\VTun\GSTM_DS_vtune 下的所有 VTune 结果
```

```
分析 C:\Users\Ambition\Desktop\VTun\GSTM_DS_vtune\r010hs 的热点函数，给出优化建议
```

```
对比 r010hs 和 r354hs 的性能差异
```

Claude 会自动调用对应工具获取数据并进行分析。

## 验证安装

重启 Claude Code 后，输入：

```
/mcp
```

应该能看到 `vtune-profiler` 服务器及其 5 个工具。
