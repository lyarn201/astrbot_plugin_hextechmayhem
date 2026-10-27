<div align="center">

<h1>海克斯乱斗</h1>

为 AstrBot 提供《英雄联盟》海克斯大乱斗**英雄胜率榜（TOP / BOTTOM）**、英雄完整报告、海克斯强化查询与综合强度排名。

![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.9.2%20%3C5-5865f2?style=flat-square)
![Version](https://img.shields.io/badge/version-v1.2.0-22c55e?style=flat-square)
![Platform](https://img.shields.io/badge/platform-aiocqhttp-f97316?style=flat-square)
![License](https://img.shields.io/badge/license-GPL--3.0-3b82f6?style=flat-square)
![Python](https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square)

<br>
<img src="logo.png" alt="海克斯乱斗 Logo" width="180">

</div>

> [!NOTE]
> 本仓库是 [muyikk/astrbot_plugin_hextechmayhem](https://github.com/muyikk/astrbot_plugin_hextechmayhem) 的改造版（fork），
> 在原版基础上新增 `/海斗胜率` 双向胜率榜、海克斯胜率 / 选取率展示、`/海斗 <海克斯名>` 智能识别，
> 并修复了与 AstrBot 核心依赖保护冲突的 `Pillow` 版本约束。改造说明见 [CHANGELOG.md](CHANGELOG.md)。

## 目录

- [功能一览](#功能一览)
- [快速开始](#快速开始)
- [常用指令](#常用指令)
- [数据来源与展示规则](#数据来源与展示规则)
- [胜率数据可信度说明](#胜率数据可信度说明)
- [图片体积与发送超时](#图片体积与发送超时)
- [推荐配置](#推荐配置)
- [缓存与故障降级](#缓存与故障降级)
- [开发与测试](#开发与测试)
- [依赖](#依赖)
- [声明与致谢](#声明与致谢)

## 功能一览

| 场景 | 能力 |
| --- | --- |
| **胜率榜** | `/海斗胜率` 同屏输出胜率最高 TOP N 与最低 BOTTOM N，按真实胜率排序 |
| **英雄报告** | 英雄封面、强度分档、胜率 / 登场率、推荐海克斯、召唤师技能、技能加点、出装组合 |
| **海克斯查询** | 按中英文关键词模糊查询，展示**胜率、选取率、场次**、稀有度、描述与图标 |
| **智能识别** | `/海斗 <查询>` 先匹配英雄，未命中自动按海克斯名检索，无需记两套指令 |
| 综合排名 | 按信息源提供的官方综合排名与强度档位生成前 10 名图片卡片 |
| ARAMGG 扩展 | 真实流派、完整 18 级技能序列、情境装备、三海克斯组合、热门单件、相关文章 |
| 双信息源 | 默认国内优先 ARAMGG，可切换 OP.GG；两条请求链路相互隔离 |
| 名称识别 | 支持中文名、英文名、内部 ID、数字 ID、无空格英文名与 ARAMGG 别名 |
| 社区路线 | 可选展示 Mayhempedia 维护的真实六件套路线，不使用插件推导内容补齐 |
| 稳定性 | 共享超时、并发限制、单飞刷新、旧缓存回退、图片占位、完整文字降级 |

> 主要面向 QQ OneBot / `aiocqhttp`。`support_platforms` 只是声明字段，其他平台未做验证。

## 快速开始

1. 在 AstrBot WebUI 的插件安装页面粘贴仓库地址：

   ```text
   https://github.com/<你的账号>/astrbot_plugin_hextechmayhem
   ```

   也可以下载仓库 ZIP 后选择「导入插件」。

2. 在插件配置中选择海斗信息源：
   - 国内环境推荐保持默认 `aramgg`，并填写 `aramgg_api_key`。
   - 不使用 ARAMGG 时切换为 `opgg`，无需填写 ARAMGG API Key。

3. 重载插件后直接查询：

   ```text
   /海斗胜率
   /海斗 亚索
   /海克斯 珠光护手
   /海斗 珠光护手
   /海斗排名
   ```

> [!IMPORTANT]
> **ARAMGG API Key 与 credits**
>
> 前往 [ARAMGG 开发者后台](https://data.dtodo.cn/developer.html)，使用 GitHub 登录并创建 API Key，
> 再填写完整的 `hx_live_...` 密钥。密钥仅作为鉴权请求头发送，不会写入报告或日志。
> 默认每天 200 credits，单个英雄首次查询消耗 2 credits，缓存命中不会重复消耗。

> [!TIP]
> 选择 `opgg` 后，插件不会读取 ARAMGG 目录缓存，也不会请求 ARAMGG API、配置文件或图片 CDN，
> 因此不会消耗 ARAMGG credits。

## 常用指令

| 指令 | 说明 | 示例 |
| --- | --- | --- |
| `/海斗胜率` | 输出胜率最高 TOP 与最低 BOTTOM 英雄（数量由 `winrate_rank_size` 控制，默认各 10 名） | `/海斗胜率` |
| `/海斗 <英雄名>` | 生成英雄海克斯大乱斗完整图片报告（胜率、出装、海克斯适配） | `/海斗 Miss Fortune` |
| `/海斗 <海克斯名>` | 英雄未命中时自动按海克斯检索并展示胜率 / 选取率 | `/海斗 珠光护手` |
| `/海克斯 <海克斯名>` | 生成最多 5 条海克斯搜索图片卡片（含胜率、选取率、场次） | `/海克斯 珠光护手` |
| `/海斗排名` | 生成英雄综合强度前 10 名图片卡片 | `/海斗排名` |

英雄查询同时支持中文名、英文名、英雄内部 ID 和数字 ID，例如 `/海斗 亚索`、`/海斗 Miss Fortune`、`/海斗 21`。
当前 AstrBot 支持 `GreedyStr` 时可直接输入多词英文名；插件也会从原始消息恢复完整参数，以兼容较早的 AstrBot 4.x。

> [!NOTE]
> `/海斗排名` 与 `/海斗胜率` 是**两个不同的榜**：
> 前者遵循信息源的**官方综合档位**（胜率只是其中一部分），后者**只按胜率**排序。
> 插件不会用胜率去覆盖官方综合排名。

## 数据来源与展示规则

| 数据源 | 用途 | 使用条件 |
| --- | --- | --- |
| [Riot Data Dragon](https://developer.riotgames.com/docs/lol) | 英雄基础资产与高清封面；为 OP.GG 模式提供英雄目录 | 始终作为可信英雄资产来源 |
| [ARAMGG 数据 API](https://data.dtodo.cn/api/v1/zh-CN/docs/cf-data-api.md) | 英雄名称、别名、图标、海克斯目录与统计、综合排名、技能与装备 | `mayhem_source=aramgg`，默认且国内优先 |
| [OP.GG](https://op.gg/zh-cn/lol/modes/aram-mayhem) | 英雄综合排名、推荐海克斯、召唤师技能、技能加点与装备 | `mayhem_source=opgg`，解析公开服务端页面 |
| [CommunityDragon](https://www.communitydragon.org/) | OP.GG 模式下的海克斯稳定 ID、名称、稀有度、描述和图标 | 仅 OP.GG 模式使用 |
| [Mayhempedia](https://github.com/boxsbraindump/Mayhempedia) | 社区维护的真实六件套路线 | `enable_mayhempedia_source=true` 时使用 |

### 英雄资料与排名

- ARAMGG 模式直接使用其英雄目录、中文名、称号、英文别名和图标；OP.GG 模式使用 Riot Data Dragon 的英雄目录与图标。
- 报告仅展示英雄封面，不展示英雄简介、被动或 QWER 技能详情；技能加点顺序来自所选海斗信息源。
- `/海斗排名` 遵循信息源自身的综合排序和强度档位，不根据胜率重新计算排名。
- `/海斗胜率` 只按胜率排序，并显式区分「胜率最高」与「胜率最低」两段。
- 胜率、登场率、场次和排名变化只在响应真实提供时展示，不推算缺失字段，也不补成 `0`。

### 海克斯与装备

- ARAMGG 模式使用 ARAMGG 海克斯目录；OP.GG 模式将页面名称重新匹配至 CommunityDragon 后才进入报告。
- 海克斯检索会展示上游 `stats` 中的胜率、选取率与场次；没有统计的条目只显示图标与描述，**不补 0**。
- 英雄报告中棱彩、黄金和白银海克斯的展示数量分别受 `max_augments_per_rarity` 限制。
- ARAMGG 单英雄响应还会解析真实流派、18 级技能序列、情境装备、三海克斯组合、热门单件、数据日期和相关文章。
- `fullItems` 为空时不会从核心装备或热门单件推导六神装。

### 社区路线与 LLM

- Mayhempedia 路线始终标注为「社区攻略」，最多展示三条真实六件套；不足三条时不会自动补齐。
- 当前英雄目录和别名无法匹配时，才会调用所选 LLM Provider 识别玩家黑话。
- 模型结果必须重新匹配英雄目录，不会直接作为网络地址使用。

## 胜率数据可信度说明

> [!WARNING]
> ARAMGG 官方明确说明：数据「随 aramgg.com 主站数据刷新，**不承诺实时**」。
> 本插件的「胜率」指**上游最近一次发布的统计快照**，并非逐秒的对局实时胜率。

上游统计的来源与门槛：

| 来源标识 | 含义 | 说明 |
| --- | --- | --- |
| `tencent` | 腾讯国服公开快照 | 不返回可核验的胜局与总场次，`wins` / `games` 可能为 `null` |
| `iesdev` | ARAMGG Build 统计 | 出装流派数据来源 |
| `aramgg-client-upload` | ARAMGG 客户端匿名上传 | 达到样本门槛后跨服务器汇总，最接近「实时」 |

样本门槛：

- 英雄 + 海克斯组合：需达到 **255 场**才补充 `winRate` / `games`，否则保持 `null`。
- 三海克斯组合：需达到 **151 场**才输出，最多返回 5 组。

因此本插件遵循三条原则：

1. **如实标注来源**（腾讯快照 / 客户端上传 / ARAMGG Build）。
2. **缺失就显示缺失**，绝不把 `null` 换算成 `0`。
3. **不把无胜率数据的英雄排进胜率榜**，避免「无数据」被误读成「胜率最低」。

若需要更实时的数据，需要在玩家机器上运行 ARAMGG Electron 客户端，由它上传对局历史。

## 图片体积与发送超时

图片消息和文字消息的发送链路不同：**图片要先上传到腾讯的富媒体 CDN**，NapCat 才能拿到
`file_id` 并发送。这个上传发生在 NapCat 内部约 10 秒的等待窗口里，超时就会报：

```text
Timeout: NTEvent serviceAndMethod:NodeIKernelMsgService/sendMsg
ListenerName:NodeIKernelMsgListener/onMsgInfoListUpdate EventRet: {}
```

而本插件的报告是**整页长截图**（`full_page` + PNG），一张英雄报告很容易达到
**3–6 MB**，base64 编码后还会再膨胀 33%。在海外服务器或上传带宽受限的环境里，
这个体积传不完就会超时。

所以插件在渲染后会自动压缩，顺序是：

1. 体积已在上限内 → **保留 PNG**（无损，小图最清晰）；
2. 超限 → **优先缩小尺寸**（下限 720px）。报告是文字密集的长图，同样字节预算下
   「更多像素 + 中等质量」比「更少像素 + 高质量」更易读；
3. 缩到下限仍超限 → 才退到兜底质量。

压缩本身是**毫秒级**的（1120×3000 约 200ms，1120×5000 约 300ms）：
大图不尝试无损 PNG，缩放比例由一次探测编码反推，`optimize` 只在最终版本付一次。

> [!IMPORTANT]
> 实测中**压缩只占总耗时 1–3%**。真正的瓶颈是 AstrBot 的 `html_render`
> （Chromium 渲染整页 + 截图），它随**页面高度**和**内联图片数量**超线性增长。
> 整页报告可能高达 8000 px、内联 50 张图，在 2 核容器上单次渲染可达 18 秒。
>
> 因此请优先用 `max_build_variants`（流派套数）控制页面高度：少一套流派就少
> 一整块内容外加十余张内联装备图标。社区六件套在无数据时不再占版面。


以 1120×3000 的报告为参考（原始 PNG 约 5.1 MB）：

| `image_max_kb` | 实际输出 | 质量 | 输出尺寸 | 压缩耗时 |
| ---: | ---: | --- | --- | ---: |
| 300 | 285 KB | q72 | 759×2033 | 181 ms |
| 400 | 371 KB | q72 | 847×2269 | 189 ms |
| **512（默认）** | **475 KB** | **q72** | **932×2496** | **206 ms** |
| 700 | 636 KB | q72 | 1051×2815 | 227 ms |
| 900 | 805 KB | q72 | 1120×3000（保留原分辨率） | 151 ms |

取舍建议：

- **发送经常超时 / 服务器在海外** → 保持默认 512，或调到 400；
- **想保留原始分辨率** → 调到 900，此时不再缩尺寸，只做 JPEG 压缩；
- 每次渲染都会在日志里打印实际体积，可据此调整：

  ```text
  报告图片已生成：952×2550，496 KB（JPEG q72）
  ```

> [!TIP]
> 如果调小后仍然发送超时，问题通常不在体积，而在**到腾讯 CDN 的网络**或
> **NapCat / QQ 版本**。可先在群里发一张 100 KB 以内的小图验证：
> 小图能发而大图不能 → 体积；小图也超时 → 网络或版本，需要检查 Docker MTU
> 与 NapCat 版本。

## 推荐配置

| 配置 | 建议 |
| --- | --- |
| `mayhem_source` | 国内环境优先使用默认值 `aramgg`；无法使用 ARAMGG 时切换为 `opgg` |
| `aramgg_api_key` | ARAMGG 模式必填；从开发者后台获取完整的 `hx_live_...` 密钥 |
| `winrate_rank_size` | 默认 `10`，即 `/海斗胜率` 两端各显示 10 名；有效范围 3–50 |
| `max_build_variants` | 默认 `2`。流派区块最占版面，套数越多渲染越慢；`0` 可整块隐藏 |
| `image_max_kb` | 默认 `512`。图片发送超时时调小（如 400）；想保留原分辨率可调到 900 |
| `image_max_concurrent_requests` | 默认 `8`。首屏等待久可适当调大（上限 32）；图标 CDN 限流则调小 |
| `llm_provider_id` | 可选；需要识别「奥巴马」「奶妈」等玩家黑话时再选择 Provider |
| `enable_mayhempedia_source` | 默认关闭；需要社区六件套且可接受额外请求耗时时再开启 |
| `max_concurrent_requests` | 建议保持 `3`，设置过高可能触发第三方站点限流 |

<details>
<summary><strong>完整配置项</strong></summary>

| 配置项 | 默认值 | 说明 |
| --- | ---: | --- |
| `llm_provider_id` | 空 | 用于英雄别名识别的 LLM Provider。ARAMGG 名称和别名无法匹配时识别玩家黑话；留空即关闭 |
| `mayhem_source` | `aramgg` | 海斗信息源，可选 `opgg`、`aramgg` |
| `aramgg_api_key` | 空 | 仅在 `mayhem_source=aramgg` 时使用；只作为鉴权请求头发送，不写入报告或日志 |
| `enable_mayhempedia_source` | `false` | 启用 Mayhempedia 社区六件套路线 |
| `request_timeout_seconds` | `20` | 所有上游请求超时；有效范围 5–120 秒 |
| `cache_ttl_seconds` | `3600` | 实时数据的内存缓存有效时间 |
| `max_concurrent_requests` | `3` | 最大并发上游请求数；有效范围 1–10 |
| `max_results` | `5` | `/海克斯` 搜索最多展示条数；有效范围 1–10 |
| `max_augments_per_rarity` | `5` | 英雄报告每个稀有度最多展示的海克斯数量；有效范围 1–10 |
| `winrate_rank_size` | `10` | `/海斗胜率` 两端各显示的英雄数量；有效范围 3–50 |
| `max_build_variants` | `2` | 英雄报告最多展示几套流派；有效范围 0–4，`0` 表示整块隐藏 |
| `image_max_kb` | `512` | 报告图片体积上限；有效范围 128–3000。超限时优先缩小尺寸，缩到下限才降质量 |
| `image_max_concurrent_requests` | `8` | 图标下载并发数；有效范围 1–32。与 API 请求的并发限制相互独立 |
| `proxy` | 空 | 访问实时数据源时使用的 HTTP 代理，例如 `http://127.0.0.1:7890` |

旧配置 `max_interactions` 已弃用。若配置文件仍存在该字段，插件只记录一次提示，不再使用其值控制报告内容。

</details>

## 缓存与故障降级

ARAMGG 英雄列表、英雄别名和海克斯目录会保存到固定缓存文件：

```text
data/plugin_data/astrbot_plugin_hextechmayhem/cache/
├── aramgg_champions.json
└── aramgg_augments.json
```

插件启动时先读取本地目录缓存，再访问不消耗 credits 的 ARAMGG `config.json` 检查 `dataVersion`；
只有版本变化时才下载并原子替换缓存文件。网络不可用但本地目录有效时继续使用本地数据。

单英雄统计、OP.GG 页面、社区路线、LLM 结果和图片只保存在当前进程内。
缓存过期后会单飞刷新；刷新失败但有旧缓存时继续使用并标记「缓存数据」，冷启动失败时只隐藏对应模块。

> [!WARNING]
> 第三方站点结构变化、限流、访问验证或网络故障可能使部分模块暂时不可用。
> 单个图标失败时使用占位块；HTML 图片渲染失败时发送包含相同字段的完整文字报告，不阻断其他可用数据源。

图片下载只接受可信 HTTPS 域名，并校验最终重定向、Content-Type 和响应体大小。最终报告通过 Base64 图片发送，不在磁盘中持久化。

## 开发与测试

```bash
git clone https://github.com/<你的账号>/astrbot_plugin_hextechmayhem
cd astrbot_plugin_hextechmayhem

# 依赖
pip install -r requirements.txt
pip install pytest

# 测试（需在仓库的父目录下执行，或在 pyproject.toml 指定的 pythonpath 下运行）
pytest -q
```

测试覆盖：ARAMGG / OP.GG / CommunityDragon / Mayhempedia 解析、英雄名匹配、单飞与缓存回退、
图片域名白名单、HTML 渲染、胜率榜分组、配置边界与指令注册。

代码规范：

```bash
ruff check .
ruff format --check .
```

参与贡献请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 依赖

AstrBot 会根据 `requirements.txt` 自动安装：

```text
aiohttp>=3.10,<4
beautifulsoup4>=4.12,<5
certifi>=2024.8.30
Pillow>=11.1
yarl>=1.15,<2
```

> [!IMPORTANT]
> **关于 `Pillow` 的版本约束**
>
> 原版写的是 `Pillow>=11.1,<13`。当 AstrBot 运行环境的 Pillow 已经是 13.x 时，
> AstrBot 的「核心依赖版本保护」会把已安装版本锁成 `pillow==13.0.0`，
> 而插件的 `<13` 上界与之无交集，安装会直接失败并报：
>
> ```text
> DependencyConflictError: A core dependency version protection conflict was detected.
> Conflict details: Pillow<13 and >=11.1 vs (constraint) pillow==13.0.0
> ```
>
> 本改造版去掉了上界（`Pillow>=11.1`）。插件只使用 Pillow 的稳定核心 API
> （`Image.open` / `load` / `thumbnail` / `convert` / `save`），在 Pillow 11、12、13 上行为一致。
> 如果上游将来引入不兼容变更，请改用 `Pillow>=11.1,<15` 这类宽松上界，而不要再排除中间版本。

## 声明与致谢

- 原项目：[muyikk/astrbot_plugin_hextechmayhem](https://github.com/muyikk/astrbot_plugin_hextechmayhem)（GPL-3.0）
- 英雄资料与资产：[Riot Games Data Dragon](https://developer.riotgames.com/docs/lol)
- 国内优先英雄统计：[ARAMGG 数据 API](https://data.dtodo.cn/api/v1/zh-CN/docs/cf-data-api.md)
- 备用英雄统计：[OP.GG](https://op.gg/zh-cn/lol/modes/aram-mayhem)
- OP.GG 模式海克斯定义与资产：[CommunityDragon](https://www.communitydragon.org/)
- 社区攻略路线：[Mayhempedia](https://github.com/boxsbraindump/Mayhempedia)
- 功能设计参考：[PayneXie/astrbot_plugin_hextech](https://github.com/PayneXie/astrbot_plugin_hextech)
- 插件图标：Riot Data Dragon 的 ARAM: Mayhem 「Friends in Mayhem」召唤师图标（ID 7011）

本插件与 Riot Games、ARAMGG、OP.GG 和 Mayhempedia 均无官方关联。请遵守相关服务条款和 Riot Games 的知识产权政策。

项目采用 [GNU General Public License v3.0](LICENSE)，详细的第三方来源与许可说明见 [NOTICE](NOTICE)。
