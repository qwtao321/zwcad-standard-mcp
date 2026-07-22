# ZWCAD Standard MCP

面向 **中望 CAD 标准版** 的本地 MCP Server。它不是为了把所有 COM 方法机械地暴露给大模型，而是围绕 CAD 用户常见痛点，提供一组中等粒度、可批量、可预览、可验证的工具。

底层使用 ZWCAD 对外公开的 ActiveX/COM API，通过 `pywin32` 连接本机正在运行的 ZWCAD；MCP 层使用官方 Python SDK。

> 本项目不包含中望机械版的图框、机械标题栏、BOM、球标、机械标准环境等专有能力。

## 解决的用户问题

| 用户痛点 | 对应能力 |
|---|---|
| AI 连不上 CAD、版本和当前图纸不明确 | `diagnose_cad`、`get_cad_app_info`、`get_current_document` |
| 收到陌生 DWG，不知道图层、对象和块的整体情况 | `audit_drawing`、`list_layers`、`query_entities`、`list_block_references` |
| 外部导入图纸全部在 0 层，颜色和线型不随层 | `normalize_selected_entities`、`ensure_layers`、`update_entity_properties` |
| 需要批量读取、修改或变换一组对象 | `get_selected_entities`、`get_entity_details`、`transform_entities` |
| 重复绘制简单几何、文字和常用标注 | `create_entities_batch` |
| 多个布局逐个切换和出 PDF，或整个文件夹批量出图 | `list_layouts`、`plot_layouts`、`create_batch_job`、`scan_cad_folder` |
| 标准版标题栏是属性块，需要批量检查和填写 | `list_block_references`、`get_block_attributes`、`update_block_attributes` |
| 操作风险高，担心误改或误删 | 写工具默认 `dry_run=true`、每次调用授权（`confirm`）、删除/保存二次确认、Undo Mark |

## 工具清单（33 个）

### 系统诊断

- `diagnose_cad`
- `get_cad_app_info`
- `audit_drawing`

### 文档

- `get_current_document`
- `list_documents`
- `activate_document`
- `save_document`

### 图层

- `list_layers`
- `ensure_layers`

### 对象读取与修改

- `get_selected_entities`
- `query_entities`
- `get_entity_details`
- `update_entity_properties`
- `normalize_selected_entities`
- `transform_entities`
- `delete_entities`

### 基础绘图

- `create_entities_batch`

支持：直线、圆、圆弧、轻量多段线、单行文字、多行文字、图块、对齐/旋转/半径/直径标注。

### 布局与出图

- `list_layouts`
- `activate_layout`
- `get_layout_plot_settings`
- `plot_layouts`
- `export_drawing`
- `verify_export_files`

### 图块

- `list_block_definitions`
- `list_block_references`
- `get_block_attributes`
- `update_block_attributes`
- `insert_blocks_batch`

### 文件管理

- `scan_cad_folder`
- `open_document`
- `close_document`
- `create_batch_job`
- `get_batch_job_status`

> 文件夹级批量出图：先用 `scan_cad_folder` 列出目标目录的全部 CAD 文件，再 `create_batch_job(operation="plot_pdf", files=[...], output_dir=..., config={"plot_configuration": "DWG to PDF.pc5", "extension": "pdf"})` 在后台线程逐个只读打开、出 PDF、关闭；`get_batch_job_status` 轮询进度。批量任务在独立 COM 适配器实例中运行，不与交互会话争用主线程。

## 安全默认值

1. **默认预览、按调用授权**：本版本已移除启动期的全局写入开关（`ZWCAD_MCP_ALLOW_WRITE` 不再生效）。所有写工具默认 `dry_run=true` 只给变更预览；真实执行需要在**每次调用**传入 `confirm=true`（删除还需 `second_confirm=true`、保存还需 `file_path`）。无需重启服务即可在只读与可写之间切换。
2. **写工具默认预览**：所有批量修改、绘图、出图和导出工具默认 `dry_run=true`。
3. **删除二次确认**：执行删除必须同时传 `dry_run=false` 和 `confirm=true`。
4. **保存二次确认**：保存必须传 `confirm=true`。
5. **批量限制**：默认每次最多处理 200 个写入对象、查询最多返回 500 个对象。
6. **撤销分组**：批量 CAD 修改会尽量放入一次 Undo Mark 中，便于用户在 ZWCAD 内撤销。

## 环境要求

- Windows 10/11
- 已安装中望 CAD 标准版，并开放 ActiveX/COM 自动化接口
- 启动 ZWCAD 并打开至少一个 DWG
- Python 3.10+

默认 COM ProgID：

```text
ZWCAD.Application
```

某些版本或安装环境如使用不同 ProgID，可通过 `ZWCAD_MCP_PROG_ID` 修改。

## 安装

### 一键安装

双击：

```text
install.bat
```

安装完成后，先启动 ZWCAD 并打开 DWG，再运行：

```text
start.bat
```

