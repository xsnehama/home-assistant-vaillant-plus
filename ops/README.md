# 维护与部署

仓库位于 NAS `/root/vaillant_plus`，保留上游完整目录结构，便于直接比较上游。
部署源为 `custom_components/vaillant_plus/`；现网目录仅存组件文件。

```sh
cd /root/vaillant_plus
git fetch --tags upstream
git diff --stat v1.4.0 -- custom_components/vaillant_plus
python3 ops/check_deployment.py
sh ops/deploy.sh --dry-run
# 审阅并提交修改后，需要部署时执行：
sh ops/deploy.sh --apply
```

漂移检查逐文件比较 SHA-256，忽略 Python 缓存；工作树不干净、文件不同或部署目录含 `.git` 时返回非零退出码并列出文件名，可接入已有告警系统。本次只提供并执行检查命令，未设置定时任务。

部署命令只同步组件子目录，执行前在 `/root/vaillant-deploy-backups` 保存组件副本和提交号，执行后校验。不自动重启 HA。

`.gitattributes` 将 Python 文件固定为 LF。历史导入时同样规范行尾；原始字节哈希记录在 `docs/history/provenance-20261015.json`。

本仓库不收录 HA 配置、`.storage`、数据库、凭据或 HA 备份。配置另由 `/root/ha-config` 的白名单仓库维护。

原有会话提交另保留于 `archive/session-20261015`。上游标签 `v1.2.5` 与 fork 原有同名标签指向不同提交；NAS 本地的普通版本标签均来自 upstream，fork 原始提交由 `origin/master` 和归档分支保留。不要把所有本地标签强推回 fork。

维护分支的最终归档提交另以原会话提交为第二父提交，使重建图和原提交链均可从该分支追溯。GitHub 只推送维护分支；`evidence/c1` 到 `evidence/c7` 标签保留在 NAS 和离线 bundle，克隆后也可通过 provenance 中的完整提交号查看对应状态。
