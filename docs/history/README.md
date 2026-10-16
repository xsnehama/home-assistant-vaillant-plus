# 2026-10-15 物证重建说明

提交者时间为本次恢复时间；重建提交的作者时间取该快照源码文件的最大 mtime，不代表最初编写、部署或验证时间。所有恢复提交均带 `[reconstructed]`、来源路径及依赖版本的证据范围。父子关系仅表示恢复过程中的比较关系。

| 状态 | 可核对的物证 | 结论 |
|---|---|---|
| c1 | 真正的上游 `v1.2.4` 标签；`/root/vp2/v124` | 上游基线 |
| c2 | `.codex_backups/vaillant_plus.backup-20260606-params-unavailable` | `binary_sensor.py` 已有三行防御性修改，并非纯上游 |
| c3 | `vaillant_plus_user_backup/`；`/root/vp-HANDPATCH.diff` | 7 月 4 日备份的定制源码；`.bak` 与 `.bak2` 内容相同，未另造状态 |
| c4 | `ha-config-text-20261015-1300.tar.gz` 的组件文件；更新前完整组件备份 | 两份逐字节一致，manifest 为 1.2.5 |
| c5 | `vaillant_plus_restore_backups/vaillant_plus_upstream_v1.4.0_before_restore_20260901_090945`；真正的上游 `v1.4.0` 标签 | 源码与上游一致，缺少定制；物证不能单独证明当时回退的动机 |
| c6 | `vaillant_plus-before-post2-20261015-172137/original-post1`；原会话提交 `1dad169`；`/root/vp-POST1.diff` | 1.4.0.post1，快照与原提交规范行尾后相同 |
| c7 | 当前部署；原会话提交 `77e1146` | 1.4.0.post2，17 个源码文件与部署逐字节一致 |

```text
真实上游 v1.2.4 ─ c2 ─ c3 ─ c4 ─────────── c6 ─ c7
真实上游 v1.4.0 ─ c5（9 月独立物证）────────┘
```

这不是伪造的原始开发时间线：c4 的现存物证采集于 10 月，c5 的备份名称指向 9 月，因此 c5 单列后作为 c6 的比较来源。c6 的两个父提交记录选择移植的证据来源，不声称当时真的执行过 Git merge。

明确空缺：

- `no artifact for this period: 2026-07-04 to 2026-09-01`：未恢复期间每次中间修改和部署顺序。
- `no artifact for this period: 2026-09-01 to 2026-10-15`：未恢复当前 1.2.5 定制树形成前的中间修改和部署顺序。

当前部署依赖：Home Assistant `2026.10.1`，`vaillant-plus-cn-api` 使用 fork `xsnehama/vaillant-plus-cn-api` 的 `v2.1.2`（提交 `5f9b107`）。旧快照只有 manifest 声明的依赖，未将当前 HA 版本冒充成历史运行版本。涉及 `utils.py` 的库私有方法和 HA 兼容分支时，应结合提交内依赖说明审阅。

上游同步记录：上游 `da2fdf8`（diagnostics 中报告 product family）不是当前维护分支的祖先；其 `platform` 和 `sub_product_key` 字段已在当前重写版 `diagnostics.py` 中保留。后续同步应以字段行为比对，不要直接覆盖该文件。

原始 diff（591 行、2300 行）保留在 NAS `/root`，另存私有副本 `/root/vaillant-evidence-20261015`。本仓库提交哈希和来源清单，原始 diff 不用来替代完整源码快照。所有已存在的备份均保留。