### 命令行安装

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e .
python -m zwcad_standard_mcp.server
```

## MCP 客户端配置

复制 `mcp-config.example.json` 并修改本机绝对路径：

```json
{
  "mcpServers": {
    "zwcad-standard": {
      "command": "D:\\path\\to\\zwcad-standard-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "zwcad_standard_mcp.server"],
      "env": {
        "ZWCAD_MCP_PROG_ID": "ZWCAD.Application",
        "ZWCAD_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

本版本采用「每次调用授权」模型，无需在配置里预设写入开关，也无需重启服务来切换读写：

- 只读操作（`diagnose_cad` / 读取 / 查询 / 图层列表）随时可用。
- 写操作先以 `dry_run=true` 看预览；确认无误后在**同一次调用**加 `dry_run=false, confirm=true` 真正执行。
- 删除需 `confirm=true` 且 `second_confirm=true`；保存需 `confirm=true` 并提供 `file_path`。

## 推荐验证顺序

### 第 1 阶段：只读连通

1. `diagnose_cad`
2. `get_current_document`
3. `audit_drawing`
4. `list_layers`
5. `get_selected_entities`

### 第 2 阶段：低风险修改

1. 在 ZWCAD 中复制一份测试图纸。
2. 选中少量对象。
3. 调用 `normalize_selected_entities(dry_run=true)`。
4. 检查预览。
5. 开启写入后调用 `dry_run=false`。
6. 在 ZWCAD 中测试一次 Undo。

### 第 3 阶段：标准版标题栏

1. `list_block_references(has_attributes=true)` 找到标题栏块。
2. `get_block_attributes` 读取属性 TAG。
3. `update_block_attributes(dry_run=true)` 预览。
4. 用户确认后用 `dry_run=false` 执行。
5. 再次读取属性验证。

### 第 4 阶段：文件夹级批量出图

1. `scan_cad_folder(path="目标目录")` 列出全部 DWG/DXF/DWT。
2. `create_batch_job(operation="plot_pdf", files=[...], output_dir=".../Publish", config={"plot_configuration": "DWG to PDF.pc5", "extension": "pdf"}, confirm=true)` 创建并执行批量任务。
3. `get_batch_job_status(job_id=...)` 轮询进度。
4. `verify_export_files(file_paths=[...])` 校验产物。

## 示例

### 归一化当前选中对象

```json
{
  "target_layer": "OUTLINE",
  "set_color_bylayer": true,
  "set_linetype_bylayer": true,
  "dry_run": true
}
```

### 批量绘制矩形和孔

```json
{
  "entities": [
    {
      "entity_type": "lwpolyline",
      "layer": "OUTLINE",
      "params": {
        "vertices": [[0, 0], [300, 0], [300, 200], [0, 200]],
        "closed": true
      }
    },
    {
      "entity_type": "circle",
      "layer": "HOLE",
      "params": {"center": [25, 25, 0], "radius": 5}
    }
  ],
  "dry_run": true
}
```

### 更新标准版标题栏属性块

```json
{
  "updates": [
    {
      "handle": "3AF",
      "attributes": {
        "DESIGNER": "张三",
        "DATE": "2026-07-21"
      }
    }
  ],
  "dry_run": true
}
```

## 配置项

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `ZWCAD_MCP_PROG_ID` | `ZWCAD.Application` | COM ProgID |
| `ZWCAD_MCP_AUTO_START` | `false` | 找不到运行实例时是否自动启动 ZWCAD |
| `ZWCAD_MCP_MAX_QUERY_RESULTS` | `500` | 单次查询最大返回数量 |
| `ZWCAD_MCP_MAX_BATCH_SIZE` | `200` | 单次批量写入最大数量 |
| `ZWCAD_MCP_TRANSPORT` | `stdio` | `stdio` 或 `streamable-http` |
| `ZWCAD_MCP_ADAPTER` | `com` | `com`；测试时可设为 `fake` |
| `ZWCAD_MCP_LOG_LEVEL` | `INFO` | 日志级别 |

## 测试

代码仓库包含不依赖 Windows/ZWCAD 的 Fake Adapter：

```powershell
pip install -e ".[dev]"
pytest
```

本地查看 MCP 工具 Schema 时可使用：

```powershell
set ZWCAD_MCP_ADAPTER=fake
python -m zwcad_standard_mcp.server
```

## 已知边界

- 未在当前生成环境中连接真实 Windows ZWCAD，因此 COM 方法需要在目标 ZWCAD 版本上进行实机验收。
- 不包含机械版专用对象。
- 动态块、嵌套块、外部参照内属性、字段对象、复杂代理对象可能需要后续专项适配。
- `plot_layouts` 依赖当前布局已有可用打印配置；不同企业 PC3、PMP 和纸张配置需实机验证。
- 文件夹级批量任务（`create_batch_job` 传入 `files`）在后台线程中打开图纸并出图；若 ZWCAD 因缺少字体、代理对象或打印配置弹出模态对话框，会阻塞该后台线程，需先在 ZWCAD 中关闭所有弹窗再重试。
- 当前查询以 COM 集合遍历为主，大图纸需要进一步增加索引、选择集过滤和分页。
- Undo Mark 便于用户撤销，但不是数据库级自动事务回滚。

## 项目结构

```text
zwcad-standard-mcp/
├── README.md
├── pyproject.toml
├── install.bat
├── start.bat
├── mcp-config.example.json
├── docs/
├── examples/
├── src/zwcad_standard_mcp/
│   ├── adapters/
│   ├── services/
│   ├── tools/
│   ├── config.py
│   ├── models.py
│   └── server.py
└── tests/
```

## 参考

- ZWCAD Application Development Support: https://www.zwsoft.com/support/zwcad-devdoc
- Official MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- ZWCAD Mechanical MCP reference implementation: https://github.com/john0909/ZWCAD-Mechanical-MCP
