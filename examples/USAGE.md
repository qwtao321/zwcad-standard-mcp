# Agent 使用示例

## 1. 图纸快速检查

用户：

> 帮我看一下当前图纸有多少图层、主要有哪些对象、有哪些带属性的块，但不要修改。

推荐调用：

1. diagnose_cad
2. audit_drawing
3. list_block_references(scope="all_layouts", has_attributes=true)

## 2. 归一化选择对象

用户先在 CAD 中选中对象，然后说：

> 把这些对象放到 OUTLINE 层，并统一为 ByLayer，先给我预览。

调用：

```json
{
  "target_layer": "OUTLINE",
  "set_color_bylayer": true,
  "set_linetype_bylayer": true,
  "dry_run": true
}
```

用户确认后，将 `dry_run` 改为 `false`。

## 3. 批量更新标题栏属性

先查询：

```json
{
  "scope": "all_layouts",
  "block_name": "A3_TITLE_BLOCK",
  "has_attributes": true,
  "limit": 50
}
```

读取属性后，预览更新：

```json
{
  "updates": [
    {
      "handle": "3AF",
      "attributes": {
        "DESIGNER": "张三",
        "CHECKER": "李四",
        "DATE": "2026-07-21"
      }
    }
  ],
  "dry_run": true
}
```

确认无误后执行，再调用 `get_block_attributes` 验证。

## 4. 多布局出图

```json
{
  "layout_names": ["A01", "A02", "A03"],
  "output_dir": "D:\\Project\\PDF",
  "plot_configuration": "DWG To PDF.pc3",
  "extension": "pdf",
  "dry_run": true
}
```
