# writing — 厦门灯塔博客项目

> 项目级上下文文件。在此目录下工作时自动加载。

## 项目概览

厦门灯塔的 Astro 6 博客站点，托管于 GitHub Pages (custom domain: williamwriting.com)。

**用途：** 英语作文批改技巧、学习方法论、考试策略的英文/中文内容发布。

## 技术栈

| 层 | 技术 | 备注 |
|----|------|------|
| 框架 | Astro 6 | `npm run dev` (port 3000), `npm run build` |
| 内容 | Markdown + frontmatter | `src/content/blog/` |
| Schema | title, pubDate, description, author(opt) | `src/content.config.mjs` |
| 部署 | GitHub Actions → GitHub Pages | push 到 main 自动触发 |
| 域名 | williamwriting.com | CNAME 配置在 GitHub Pages |

## 内容工作流

```
~/Desktop/Daily/ 中的 TXT 文件
    → 转为 markdown，写入 src/content/blog/{slug}.md
    → frontmatter 必须包含 title, pubDate, description
    → git commit → git push origin main
    → GitHub Actions 自动构建并部署
```

### Frontmatter 格式

```yaml
---
title: "文章标题"
pubDate: 2026-05-24
description: "一句话描述，用于SEO和公众号摘要"
author: "威廉"  # 可选
---
```

### 文件命名规范
- slug 用英文小写 + 连字符（如 `gaokao-continuation-full-guide.md`）
- 中文教育类文章 slug 用中文拼音或英文（如 `ai批改vs人工逐句精批.md`）
- FT 双语系列 slug 以 `ft-` 开头（如 `ft-03-nyc-salad-chains-digital-shift.md`）
- 每日10篇生成的源文件以 `blog_读《金融时报》学英文写作_` 开头（如 `blog_读《金融时报》学英文写作_词汇升级.txt`）

## 公众号推送管道（已暂停）

> **2026-05-26 策略变更：** 停止博客文章推送公众号。公众号改为发布「虚拟教辅资料」产品介绍文章，通过加微信（linstudio799）销售¥99的电子资料。不再使用草稿箱推送API。

blog 文章发布后，原通过以下脚本推送到微信公众平台草稿箱（当前已停用）：

| 脚本 | 用途 | 说明 |
|------|------|------|
| `scripts/cron-push-runner.py` | 主推送脚本 | 读取 blog 目录 → 转 HTML → 推草稿箱（已停用） |
| `scripts/cron-push.py` | 旧版推送 | 已迁移到 runner（已停用） |
| `scripts/cron-push-new.py` | 新版推送 | 动态查找未推送文章（已停用） |
| `scripts/wechat-push-cron.py` | cron 版推送 | 含状态管理（已停用） |
| `scripts/push-draft.py` | 手动推送 | 指定 slug 推送（已停用） |
| `scripts/md-to-wechat-html.py` | markdown→HTML | 转换器 |

**凭据：** 从 `.env` 中读取 `WECHAT_APPID` 和 `WECHAT_APPSECRET`（不在代码中硬编码）。`.env` 已加入 `.gitignore`。

**推送状态：** 保存在 `.hermes-heartbeat/draft-push-state.md`，避免重复推送。

## Cron 工作流

| 工作流 | 时间 | 说明 |
|--------|------|------|
| 博客心跳 | 每30分钟 0-6点 | 检查并发布待处理的博客 |
| 读《金融时报》学英文写作 × 每日10篇 | 每天1:00 | 从225篇FT双语素材生成10篇写作技巧文章，保存为 blog_读《金融时报》学英文写作_*.txt |
| FT 双语系列 | 每天0:00/6:00 | 从FT双语阅读生成英文写作文章 |
| 七年爬藤笔记 | 每天3:00 | 提取公众号教育观点 |
| Blog → 公众号草稿箱 | 🚫 已暂停 | 不再推送博客内容到公众号，改为虚拟资料销售模式 |

## 部署

- **自动部署：** push 到 main 分支 → GitHub Actions build → GitHub Pages
- **无需手动干预**
- build 命令：`npm run build`（输出到 dist/）

## 开发命令

```bash
npm run dev    # 本地开发 (localhost:3000)
npm run build  # 静态构建
npm run preview # 预览构建结果
```

## AI 工作规范

1. **写入 markdown 文件前**，先检查该 slug 是否已存在（避免覆盖）。
2. **FT 系列文章名保持 `ft-{序号}-{英文关键词}` 格式**，序号从已有文件递增。
3. **所有推送脚本使用 env 变量**，不在代码中写死凭据。
4. **修改推送脚本后**，在本地跑一次 `python3 scripts/cron-push-runner.py --dry-run` 测试（如有 dry-run 模式）。
5. **不要修改 `.hermes-heartbeat/` 下的状态文件**——这些由 cron 任务管理。

## 页面结构

| 页面 | 文件 | 说明 |
|------|------|------|
| 首页 | `src/pages/index.astro` | 品牌首页，含 Organization/Person/FAQPage schema |
| 博客列表 | `src/pages/blog/index.astro` | 全量文章列表，搜索+分页 |
| 文章页 | `src/pages/blog/[slug].astro` | 单篇文章，含 Article/BreadcrumbList schema |
| 关于 | `src/pages/about.astro` | 品牌介绍 |
| FT 专题页 | `src/pages/ft.astro` | 读《金融时报》学英文写作 专属聚合页，深蓝色调 |

### FT 专题页规则
- **收录：** slug 以 `ft-` 开头 或 标题包含「读《金融时报》」「读外刊学写作」
- **设计：** 深蓝渐变头图 + 搜索筛选 + FT精选/写作课标签
- **导航：** `src/components/Navbar.astro` 中新增「FT双语」入口
- **增长：** 每天 cron 生成的 FT 相关文章自动流入
