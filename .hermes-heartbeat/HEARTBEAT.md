# Work Heartbeat — 厦门灯塔 Blog Agent

这是 Hermes Agent 的 Work Heartbeat 指令集。每次 cron 唤醒后，按此流程执行。

## 每次醒来必须做

1. 读取本项目所有状态文件
2. 检查 `~/Desktop/Daily/` 是否有新 blog 内容或待处理 TXT
3. 推进一个实际工作单元（不能只输出计划）
4. 更新状态文件
5. 写运行日志

## 必须遵守的规则

- **不要只输出计划**。只要没有阻塞，就必须推进一个实质产出：写 blog post、改文案、发布、或研究内容
- **Blog 自动发布**：如果有 `blog_*.txt` 在 `~/Desktop/Daily/`，运行 `python3 ~/.hermes/scripts/blog_auto_publish.py`
- **QQ 空间写作**：如果有 `qq_*.txt` 在 `~/Desktop/Daily/`，分析内容→生成 blog 文章→发布
- **每轮只需要推进一件事**。不要试图一次做完所有事
- **如果无事可做**：检查是否需要 GEO 优化、SEO 更新、相关文章添加、或内容整理
- **如果被阻塞**：在 run-state.md 里明确记录阻塞原因

## 项目信息

- Blog 路径: `/Users/william/writing/`
- 内容源: `~/Desktop/Daily/`（TXT 文章草稿、作文批改、公众号文案）
- Blog 博客文章: `src/content/blog/`
- 自动发布脚本: `~/.hermes/scripts/blog_auto_publish.py`
- 部署: GitHub Pages → williamwriting.com
- 品牌色: #E67E60 (橙) / #FFF8EF (米白) / #222
