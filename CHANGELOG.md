# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 与
[语义化版本](https://semver.org/lang/zh-CN/)。

## [1.2.0] - 2026-10-27

基于 [muyikk/astrbot_plugin_hextechmayhem v1.1.1](https://github.com/muyikk/astrbot_plugin_hextechmayhem)
的改造版（fork）。

### 新增

- **`/海斗胜率`**：按真实胜率输出「胜率最高 TOP N」与「胜率最低 BOTTOM N」双向榜单，
  两端各自高亮，并展示胜率、登场率、场次与强度档位。
  - 只统计上游确实提供了 `winRate` 的英雄，缺失胜率者不参与排序。
  - 样本不足时会从中位数切开，避免同一英雄同时出现在两端。
  - 新增配置 `winrate_rank_size`（默认 `10`，有效范围 3–50）。
- **海克斯胜率与选取率**：`/海克斯` 与 `/海斗 <海克斯名>` 现在展示每个强化的
  胜率、选取率和场次，并在页脚标注统计来源与汇总范围。
  - 上游没有统计的条目只显示图标与描述，不补 `0`。
- **`/海斗 <查询>` 智能识别**：先按英雄目录匹配；英雄未命中时自动按海克斯名检索，
  命中则直接输出海克斯卡片，无需记住两套指令。
- 服务层新增 `champion_winrate_rankings()` 与 `augment_winrate_rankings()`。
- 新增 12 个测试，覆盖胜率榜分组、样本不足对半切、无胜率数据、海克斯统计解析与渲染。

### 修复

- **依赖冲突导致无法安装**：`requirements.txt` 中的 `Pillow>=11.1,<13` 与 AstrBot
  「核心依赖版本保护」锁定的 `pillow==13.0.0` 无交集，安装时报
  `DependencyConflictError: A core dependency version protection conflict was detected`。
  现改为 `Pillow>=11.1`（去掉上界）。插件只使用 Pillow 稳定核心 API，在 11/12/13 上行为一致。

### 变更

- `metadata.yaml` 版本号提升至 `v1.2.0`，补充 `repo` 占位说明与 `胜率榜` 标签。
- README 重写：新增「胜率数据可信度说明」，明确区分 `/海斗排名`（官方综合档位）
  与 `/海斗胜率`（纯胜率排序）。
- 新增 GitHub 标准文件：`CHANGELOG.md`、`CONTRIBUTING.md`、`pyproject.toml`、
  `.github/workflows/ci.yml`、Issue / PR 模板。

### 不兼容变更

无。原有 `/海斗`、`/海克斯`、`/海斗排名` 三条指令的行为与输出保持不变，
新增的统计展示只在上游返回数据时出现。

## [1.1.1] - 上游版本

原始实现作者 muyikk。功能见上游仓库：

<https://github.com/muyikk/astrbot_plugin_hextechmayhem>
