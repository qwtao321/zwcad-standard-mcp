# 实机验收用例

## A. 环境与连接

1. ZWCAD 未启动：`diagnose_cad` 返回 `CAD_CONNECTION_ERROR`。
2. ZWCAD 已启动但未打开 DWG：返回 `NO_ACTIVE_DOCUMENT`。
3. 使用不同版本 ProgID：通过环境变量切换并连接。
4. CAD 关闭重开：下一次调用能重新连接。
5. 多文档打开：`list_documents` 与 `activate_document` 正确。

## B. 安全策略

1. 默认 `ALLOW_WRITE=false` 时，所有写工具拒绝执行。
2. 所有写工具默认 `dry_run=true`。
3. `delete_entities` 缺少 `confirm=true` 时拒绝。
4. `save_document` 缺少 `confirm=true` 时拒绝。
5. 只读文档允许扫描但禁止修改。
6. 超过批量上限时返回 `BATCH_LIMIT_EXCEEDED`。

## C. 图层与对象

1. 列出图层及颜色、线型、锁定和冻结状态。
2. 创建新图层。
3. 更新已有图层。
4. 读取用户预选对象。
5. 按类型和图层查询对象。
6. 批量读取句柄详情。
7. 批量改图层、颜色 ByLayer、线型 ByLayer。
8. 移动、复制、旋转、缩放和镜像。
9. 批量修改后一次 Undo 能撤回。
10. 删除对象先预览再确认。

## D. 绘图

逐一验证：

- line
- circle
- arc
- lwpolyline
- text
- mtext
- block
- dimension_aligned
- dimension_rotated
- dimension_radial
- dimension_diametric

每个结果都应返回可再次查询的句柄。

## E. 布局与出图

1. 列出 Model 和所有 Paper Layout。
2. 正确激活指定布局。
3. 使用企业 PC3 配置输出单个 PDF。
4. 批量输出多个布局，文件命名正确。
5. 某个布局出图失败时，其他布局继续并返回逐项结果。
6. 批量完成后恢复原活动布局。

## F. 图块和标题栏

1. 列出块定义。
2. 跨布局查找带属性的块引用。
3. 正确返回 EffectiveName（动态块需专项验证）。
4. 读取属性 TAG 和文本。
5. dry_run 预览新旧值。
6. 修改存在的 TAG 并重新读取验证。
7. 不存在的 TAG 出现在 `unmatched_tags`。
8. 多个标题栏块批量修改。
9. 常量属性、XREF 内属性和嵌套块不误改。

## G. 大图纸性能

至少选取：

- 1,000 实体图纸
- 10,000 实体图纸
- 100,000 实体图纸

记录：

- audit_drawing 耗时
- query_entities 耗时
- 批量读取 200 个句柄耗时
- COM 内存和稳定性

根据结果决定是否增加 SelectionSet 过滤、分页游标和缓存。
