# 高中地理热点周报配置

本仓库已加入高中地理热点筛选配置和周报候选生成脚本。

## 默认行为

- AI 筛选兴趣文件：`config/custom/ai/high_school_geography.txt`
- 关键词兜底文件：`config/custom/keyword/high_school_geography.txt`
- AI 分析提示词：`config/geography_weekly_prompt.txt`
- 权威信源入口：按候选主题自动匹配中国气象局、自然资源部、水利部、国家统计局等官网
- 权威 RSS 数据池：默认启用国家统计局“最新发布”和“数据解读”RSS；不进入 AI 分析，不增加推送噪声
- 课标依据：默认读取 `D:\BaiduNetdiskDownload\普通高中地理课程标准（2017年版2020年修订).pdf`
- 周报候选输出：`output/geography/YYYY-MM-DD-weekly-geography.md`
- 结构化输出：`output/geography/YYYY-MM-DD-weekly-geography.json`
- “切入角度”输出：每条热点区分 `课堂/备课`、`内容创作`、`核验边界`，可同时服务课堂案例设计、公众号/知乎选题参考和正式成稿前的事实核查
- 分类边界：排除以股指、股价、比特币等为主的市场行情标题；保留 AI 产业、算力中心、数据中心、半导体产业等具有产业地理价值的新兴产业内容
- 文件投递：GitHub Actions 会上传 `geography-weekly-report` artifact；如配置邮箱 Secrets，会同时发送 Markdown 和 JSON 附件

GitHub Actions 中的 `Get Hot News` 会在每天北京时间 24:00（次日 00:00）抓取热榜，并把 `output/news/*.db` 与 `output/rss/*.db` 提交回仓库，用于积累滚动数据。每日抓取步骤会显式关闭普通热榜通知，不会发送普通热点邮件；每周三北京时间 24:00 会在抓取后额外生成地理周报候选并发送邮件。手动运行 workflow 时会直接生成周报，方便测试。

## 手动生成

```bash
python -m trendradar.report.geography_weekly --days 7 --limit 15 --format both
```

使用仓库内置样例数据测试：

```bash
python -m trendradar.report.geography_weekly --end-date latest --days 7 --limit 15 --format both
```

指定课标 PDF：

```bash
python -m trendradar.report.geography_weekly --curriculum-pdf "D:\BaiduNetdiskDownload\普通高中地理课程标准（2017年版2020年修订).pdf"
```

也可以通过环境变量指定：

```bash
GEOGRAPHY_CURRICULUM_PDF=/path/to/curriculum.pdf python -m trendradar.report.geography_weekly
```

## 邮件投递

每周报告生成后，workflow 会自动尝试发送邮件附件。邮箱 Secrets 只在周报邮件步骤中使用，不会注入每日抓取步骤；未配置邮箱时会跳过，不影响周报生成和 artifact 上传。

在 GitHub 仓库中进入 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`，添加：

| Secret | 必填 | 说明 |
|---|---|---|
| `EMAIL_FROM` | 是 | 发件邮箱 |
| `EMAIL_PASSWORD` | 是 | 邮箱授权码或 SMTP 密码 |
| `EMAIL_TO` | 否 | 专用周报邮件已固定发送至 `1426056128@qq.com`；如需改收件人，再修改 workflow 中的 `EMAIL_TO` |
| `EMAIL_SMTP_SERVER` | 否 | 自定义 SMTP 服务器 |
| `EMAIL_SMTP_PORT` | 否 | 自定义 SMTP 端口，465 为 SSL，其他默认 STARTTLS |

本地测试邮件附件发送：

```bash
EMAIL_FROM=sender@example.com EMAIL_PASSWORD=app-password EMAIL_TO=you@example.com \
python -m trendradar.report.email_geography_weekly --report-dir output/geography
```

## 注意事项

生成脚本负责“热点与课标匹配”“切入角度区分”和“权威核验入口匹配”。热榜链接只能证明话题热度，不能证明科学解释正确。正式用于课堂、公众号、知乎或其他内容成稿前，仍需打开对应官网或正规媒体页面，核对具体事件事实、数据口径和发布时间；缺少具体权威页面时，不应生成确定性的科学说明。
