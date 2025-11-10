# DingZhenSpider – Bilibili 视频采集与统计（路线A）

本项目基于公开 Web 接口（popular、ranking）采集 B 站视频数据，支持保存到 CSV 与 SQLite，并生成基础统计报表。

注意：本实现优先使用无需 WBI 的公开接口，适合作为热门与排行榜的快速采集方案。若后续需要搜索、UP 主投稿等，需要适配 WBI 签名或改用 SDK/APP 接口。

## 功能
- popular 热门分页采集（pn/ps）
- ranking 排行（全站或分区 rid，day=1/3/7）
- 输出 CSV 与 SQLite（按 bvid 去重，支持更新）
- 统计与报表（总播放/点赞、TopN）

## 快速开始
1. 创建与激活虚拟环境（Windows PowerShell）：
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. 安装依赖：
   ```powershell
   pip install -r requirements.txt
   ```
3. 运行（示例）：
   - 抓取热门前 10 页（每页 20 条，默认）：
     ```powershell
     python main.py popular --pages 10 --ps 20
     ```
   - 抓取全站排行榜 day=3：
     ```powershell
     python main.py ranking --day 3 --rid 0
     ```

数据将保存到 `data/` 目录，并生成 `summary.csv` 与 TopN 报表。

## 配置
- 在 `config.yaml` 中可配置输出目录、代理、限速等；命令行参数可覆盖配置文件。

## 法律与合规
- 仅用于学习与研究，请遵守目标网站的服务条款与相关法律法规。
- 请合理控制抓取频率，避免对站点造成压力。
