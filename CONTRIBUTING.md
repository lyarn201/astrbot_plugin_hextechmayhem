# 贡献指南

感谢你愿意改进「海克斯乱斗」插件！本文档说明开发流程与代码约定。

## 项目定位

本仓库是 [muyikk/astrbot_plugin_hextechmayhem](https://github.com/muyikk/astrbot_plugin_hextechmayhem)
的改造版（fork），遵循 **GPL-3.0** 协议。提交代码即表示你同意以同一协议分发。

如果你是来**扩展现有功能**，请优先考虑：

1. 属于上游通用能力 → 给上游提 PR；
2. 属于本改造版新增的方向（胜率榜、海克斯统计、智能识别）→ 提到本仓库。

## 开发环境

```bash
git clone https://github.com/<你的账号>/astrbot_plugin_hextechmayhem
cd astrbot_plugin_hextechmayhem

# 安装依赖
pip install -r requirements.txt
pip install pytest ruff

# 运行测试
pytest -q

# 代码检查
ruff check .
ruff format --check .
```

### 在 AstrBot 中调试

AstrBot 在运行时注入插件，因此调试需要启动 AstrBot 本体：

1. 把本仓库放到 `AstrBot/data/plugins/astrbot_plugin_hextechmayhem`；
2. 启动 AstrBot，在 WebUI 的「插件」页找到本插件；
3. 修改代码后，点击插件卡片上的刷新图标「重载插件」；
4. 加载失败时，在同一页面的「加载失败插件」列表中点「重载」查看报错。

## 代码约定

- **异步网络请求**：只用 `aiohttp` / `httpx`，**不要用 `requests`**（会阻塞事件循环）。
- **持久化数据**：写到 `data/plugin_data/astrbot_plugin_hextechmayhem/`，**不要写到插件自身目录**，
  否则插件更新或重装时数据会被覆盖。
- **错误处理**：任何上游失败都要降级，不能让整条指令崩掉。图片渲染失败必须回退成文字报告。
- **数据可信度**：上游缺失的统计字段保持缺失，**绝不补 `0`**，也不要推算。
  展示时如实标注数据来源与样本门槛。
- **可信域名**：新增图片来源时必须同步更新 `hextech_service.py` 的 `_TRUSTED_IMAGE_HOSTS`，
  并保持「校验最终重定向 + Content-Type + 大小上限」的检查。
- **注释**：公共函数写清楚用途和副作用；对数据可信度相关的判断（为何不补 0、为何对半切）要写明理由。
- **格式化**：提交前跑 `ruff format .`。

## 目录结构

```text
astrbot_plugin_hextechmayhem/
├── main.py            # 指令层：注册指令、事件处理、图文降级
├── hextech_service.py # 服务层：数据编排、缓存、单飞刷新、并发闸门、图片下载
├── sources.py         # 解析层：ARAMGG / OP.GG / CommunityDragon / Mayhempedia
├── renderer.py        # 渲染层：HTML 模板 + html_render 转 PNG
├── models.py          # 数据模型：frozen dataclass
├── command_utils.py   # 指令参数恢复（兼容无 GreedyStr 的 AstrBot 4.x）
├── _conf_schema.json  # WebUI 配置 schema
├── metadata.yaml      # 插件元数据
└── tests/             # 单元测试与 HTML fixture
```

分层原则：**指令层只做编排，不做解析也不做渲染**。新增数据源写在 `sources.py`，
新增数据处理放在服务层，新增展示样式放在 `renderer.py`。

## 提交测试

新增功能或修复必须带测试。测试放在 `tests/`，使用标准库 `unittest`：

```bash
pytest -q                      # 全部
pytest tests/test_service.py -q  # 单个文件
```

解析器测试请使用 `tests/fixtures/` 下的 HTML 片段或内联 dict，**不要依赖真实网络**。

## 提交 PR

1. 从 `main` 拉一个语义化分支：`feat/winrate-bottom-n`、`fix/pillow-constraint`。
2. 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：
   - `feat: 新增海克斯胜率榜`
   - `fix: 修正胜率榜样本不足时的重复条目`
   - `docs: 补充数据来源说明`
3. 确认 `pytest -q` 与 `ruff check .` 均通过。
4. 在 PR 描述里说明：**改了什么、为什么、如何验证**，并附上关键截图（如涉及 UI）。
5. 同步更新 `CHANGELOG.md` 的 `Unreleased` 段落。

## 报告问题

请使用 Issue 模板，并尽量附上：

- AstrBot 版本（WebUI 左下角可见）与本插件版本；
- `mayhem_source` 配置值（**不要贴出 API Key**）；
- 相关日志片段（可在 AstrBot「数据与日志 → 日志」中获取）；
- 复现步骤与实际结果。

## 安全提示

不要在 Issue、PR 或日志中提交以下内容：

- ARAMGG API Key（`hx_live_...`）；
- 完整的调用日志中的鉴权头；
- 任何真实用户的 QQ 号或聊天记录。
