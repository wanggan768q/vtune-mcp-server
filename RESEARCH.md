# Intel VTune 2026.1 + Claude Code 集成调研报告

## 一、数据结构概况

路径 `C:\Users\Ambition\Desktop\VTun\GSTM_DS_vtune` 包含：
- 7 个 Hotspots 分析结果（`r010hs`, `r017hs`, `r021hs`, `r023hs`, `r024hs`, `r354hs`, `r361hs`）
- 采集对象：UE Linux Server（GangstarServer），远程机器 `10.53.6.191` 上的数据
- 数据格式：每个结果目录下有 `sqlite-db/dicer.db`（~14MB SQLite）、`data.0/` 原始采样、`config/` 配置

## 二、让 Claude Code 调用 VTune CLI 的三种方式

### 方式 1：直接 Bash 调用（最简单，推荐先试）

VTune CLI 安装在：
```
C:\Program Files (x86)\Intel\oneAPI\vtune\2026.1\bin64\vtune.exe
```

核心命令：
```bash
# 生成 hotspots 文本报告
vtune -report hotspots -result-dir "C:\...\r010hs" -format text

# 生成 CSV 格式（便于 AI 解析）
vtune -report hotspots -result-dir "C:\...\r010hs" -format csv

# 生成 summary 报告
vtune -report summary -result-dir "C:\...\r010hs" -format text

# 生成 top-down（微架构分析）
vtune -report top-down -result-dir "C:\...\r010hs" -format csv

# 生成 callstacks 报告
vtune -report callstacks -result-dir "C:\...\r010hs" -format text
```

需要在 Claude Code 设置中添加 Bash 权限规则：
```json
{
  "permissions": {
    "allow": [
      "Bash(vtune*)",
      "Bash(*vtune.exe*)"
    ]
  }
}
```

### 方式 2：MCP Server（最优方案，一劳永逸）

MCP（Model Context Protocol）是 Claude Code 集成外部工具的官方标准。写一个 MCP server 把 VTune CLI 封装为工具，注册后 Claude Code 会话中自动出现 VTune 相关工具。

已实现于本目录的 `server.py`，暴露 5 个工具：
- `vtune_report` — 通用报告生成
- `vtune_list_results` — 列出项目下所有结果目录
- `vtune_compare` — 对比两次采集
- `vtune_summary` — 快捷摘要
- `vtune_hotspots` — Top N 热点函数（CSV，AI 友好）

注册命令：
```bash
claude mcp add --scope user vtune-profiler -- python "E:\Git\vtune-mcp-server\server.py"
```

### 方式 3：直接读 SQLite（最快获取数据，不依赖 CLI）

结果目录中 `sqlite-db/dicer.db` 是 VTune 的核心数据存储，可用 Python/sqlite3 直接查询。

## 三、让 AI 分析 VTune 数据的最佳工作流

### 推荐工作流

**步骤 1**：在项目 CLAUDE.md 中加入 VTune 分析上下文：
```markdown
## VTune Analysis Context

VTune results location: C:\Users\Ambition\Desktop\VTun\GSTM_DS_vtune
VTune CLI: "C:\Program Files (x86)\Intel\oneAPI\vtune\2026.1\bin64\vtune.exe"
Target: GangstarServer (UE5 Linux Dedicated Server)

When analyzing VTune data:
1. First run `vtune -report summary` to get overview
2. Then `vtune -report hotspots -format csv` for top functions
3. Use `vtune -report top-down` for microarchitecture bottlenecks
4. Compare results with `vtune -report hotspots -compare-with`
```

**步骤 2**：对话中直接请求分析：
```
分析 r010hs 的热点数据，找出 CPU 消耗最高的函数，给出优化建议
```

**步骤 3**：对比分析多个结果：
```
对比 r010hs 和 r354hs 的性能差异，哪些函数变慢了
```

### 使用 --system-prompt 定制分析角色

```bash
claude -p --system-prompt "You are a performance engineer specializing in Intel VTune analysis and UE5 game server optimization. Always reference exact function names and source locations." "Analyze the hotspots in r010hs"
```

## 四、注意事项与限制

| 项目 | 说明 |
|------|------|
| Bash 输出上限 | 30,000 字符，超长 CSV 会被截断保存到文件供后续 Read |
| MCP 输出上限 | 默认 25,000 tokens，可通过 `MAX_MCP_OUTPUT_TOKENS` 环境变量调大 |
| 长时间命令 | 新采集用 `run_in_background` 避免阻塞 |
| 安全分类器 | 需要在 settings 中显式允许 vtune 相关的 Bash 命令 |
| CSV 最适合 AI | CSV 格式结构化程度高，AI 分析效率最好 |

## 五、调研来源

- [Claude Code MCP 文档](https://code.claude.com/docs/en/mcp)
- [Claude Code 工具文档](https://code.claude.com/docs/en/tools)
- [Claude Code CLI 用法](https://code.claude.com/docs/en/cli-usage)
- [MCP Server 开发快速入门](https://modelcontextprotocol.io/quickstart/server)
- [MCP Server 概念](https://modelcontextprotocol.io/docs/learn/server-concepts)
