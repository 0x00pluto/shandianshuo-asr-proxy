# Document index

## Index

- `README.md`: 项目用法入口：装 UV、`uv sync`、启动代理、闪电说 Chat 音频对照控制台摘要
- `docs/builtin-workflows/post-task-reflect.md`: 任务后反思（白痴指数 → 删 → 程序化 → 鲁棒 → 加速）；用户明确要求时触发，不自动跑
- `docs/builtin-workflows/extract-experience.md`: 提取经验 → 项目无关最佳实践；用户明确要求时触发；落盘须问或读 experience_target，默认本仓 docs/best-practices/
- `docs/builtin-workflows/write-memo.md`: 写备忘：本仓稳定约束落盘；仅用户明确要求「写成备忘 / 记进 memos」时触发
- `docs/builtin-workflows/consolidate-memory.md`: 记忆巩固与遗忘（冲突消解 → 情景提纯 → 剪枝）；仅用户显式触发
- `docs/builtin-workflows/publish-evo-agent-pack.md`: 仅首次 / 改合同时发布或核对 evo_agent_pack.json 工牌；日常发版勿进门；打 tag 改走 cut-release-tag；不做安装器
- `docs/builtin-workflows/cut-release-tag.md`: 日常发版唯一入口；汇总变更 → upgrades → 对齐 version → tag → 推送 → gh 或网页建 Release；major 须人指定
- `docs/memos/_TEMPLATE.md`: 备忘 frontmatter + 正文骨架（不占序号）
- `docs/memos/memo-wiki-index.md`: Memo 索引（不计入五位序号）；下一号 00001
- `docs/workflows/asr-proxy.md`: 无参启动转写代理（SenseVoice/Whisper 二选一本地兜底）；默认端口 18888；结构化日志见 `temp/logs/asr-proxy.log`
- `.env.example`: 豆包密钥环境变量模板（入库）；本机复制为 gitignore 的 `.env`
- `configs/proxy.json`: 对外端口（默认 18888）、local 引擎意图、whisper 路径/超时、日志（入库）
- `configs/premium.json`: 高级模型出厂行为配置（入库，无密钥）
- `docs/faqs/`: 一次踩坑 FAQ；记录与检索用技能 `huyuan-ai-dev-faq-assistant`
- `docs/faqs/how-to-fix-sensevoice-deps-with-uv-sync.md`: SenseVoice 依赖用 `uv sync` 一条装齐；启动不自动装包
- `docs/faqs/how-to-fill-shandianshuo-when-config-not-written.md`: 闪电说配置「未写入」时按摘要四项手填 Chat 音频

- `specs/prds/prd-wiki-index.md`: PRD 索引（不占序号）；下一号 00003
- `specs/prds/prd-00001-dual-write.md`: 本地与高级模型并行双写（豆包优先）；已实现
- `specs/prds/prd-00002-local-fallback.md`: 本地兜底 SenseVoice / Whisper 二选一；启动探测与闪电说配置对齐；accepted
- `.cursor/commands/team/product-manager.md`: 产品经理；`/team:product-manager`
- `.cursor/commands/team/backend-engineer.md`: Python 开发工程师（标准库 HTTP 代理）；`/team:backend-engineer`
- `.cursor/commands/team/prd-accept.md`: 工程验收官；`/team:prd-accept`
- `.cursor/commands/team/feature-dev.md`: 自主交付工程师（S1→S2→S3）；`/team:feature-dev`
- `.cursor/commands/team/test-enginer.md`: 测试工程师（真实环境端到端验收）；`/team:test-enginer`
