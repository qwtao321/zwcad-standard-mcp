# Tool Design: 从用户场景倒推 MCP 能力

## 1. 设计原则

### 不暴露万能反射工具

禁止提供以下形式：

```text
invoke_com_method(class_name, method_name, args)
execute_command(command_string)
```

原因：权限边界过大、参数不可校验、结果难审计、模型选择不稳定。

### 使用中等粒度、批量优先

推荐：

```text
update_entity_properties(handles, properties)
update_block_attributes(updates)
create_entities_batch(entities)
plot_layouts(layout_names, output_dir)
```

这些 Tool 既能被 Skill 编排，又不会把每个对象拆成大量 MCP 往返。

### 先读后写

每个高风险场景采用：

```text
诊断 → 查询 → dry_run 预览 → 用户确认 → 执行 → 再读取验证
```

## 2. 场景与依赖工具

### 场景 A：陌生图纸快速盘点

目标：用户收到供应商图纸后快速了解图层、实体、块和布局。

工具：

- diagnose_cad
- get_current_document
- audit_drawing
- list_layers
- list_block_references
- list_layouts

### 场景 B：导入对象图层和属性归一化

目标：解决对象全部在 0 层、颜色固定、线型不随层。

工具：

- get_selected_entities
- ensure_layers
- normalize_selected_entities
- update_entity_properties
- get_entity_details

### 场景 C：参数化生成简单图形

目标：减少矩形板、孔阵列、文字和尺寸的重复绘制。

工具：

- ensure_layers
- create_entities_batch
- get_entity_details

### 场景 D：多布局批量出图

目标：减少逐个切换布局和命名 PDF 的操作。

工具：

- get_current_document
- list_layouts
- plot_layouts

### 场景 E：标准版标题栏批量维护

目标：处理各布局中的属性块标题栏。

工具：

- list_block_references
- get_block_attributes
- update_block_attributes
- save_document

## 3. 暂不纳入首版

- 任意 CAD 命令字符串执行
- 图层删除和强制清理
- XREF 绑定、拆离和路径修复
- 动态块参数编辑
- 布尔运算和复杂 3D 建模
- 任意对象反射式属性写入
- 自动保存覆盖原文件

这些能力要么风险高，要么需要更明确的用户场景和实机兼容验证。
