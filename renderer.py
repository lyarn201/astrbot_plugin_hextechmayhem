from __future__ import annotations

import base64
import binascii
import html
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable
from urllib.parse import unquote, urlparse

from PIL import Image as PILImage

from .models import (
    Augment,
    AugmentRecommendation,
    AugmentTrio,
    BuildVariant,
    ChampionSummary,
    FullBuildRoute,
    HeroReport,
    ItemPerformance,
    ItemRef,
    LoadoutOption,
)

RenderCallable = Callable[..., Awaitable[Any]]

_TIER_LABELS = {
    "Prismatic": "棱彩阶",
    "Gold": "黄金阶",
    "Silver": "白银阶",
    "Bronze": "青铜阶",
}

# 报告模板 body 背景色（#050914）。转 JPEG 前用它合成透明像素，
# 保证视觉上与原图一致。
_DOC_BACKGROUND = (5, 9, 20)
# 基准质量：体积靠「缩放」而不是「降质量」来控制。文字密集的报告里，
# 保分辨率比保质量因子更划算，因此基准压到 72 换取更大的像素数。
_BASE_QUALITY = 72
# 体积还有余量时尝试提升到的质量档（只试一次，避免反复编码）。
_QUALITY_BUMP = 82
# 少量兜底质量档：缩到下限仍超限时使用。
_FALLBACK_QUALITIES = (66, 60)
# JPEG 体积对缩放比例的实测幂次（缩得越小，压缩收益越大于面积比）。
# 用它反推达标所需缩放比例，避免像逐档试探那样反复编码。
_SCALE_EXPONENT = 2.6
# 不超过该像素数时才尝试无损 PNG。整页长图的 PNG 编码本身就要近一秒，
# 且几乎必然超出体积上限，不值得尝试。
_PNG_ATTEMPT_MAX_PIXELS = 1_500_000
# 缩尺寸的下限：低于该宽度文本已经不可读，不再继续压缩。
_MIN_WIDTH = 720


class ReportRenderer:
    width = 1120

    def __init__(self, max_image_kb: int = 512, compact: bool = True) -> None:
        self.max_image_kb = max(64, int(max_image_kb))
        # 精简模式：英雄报告只保留封面与海克斯推荐，不再渲染出装 / 流派 / 组合等模块。
        self.compact = bool(compact)
        # 最近一次渲染的体积信息，供调用方记录日志。
        self.last_render_meta: dict[str, Any] = {}

    async def hero_report(
        self,
        render: RenderCallable,
        report: HeroReport,
        images: dict[str, str],
    ) -> bytes:
        return await self._render(render, self.hero_html(report, images))

    async def augment_report(
        self,
        render: RenderCallable,
        augments: list[Augment],
        images: dict[str, str],
        *,
        query: str,
        total: int,
        stale: bool,
    ) -> bytes:
        return await self._render(
            render,
            self.augment_html(
                augments,
                images,
                query=query,
                total=total,
                stale=stale,
            ),
        )

    async def ranking_report(
        self,
        render: RenderCallable,
        rankings: list[ChampionSummary],
        images: dict[str, str],
        *,
        source: str,
        stale: bool,
    ) -> bytes:
        return await self._render(
            render,
            self.ranking_html(rankings, images, source=source, stale=stale),
        )

    def ranking_html(
        self,
        rankings: list[ChampionSummary],
        images: dict[str, str],
        *,
        source: str,
        stale: bool,
    ) -> str:
        source_label = "OP.GG" if source == "opgg" else "ARAMGG"
        patch = next((item.stats_patch for item in rankings if item.stats_patch), "")
        date = next((item.stats_date for item in rankings if item.stats_date), "")
        stats_source = next((item.stats_source for item in rankings if item.stats_source), source)
        region = next((item.stats_region for item in rankings if item.stats_region), "")
        meta = [
            value
            for value in (
                f"PATCH {patch}" if patch else "",
                date,
                _source_label(stats_source),
                _region_label(region),
            )
            if value
        ]
        if stale:
            meta.append("缓存数据")
        grouped: dict[str, list[ChampionSummary]] = {}
        for item in rankings:
            grouped.setdefault(item.stats_tier or "未分档", []).append(item)
        sections = []
        for tier, items in grouped.items():
            cards = "".join(_ranking_card(item, images) for item in items)
            label = f"T{tier}" if tier != "未分档" else tier
            sections.append(
                '<section class="ranking-tier"><div class="ranking-tier-head">'
                f'<h2>{_safe(label)}</h2><span>{len(items)} 位英雄</span></div>'
                f'<div class="ranking-grid">{cards}</div></section>'
            )
        return self._document(
            title=f"海克斯大乱斗英雄排名 · {source_label}",
            body=f"""
<header class="ranking-header">
  <div class="eyebrow">HEXTECH MAYHEM RANKING</div>
  <h1>英雄综合强度排名</h1>
  <div class="subtitle">{_safe(source_label)} 官方公开榜单 · 胜率只是综合排名的一部分</div>
  <div class="badges">{''.join(f'<span class="badge">{_safe(value)}</span>' for value in meta)}</div>
</header>
{''.join(sections)}
<footer>排名、档位与统计均按来源实际返回展示 · 缺失字段不补 0 · 非官方插件</footer>
""",
        )

    async def winrate_ranking_report(
        self,
        render: RenderCallable,
        top: list[ChampionSummary],
        bottom: list[ChampionSummary],
        images: dict[str, str],
        *,
        source: str,
        stale: bool,
    ) -> bytes:
        return await self._render(
            render,
            self.winrate_ranking_html(top, bottom, images, source=source, stale=stale),
        )

    def winrate_ranking_html(
        self,
        top: list[ChampionSummary],
        bottom: list[ChampionSummary],
        images: dict[str, str],
        *,
        source: str,
        stale: bool,
    ) -> str:
        source_label = "OP.GG" if source == "opgg" else "ARAMGG"
        sample = (*top, *bottom)
        patch = next((item.stats_patch for item in sample if item.stats_patch), "")
        date = next((item.stats_date for item in sample if item.stats_date), "")
        stats_source = next((item.stats_source for item in sample if item.stats_source), source)
        region = next((item.stats_region for item in sample if item.stats_region), "")
        meta = [
            value
            for value in (
                f"PATCH {patch}" if patch else "",
                date,
                _source_label(stats_source),
                _region_label(region),
                "仅统计有真实胜率的英雄",
            )
            if value and value != source_label
        ]
        if stale:
            meta.append("缓存数据")
        return self._document(
            title=f"海克斯大乱斗胜率榜 · {source_label}",
            body=f"""
<header class="ranking-header">
  <div class="eyebrow">HEXTECH MAYHEM WIN RATE</div>
  <h1>英雄胜率榜</h1>
  <div class="subtitle">{_safe(source_label)} 公开统计 · 按真实胜率排序，最强与最弱各一榜</div>
  <div class="badges">{''.join(f'<span class="badge">{_safe(value)}</span>' for value in meta)}</div>
</header>
{_winrate_section("胜率最高", top, images, "top", "TOP")}
{_winrate_section("胜率最低", bottom, images, "bottom", "BOTTOM")}
<footer>胜率取自上游实际返回 · 无胜率数据的英雄不参与排序 · 缺失字段不补 0 · 非官方插件</footer>
""",
        )

    def hero_html(self, report: HeroReport, images: dict[str, str]) -> str:
        champion = report.champion
        splash = _first_image(images, champion.splash_url, champion.splash_fallback_url)
        splash_style = (
            "background-image:linear-gradient(90deg,rgba(5,10,20,.16),"
            f"rgba(5,10,20,.96)),url('{html.escape(splash, quote=True)}')"
            if splash.startswith("data:image/")
            else ""
        )
        badges = []
        if report.patch:
            badges.append(f'<span class="badge">PATCH {_safe(report.patch)}</span>')
        if report.tier:
            badges.append(f'<span class="badge tier-rank">{_safe(report.tier)}</span>')
        for source in report.stale_sources:
            badges.append(f'<span class="badge stale">{_safe(source)} 旧缓存</span>')

        unavailable = ""
        if report.unavailable_sources:
            unavailable = (
                '<div class="source-warning">暂不可用：'
                + _safe("、".join(report.unavailable_sources))
                + "；其余模块仍为可用数据。</div>"
            )

        augment_columns = []
        for tier in ("Prismatic", "Gold", "Silver"):
            items = report.augments.get(tier, ())
            cards = "".join(_recommendation_card(item, images) for item in items)
            if not cards:
                cards = '<div class="mini-empty">暂无统计推荐</div>'
            augment_columns.append(
                f'<div class="augment-column tier-{_tier_class(tier)}">'
                f'<h3>{_safe(_tier_label(tier))}<span>{len(items)}</span></h3>{cards}</div>'
            )

        # 精简模式：只保留英雄封面与海克斯推荐。
        # 报告主体本来能到六七千像素高，砍掉下方模块后 Chromium 的渲染时间和
        # 内联图片数量都会成倍下降，是当前环境里最有效的一刀。
        if self.compact:
            return self._document(
                title=f"{champion.name} · 海克斯乱斗",
                body=f"""
<section class="hero" style="{splash_style}">
  <div class="eyebrow">HEXTECH MAYHEM</div>
  <h1>{_safe(champion.name)}</h1>
  <div class="subtitle">{_safe(champion.title)} · {_safe(champion.id)}</div>
  <div class="badges">{''.join(badges)}</div>
</section>
{unavailable}
<section>
  <div class="section-title"><h2>海克斯推荐</h2><span>海斗信息源排序 · ARAMGG 资料</span></div>
  <div class="augment-grid">{''.join(augment_columns)}</div>
</section>
<footer>英雄封面：Riot Data Dragon · 海克斯：ARAMGG / CommunityDragon · 非官方插件</footer>
""",
            )

        mechanisms = []
        ranked = sorted(
            (item for values in report.augments.values() for item in values),
            key=lambda item: item.rank,
        )
        for item in ranked[:3]:
            if item.augment.mechanism:
                mechanisms.append(
                    '<div class="mechanism-card">'
                    f'<b>{_safe(item.augment.name_zh)}</b>'
                    f'<span>{_safe(item.augment.mechanism)}</span></div>'
                )
        mechanism_section = (
            '<section><div class="section-title"><h2>机制补充</h2>'
            '<span>ARAMGG 机制说明</span></div>'
            f'<div class="mechanism-grid">{"".join(mechanisms)}</div></section>'
            if mechanisms
            else ""
        )

        overview_cards = [
            _option_module("召唤师技能", report.summoner_spells, images, "最多 2 套"),
            _skill_order_module(report.skill_order),
            _option_module("出门装", report.starter_items, images, "最多 2 套"),
            _items_module("鞋子", report.boots, images, "最多 2 个"),
        ]
        core_cards = _option_module("核心装备", report.core_builds, images, "海斗统计 · 最多 3 套", wide=True)
        variant_section = ""
        if report.build_variants:
            variant_cards = "".join(
                _build_variant_card(item, images) for item in report.build_variants
            )
            variant_section = (
                '<section><div class="section-title"><h2>流派与完整技能方案</h2>'
                '<span>ARAMGG · 最多 4 个真实流派</span></div>'
                f'<div class="variant-list">{variant_cards}</div></section>'
            )
        trio_section = ""
        if report.augment_trios:
            trio_cards = "".join(_augment_trio_card(item, images) for item in report.augment_trios)
            trio_section = (
                '<section><div class="section-title"><h2>三海克斯组合</h2>'
                '<span>达到来源样本门槛的真实组合 · 最多 5 套</span></div>'
                f'<div class="trio-grid">{trio_cards}</div></section>'
            )
        item_section = ""
        if report.item_performance:
            item_cards = "".join(
                _item_performance_card(item, images) for item in report.item_performance
            )
            item_section = (
                '<section><div class="section-title"><h2>热门单件表现</h2>'
                '<span>仅展示来源真实统计 · 最多 6 件</span></div>'
                f'<div class="item-performance-grid">{item_cards}</div></section>'
            )
        provenance_section = ""
        if report.provenance or report.related_articles:
            provenance = "".join(f'<li>{_safe(value)}</li>' for value in report.provenance)
            articles = "".join(f'<li>{_safe(item.title)}</li>' for item in report.related_articles)
            provenance_section = (
                '<section><div class="section-title"><h2>数据说明与相关攻略</h2>'
                '<span>缺失字段不会补成 0</span></div><div class="meta-grid">'
                f'<div><b>数据来源</b><ul>{provenance or "<li>暂无额外来源说明</li>"}</ul></div>'
                f'<div><b>相关文章</b><ul>{articles or "<li>暂无相关文章</li>"}</ul></div>'
                '</div></section>'
            )
        # 社区六件套只在真的有数据时才占版面：空区块既不提供信息，又会把整页
        # 高度顶高，直接推高 Chromium 的渲染时间。
        route_section = ""
        if report.full_builds:
            route_cards = "".join(_route_card(route, images) for route in report.full_builds)
            route_section = (
                '<section><div class="section-title"><h2>完整六件套</h2>'
                f'<span>Mayhempedia 社区攻略 · {len(report.full_builds)} 套</span></div>'
                f'<div class="route-list">{route_cards}</div></section>'
            )

        return self._document(
            title=f"{champion.name} · 海克斯乱斗",
            body=f"""
<section class="hero" style="{splash_style}">
  <div class="eyebrow">HEXTECH MAYHEM</div>
  <h1>{_safe(champion.name)}</h1>
  <div class="subtitle">{_safe(champion.title)} · {_safe(champion.id)}</div>
  <div class="badges">{''.join(badges)}</div>
</section>
{unavailable}
<section>
  <div class="section-title"><h2>海克斯推荐</h2><span>海斗信息源排序 · ARAMGG 资料</span></div>
  <div class="augment-grid">{''.join(augment_columns)}</div>
</section>
{mechanism_section}
<section>
  <div class="section-title"><h2>对局配置</h2><span>海斗信息源公开统计</span></div>
  <div class="module-grid">{''.join(overview_cards)}</div>
  {core_cards}
</section>
{variant_section}
{trio_section}
{item_section}
{route_section}
{provenance_section}
<footer>英雄封面：Riot Data Dragon · 英雄与海克斯：ARAMGG / CommunityDragon · 统计：ARAMGG / OP.GG · 非官方插件</footer>
""",
        )

    def augment_html(
        self,
        augments: list[Augment],
        images: dict[str, str],
        *,
        query: str,
        total: int,
        stale: bool,
    ) -> str:
        cards = []
        for item in augments:
            image = _image_tag(images.get(item.icon_url, ""), item.name_zh, "large-icon")
            mechanism = (
                '<div class="mechanism"><b>机制补充</b>'
                f"{_safe(item.mechanism)}</div>"
                if item.mechanism
                else ""
            )
            cards.append(
                f'<article class="search-card tier-{_tier_class(item.tier)}">'
                f'{image}<div class="search-copy"><div class="augment-head">'
                f'<span class="augment-name big">{_safe(item.name_zh)}</span>'
                f'<span class="tier-pill">{_safe(_tier_label(item.tier))}</span></div>'
                f'<div class="en-name">{_safe(item.name_en or item.api_name)}</div>'
                f'{_augment_stats_html(item)}'
                f'<div class="description">{_safe(item.description)}</div>{mechanism}'
                "</div></article>"
            )
        stale_badge = '<span class="badge stale">旧缓存</span>' if stale else ""
        stats_note = next(
            (
                _source_label(item.stats_source)
                + ("/" + _region_label(item.stats_region) if item.stats_region else "")
                for item in augments
                if item.stats_source
            ),
            "",
        )
        footer_parts = ["海克斯资料：ARAMGG"]
        if stats_note:
            footer_parts.append(f"统计：{stats_note}")
        footer_parts.append("缺失统计不补 0")
        footer_parts.append("非官方插件")
        return self._document(
            title=f"{query} · 海克斯搜索",
            body=f"""
<header class="search-header">
  <div class="eyebrow">HEXTECH AUGMENT SEARCH {stale_badge}</div>
  <h1>“{_safe(query)}”</h1>
  <div class="subtitle">找到 {total} 条，展示前 {len(augments)} 条</div>
</header>
<main class="search-list">{''.join(cards)}</main>
<footer>{_safe(" · ".join(footer_parts))}</footer>
""",
        )

    async def _render(self, render: RenderCallable, source_html: str) -> bytes:
        options = {
            "full_page": True,
            "type": "png",
            "scale": "device",
            "device_scale_factor_level": "normal",
        }
        started = time.perf_counter()
        result = await render(source_html, {}, False, options)
        normalized = normalize_render_result(result)
        data, meta = finalize_image(normalized, max_kb=self.max_image_kb)
        meta["ms"] = round((time.perf_counter() - started) * 1000)
        self.last_render_meta = meta
        return data

    def _document(self, *, title: str, body: str) -> str:
        return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width={self.width}"><title>{_safe(title)}</title>
<style>
* {{ box-sizing:border-box; }}
html,body {{ margin:0;width:{self.width}px;background:#050914;color:#eef5ff; }}
body {{ font-family:Inter,"PingFang SC","Microsoft YaHei",sans-serif;padding:32px; }}
body::before {{ content:"";position:fixed;inset:0;pointer-events:none;background:
radial-gradient(circle at 86% 4%,rgba(33,181,255,.17),transparent 29%),
radial-gradient(circle at 3% 42%,rgba(141,72,255,.13),transparent 28%); }}
section,.search-header {{ position:relative;background:linear-gradient(145deg,rgba(17,28,48,.97),rgba(8,14,27,.98));border:1px solid #203858;border-radius:22px;padding:26px;margin-bottom:20px;box-shadow:0 18px 50px rgba(0,0,0,.34);overflow:hidden; }}
.hero {{ min-height:330px;background-size:cover;background-position:center;display:flex;flex-direction:column;justify-content:flex-end; }}
.eyebrow {{ color:#65d8ff;letter-spacing:2.1px;font-size:14px;font-weight:800; }}
h1 {{ margin:9px 0 2px;font-size:54px;line-height:1.04; }}
h2 {{ margin:0;color:#d7eaff;font-size:24px; }}
h3 {{ margin:0 0 12px;font-size:18px;display:flex;justify-content:space-between; }}
h3 span {{ color:#6e88a8;font-size:12px; }}
.subtitle,.en-name {{ color:#91a9c5; }}
.badges {{ display:flex;gap:8px;flex-wrap:wrap;margin-top:12px; }}
.badge,.tier-pill {{ display:inline-block;padding:4px 9px;border-radius:999px;color:#d3e5f7;background:#17283c;border:1px solid #294662;font-size:12px;font-weight:800; }}
.tier-rank {{ color:#75e6ff; }} .stale {{ color:#ffd47b;background:rgba(255,180,40,.12);border-color:rgba(255,190,70,.35); }}
.source-warning {{ position:relative;margin:-4px 0 20px;padding:13px 18px;border-radius:13px;color:#ffd99a;background:#2b2112;border:1px solid #684b1f; }}
.section-title {{ display:flex;align-items:baseline;justify-content:space-between;margin-bottom:18px; }}
.section-title>span {{ color:#6683a5;font-size:13px; }}
.augment-grid {{ display:grid;grid-template-columns:repeat(3,1fr);gap:13px; }}
.augment-column {{ padding:15px;border:1px solid #263c59;border-top-width:4px;border-radius:16px;background:rgba(7,14,27,.72); }}
.tier-prismatic {{ border-top-color:#b47cff!important; }} .tier-gold {{ border-top-color:#ffca55!important; }} .tier-silver {{ border-top-color:#a9bfd4!important; }}
.recommendation {{ display:flex;gap:10px;align-items:center;padding:9px 0;border-top:1px solid rgba(76,103,136,.25); }}
.recommendation:first-of-type {{ border-top:0; }}
.rank {{ width:22px;color:#6f8dab;font-size:12px;font-weight:800; }}
.augment-icon,.item-icon {{ width:42px;height:42px;border-radius:10px;object-fit:cover;background:#101b2c;flex:0 0 auto; }}
.rec-copy {{ min-width:0;flex:1; }} .rec-name {{ font-size:14px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }}
.stats {{ color:#7790aa;font-size:11px;margin-top:3px; }}
.mini-empty,.empty {{ color:#8198b2;padding:22px;text-align:center;border:1px dashed #29435f;border-radius:12px; }}
.mechanism-grid {{ display:grid;gap:10px; }} .mechanism-card {{ display:grid;grid-template-columns:170px 1fr;gap:14px;padding:14px;border-radius:13px;background:rgba(255,184,60,.07);border:1px solid rgba(255,184,60,.2); }}
.mechanism-card b {{ color:#ffd079; }} .mechanism-card span {{ color:#d9c8aa;line-height:1.5; }}
.module-grid {{ display:grid;grid-template-columns:repeat(2,1fr);gap:13px;margin-bottom:13px; }}
.module {{ border:1px solid #223a59;background:rgba(8,15,28,.7);border-radius:15px;padding:15px; }}
.module.wide {{ margin-top:13px; }} .module-head {{ display:flex;justify-content:space-between;margin-bottom:11px; }} .module-head b {{ color:#dcecff; }} .module-head span {{ color:#68809d;font-size:12px; }}
.option {{ display:flex;align-items:center;gap:8px;padding:9px 0;border-top:1px solid rgba(70,97,130,.25); }} .option:first-of-type {{ border-top:0; }}
.items {{ display:flex;align-items:center;gap:7px;flex-wrap:wrap; }} .item {{ display:grid;justify-items:center;gap:4px;max-width:76px; }} .item-name {{ color:#aebed0;font-size:10px;text-align:center;line-height:1.2; }}
.arrow {{ color:#49627f;font-weight:900; }} .skill-order {{ color:#a8e8ff;font-size:22px;font-weight:900;letter-spacing:3px;padding:13px 3px; }}
.route-list {{ display:grid;gap:12px; }} .route {{ border:1px solid #2a405d;background:rgba(8,15,28,.72);border-radius:15px;padding:16px; }}
.variant-list {{ display:grid;gap:14px; }} .variant {{ border:1px solid #29425f;background:rgba(7,14,27,.74);border-radius:16px;padding:17px; }}
.variant-head {{ display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:13px; }} .variant-name {{ color:#75e6ff;font-size:18px;font-weight:900; }}
.variant-grid {{ display:grid;grid-template-columns:repeat(2,1fr);gap:12px; }} .variant-block {{ padding:11px;border-radius:11px;background:#0c1728;border:1px solid #1e354f; }} .variant-block>b {{ display:block;color:#9fb8d2;font-size:12px;margin-bottom:8px; }}
.skill-sequence {{ color:#a8e8ff;line-height:1.65;font-size:13px;word-spacing:3px; }}
.trio-grid {{ display:grid;grid-template-columns:repeat(2,1fr);gap:12px; }} .trio-card,.item-performance {{ border:1px solid #29415d;background:rgba(8,15,28,.72);border-radius:14px;padding:14px; }}
.trio-icons {{ display:flex;gap:8px;align-items:center; }} .item-performance-grid {{ display:grid;grid-template-columns:repeat(3,1fr);gap:11px; }} .item-performance {{ display:flex;gap:10px;align-items:center; }}
.meta-grid {{ display:grid;grid-template-columns:repeat(2,1fr);gap:15px; }} .meta-grid>div {{ border:1px solid #263c59;border-radius:14px;padding:15px;background:rgba(8,15,28,.7); }} .meta-grid b {{ color:#8edfff; }} .meta-grid ul {{ margin:10px 0 0;padding-left:19px;color:#9eb2c8;line-height:1.7; }}
.route-head {{ display:flex;justify-content:space-between;align-items:center;margin-bottom:12px; }} .route-name {{ font-weight:900;color:#f3d58b;font-size:17px; }} .route-source {{ color:#6d86a4;font-size:11px; }} .route-note {{ color:#9fb1c5;line-height:1.45;font-size:13px;margin-top:11px; }}
.image-placeholder {{ display:grid;place-items:center;color:#55718e;border:1px dashed #29435f;background:#0b1423;font-weight:800; }}
.augment-icon.image-placeholder,.item-icon.image-placeholder {{ width:42px;height:42px;border-radius:10px; }}
.large-icon {{ width:84px;height:84px;border-radius:18px;object-fit:cover;background:#101b2c; }} .large-icon.image-placeholder {{ width:84px;height:84px;border-radius:18px; }}
.search-list {{ position:relative;display:grid;gap:13px; }} .search-card {{ display:flex;gap:16px;align-items:flex-start;border:1px solid #223a59;border-left-width:5px;background:rgba(8,15,28,.75);border-radius:16px;padding:20px; }}
.ranking-header {{ position:relative;background:linear-gradient(135deg,#10213a,#09111f);border:1px solid #284768;border-radius:22px;padding:27px;margin-bottom:20px; }}
.ranking-header h1 {{ font-size:45px; }} .ranking-tier {{ padding:20px; }} .ranking-tier-head {{ display:flex;justify-content:space-between;align-items:center;margin-bottom:14px; }} .ranking-tier-head span {{ color:#728da9;font-size:13px; }}
.ranking-grid {{ display:grid;grid-template-columns:repeat(2,1fr);gap:11px; }} .ranking-card {{ display:flex;align-items:center;gap:12px;padding:13px;border:1px solid #263f5d;border-radius:14px;background:rgba(7,14,27,.78); }}
.ranking-position {{ width:36px;text-align:center;color:#70dcff;font-size:18px;font-weight:900; }} .ranking-avatar {{ width:54px;height:54px;border-radius:13px;object-fit:cover;background:#101b2c; }} .ranking-avatar.image-placeholder {{ width:54px;height:54px;border-radius:13px; }}
.ranking-copy {{ min-width:0;flex:1; }} .ranking-name {{ font-size:16px;font-weight:900; }} .ranking-title {{ color:#7891ad;font-size:11px;margin-top:2px; }} .role-list {{ display:flex;gap:5px;flex-wrap:wrap;margin-top:6px; }} .role {{ color:#a8bdd2;background:#14243a;border-radius:7px;padding:2px 6px;font-size:10px; }} .rank-up {{ color:#62e5a1; }} .rank-down {{ color:#ff7e91; }}
.search-copy {{ min-width:0;flex:1; }} .augment-head {{ display:flex;align-items:center;gap:10px;flex-wrap:wrap; }} .augment-name.big {{ font-size:23px;font-weight:900; }}
.description {{ color:#d5deeb;font-size:16px;line-height:1.55;margin-top:10px; }} .en-name {{ margin-top:4px;font-size:13px; }}
.mechanism {{ margin-top:13px;padding:12px 14px;border-radius:12px;line-height:1.55;color:#f4d9a2;background:rgba(255,184,60,.08);border:1px solid rgba(255,184,60,.22); }} .mechanism b {{ display:block;color:#ffc967;margin-bottom:4px; }}
.winrate-panel {{ padding:20px; }}
.winrate-panel.top .section-title h2 {{ color:#7df3b4; }}
.winrate-panel.bottom .section-title h2 {{ color:#ff9aa8; }}
.winrate-list {{ display:grid; gap:9px; }}
.winrate-row {{ display:grid;grid-template-columns:38px 50px 1fr 110px 178px;align-items:center;gap:14px;padding:11px 14px;border:1px solid #263f5d;border-radius:13px;background:rgba(7,14,27,.78); }}
.winrate-panel.top .winrate-row {{ border-left:4px solid #2f9d6a; }}
.winrate-panel.bottom .winrate-row {{ border-left:4px solid #a8404f; }}
.winrate-position {{ text-align:center;color:#70dcff;font-size:17px;font-weight:900; }}
.winrate-avatar {{ width:50px;height:50px;border-radius:12px;object-fit:cover;background:#101b2c; }}
.winrate-avatar.image-placeholder {{ width:50px;height:50px;border-radius:12px; }}
.winrate-copy {{ min-width:0; }}
.winrate-name {{ font-size:16px;font-weight:900; }}
.winrate-title {{ color:#7891ad;font-size:11px;margin-top:2px; }}
.winrate-value {{ text-align:right;font-size:23px;font-weight:900;letter-spacing:.4px; }}
.winrate-value.top {{ color:#7df3b4; }} .winrate-value.bottom {{ color:#ff9aa8; }}
.winrate-meta {{ color:#7790aa;font-size:11px;text-align:right;line-height:1.5; }}
.augment-stats {{ margin-top:10px;display:inline-block;padding:8px 13px;border-radius:10px;background:rgba(40,120,200,.13);border:1px solid rgba(70,150,230,.3);color:#9fe0ff;font-size:14px;font-weight:800; }}
footer {{ position:relative;color:#647b95;text-align:center;font-size:12px;padding:7px 0 2px; }}
</style></head><body>{body}</body></html>"""


def _recommendation_card(item: AugmentRecommendation, images: dict[str, str]) -> str:
    augment = item.augment
    image = _image_tag(images.get(augment.icon_url, ""), augment.name_zh, "augment-icon")
    stats = []
    if item.win_rate:
        stats.append(f"胜率 {item.win_rate}")
    if item.pick_rate:
        stats.append(f"登场率 {item.pick_rate}")
    if item.games:
        stats.append(f"{item.games} 场")
    stat_html = f'<div class="stats">{_safe(" · ".join(stats))}</div>' if stats else ""
    return (
        '<div class="recommendation">'
        f'<div class="rank">#{item.rank}</div>{image}<div class="rec-copy">'
        f'<div class="rec-name">{_safe(augment.name_zh)}</div>{stat_html}</div></div>'
    )


def _ranking_card(item: ChampionSummary, images: dict[str, str]) -> str:
    image = _image_tag(images.get(item.icon_url, ""), item.name, "ranking-avatar")
    roles = "".join(f'<span class="role">{_safe(_role_label(role))}</span>' for role in item.tags)
    values = []
    if item.win_rate is not None:
        values.append(f"胜率 {item.win_rate * 100:.2f}%")
    if item.pick_rate is not None:
        values.append(f"登场率 {item.pick_rate * 100:.2f}%")
    if item.games is not None:
        values.append(f"{item.games:,} 场")
    stats = f'<div class="stats">{_safe(" · ".join(values))}</div>' if values else ""
    delta = ""
    if item.rank_delta:
        direction = "rank-down" if item.rank_delta.startswith("-") else "rank-up"
        delta = f'<span class="{direction}">{_safe(item.rank_delta)}</span>'
    return (
        '<article class="ranking-card">'
        f'<div class="ranking-position">#{item.stats_rank or "-"}</div>{image}'
        f'<div class="ranking-copy"><div class="ranking-name">{_safe(item.name)} {delta}</div>'
        f'<div class="ranking-title">{_safe(item.title)}</div><div class="role-list">{roles}</div>{stats}</div>'
        '</article>'
    )


def _winrate_section(
    title: str,
    items: list[ChampionSummary],
    images: dict[str, str],
    kind: str,
    prefix: str,
) -> str:
    rows = "".join(
        _winrate_row(index, item, images, kind)
        for index, item in enumerate(items, start=1)
    )
    if not rows:
        rows = '<div class="mini-empty">暂无数据</div>'
    order = "降序" if kind == "top" else "升序"
    return (
        f'<section class="winrate-panel {kind}">'
        f'<div class="section-title"><h2>{_safe(title)} · {prefix} {len(items)}</h2>'
        f'<span>按胜率{order}</span></div>'
        f'<div class="winrate-list">{rows}</div></section>'
    )


def _winrate_row(
    index: int,
    item: ChampionSummary,
    images: dict[str, str],
    kind: str,
) -> str:
    image = _image_tag(images.get(item.icon_url, ""), item.name, "winrate-avatar")
    roles = "".join(f'<span class="role">{_safe(_role_label(role))}</span>' for role in item.tags)
    win_rate = f"{item.win_rate * 100:.2f}%" if item.win_rate is not None else "—"
    details = []
    if item.pick_rate is not None:
        details.append(f"登场率 {item.pick_rate * 100:.2f}%")
    if item.games is not None:
        details.append(f"{item.games:,} 场")
    if item.stats_tier:
        details.append(f"T{item.stats_tier}")
    delta = ""
    if item.rank_delta:
        direction = "rank-down" if item.rank_delta.startswith("-") else "rank-up"
        delta = f'<span class="{direction}">{_safe(item.rank_delta)}</span>'
    meta = _safe(" · ".join(details)) if details else "—"
    return (
        '<div class="winrate-row">'
        f'<div class="winrate-position">{index}</div>'
        f'{image}'
        f'<div class="winrate-copy"><div class="winrate-name">{_safe(item.name)} {delta}</div>'
        f'<div class="winrate-title">{_safe(item.title)}</div>'
        f'<div class="role-list">{roles}</div></div>'
        f'<div class="winrate-value {kind}">{_safe(win_rate)}</div>'
        f'<div class="winrate-meta">{meta}</div>'
        "</div>"
    )


def _augment_stats_html(item: Augment) -> str:
    """渲染海克斯的胜率 / 选取率 / 场次；无统计时返回空串。"""
    values = []
    if item.win_rate:
        values.append(f"胜率 {item.win_rate}")
    if item.pick_rate:
        values.append(f"选取率 {item.pick_rate}")
    if item.games:
        values.append(f"{item.games} 场")
    if not values:
        return ""
    return f'<div class="augment-stats">{" · ".join(_safe(value) for value in values)}</div>'


def _role_label(value: str) -> str:
    return {
        "fighter": "战士",
        "mage": "法师",
        "tank": "坦克",
        "marksman": "射手",
        "support": "辅助",
        "assassin": "刺客",
    }.get(str(value).casefold(), str(value))


def _source_label(value: str) -> str:
    return {
        "tencent": "腾讯公开快照",
        "iesdev": "ARAMGG Build 统计",
        "aramgg-client-upload": "ARAMGG 客户端匿名上传",
        "opgg": "OP.GG",
    }.get(str(value).casefold(), str(value))


def _region_label(value: str) -> str:
    return {"cn": "国服", "world": "全球"}.get(str(value).casefold(), str(value))


def _option_module(
    title: str,
    options: Iterable[LoadoutOption],
    images: dict[str, str],
    hint: str,
    *,
    wide: bool = False,
) -> str:
    option_list = list(options)
    rows = "".join(
        f'<div class="option"><div>{_items_html(option.items, images)}{_option_stats(option)}</div></div>'
        for option in option_list
    )
    if not rows:
        rows = '<div class="mini-empty">暂无数据</div>'
    classes = "module wide" if wide else "module"
    return f'<div class="{classes}"><div class="module-head"><b>{_safe(title)}</b><span>{_safe(hint)}</span></div>{rows}</div>'


def _option_stats(option: LoadoutOption) -> str:
    values = []
    if option.win_rate:
        values.append(f"胜率 {option.win_rate}")
    if option.pick_rate:
        values.append(f"登场率 {option.pick_rate}")
    if option.games:
        values.append(f"{option.games} 场")
    return f'<div class="stats">{_safe(" · ".join(values))}</div>' if values else ""


def _items_module(title: str, items: Iterable[ItemRef], images: dict[str, str], hint: str) -> str:
    values = list(items)
    body = _items_html(values, images) if values else '<div class="mini-empty">暂无数据</div>'
    return f'<div class="module"><div class="module-head"><b>{_safe(title)}</b><span>{_safe(hint)}</span></div>{body}</div>'


def _skill_order_module(order: tuple[str, ...]) -> str:
    body = " → ".join(order) if order else "暂无数据"
    return '<div class="module"><div class="module-head"><b>技能加点顺序</b><span>海斗统计</span></div>' f'<div class="skill-order">{_safe(body)}</div></div>'


def _build_variant_card(variant: BuildVariant, images: dict[str, str]) -> str:
    stats = _raw_stats(variant.win_rate, variant.pick_rate, variant.games)
    skills = "".join(
        '<div class="skill-sequence">'
        f'{_safe(" → ".join(option.order))}{_raw_stats(option.win_rate, option.pick_rate, option.games)}'
        '</div>'
        for option in variant.skill_orders
    ) or '<div class="mini-empty">暂无完整技能序列</div>'
    blocks = [
        ("召唤师技能", _compact_options(variant.summoner_spells, images)),
        ("完整技能序列", skills),
        ("出门装", _compact_options(variant.starter_items, images)),
        ("核心装备", _compact_options(variant.core_items, images)),
        ("情境装备", _compact_options(variant.situational_items, images)),
    ]
    content = "".join(
        f'<div class="variant-block"><b>{_safe(title)}</b>{body}</div>'
        for title, body in blocks
        if body
    )
    return (
        '<article class="variant"><div class="variant-head">'
        f'<span class="variant-name">{_safe(variant.name)}</span>{stats}</div>'
        f'<div class="variant-grid">{content}</div></article>'
    )


def _compact_options(options: Iterable[LoadoutOption], images: dict[str, str]) -> str:
    values = list(options)
    if not values:
        return ""
    return "".join(
        f'<div class="option"><div>{_items_html(item.items, images)}{_option_stats(item)}</div></div>'
        for item in values
    )


def _augment_trio_card(item: AugmentTrio, images: dict[str, str]) -> str:
    icons = "".join(
        _image_tag(images.get(augment.icon_url, ""), augment.name_zh, "augment-icon")
        + f'<span class="item-name">{_safe(augment.name_zh)}</span>'
        for augment in item.augments
    )
    return f'<article class="trio-card"><div class="trio-icons">{icons}</div>{_raw_stats(item.win_rate, item.pick_rate, item.games)}</article>'


def _item_performance_card(item: ItemPerformance, images: dict[str, str]) -> str:
    image = _image_tag(
        _first_image(images, item.item.icon_url, item.item.fallback_icon_url, item.item.extra_icon_url),
        item.item.name,
        "item-icon",
    )
    return (
        f'<article class="item-performance">{image}<div><b>{_safe(item.item.name)}</b>'
        f'{_raw_stats(item.win_rate, item.pick_rate, item.games)}</div></article>'
    )


def _raw_stats(win_rate: str, pick_rate: str, games: str) -> str:
    values = []
    if win_rate:
        values.append(f"胜率 {win_rate}")
    if pick_rate:
        values.append(f"登场率 {pick_rate}")
    if games:
        values.append(f"{games} 场")
    return f'<div class="stats">{_safe(" · ".join(values))}</div>' if values else ""


def _route_card(route: FullBuildRoute, images: dict[str, str]) -> str:
    note = f'<div class="route-note">{_safe(route.note)}</div>' if route.note else ""
    return (
        '<article class="route"><div class="route-head">'
        f'<span class="route-name">{_safe(route.name)}</span>'
        f'<span class="route-source">{_safe(route.source)}</span></div>'
        f'{_items_html(route.items, images)}{note}</article>'
    )


def _items_html(items: Iterable[ItemRef], images: dict[str, str]) -> str:
    values = list(items)
    parts = []
    for index, item in enumerate(values):
        data = _first_image(
            images,
            item.icon_url,
            item.fallback_icon_url,
            item.extra_icon_url,
        )
        image = _image_tag(data, item.name, "item-icon")
        parts.append(f'<div class="item">{image}<span class="item-name">{_safe(item.name)}</span></div>')
        if index < len(values) - 1:
            parts.append('<span class="arrow">›</span>')
    return f'<div class="items">{"".join(parts)}</div>'


def _first_image(images: dict[str, str], *urls: str) -> str:
    for url in urls:
        value = images.get(url, "")
        if value.startswith("data:image/"):
            return value
    return ""


def finalize_image(
    raw: bytes,
    *,
    max_kb: int = 512,
    max_height: int = 12000,
) -> tuple[bytes, dict[str, Any]]:
    """把渲染结果压到聊天平台能稳定上传的体积。

    QQ / NapCat 的图片消息要先把富媒体上传到腾讯的 CDN，体积过大会在一次
    发送的等待窗口内传不完，表现为
    ``Timeout: NTEvent ... NodeIKernelMsgService/sendMsg``。

    控制体积的杠杆选择：

    * 体积已够小 → 保留无损 PNG；
    * 超限 → **优先缩小尺寸**，而不是先降质量。报告是文字密集的整页长图，
      同样字节预算下「更多像素 + 中等质量」比「更少像素 + 高质量」更易读；
    * 缩到 ``_MIN_WIDTH`` 仍超限 → 才退到兜底质量。

    性能约束（这张图有数百万像素，任何一次多余编码都要几百毫秒）：

    * 大图不尝试 PNG：整页图的 PNG 编码本身就要近一秒，且几乎必然超出上限；
    * ``optimize=True`` 多跑一遍 Huffman 统计，单次编码约 6 倍开销、只省 5%
      体积，因此只在最终版本上付一次；
    * 缩放比例由**一次探测编码**按 ``_SCALE_EXPONENT`` 反推，最多微调 2 次，
      不做逐档质量试探。

    返回值第二项是体积信息（格式 / 宽 / 高 / 字节数），供调用方记录日志。
    """
    target = max(64, int(max_kb)) * 1024
    with PILImage.open(BytesIO(raw)) as source:
        source.load()
        image = _flatten_to_rgb(source)
        if image.height > max_height:
            ratio = max_height / image.height
            image = image.resize(
                (max(1, int(image.width * ratio)), max_height),
                PILImage.Resampling.LANCZOS,
            )

        # 1) 小图才值得尝试无损 PNG
        if image.width * image.height <= _PNG_ATTEMPT_MAX_PIXELS:
            png = _encode_png(image)
            if len(png) <= target:
                return png, _image_meta("PNG", image, len(png))

        # 2) 一次探测，拿到该图的体积密度
        probe = _encode_jpeg(image, _BASE_QUALITY, cheap=True)
        if len(probe) <= target:
            return _finish_image(image, probe, target)

        # 3) 超限：按实测幂次反推缩放比例，最多微调两次
        current = image
        scale = min(1.0, (target / len(probe)) ** (1 / _SCALE_EXPONENT)) * 0.99
        for _ in range(3):
            width = max(_MIN_WIDTH, int(round(current.width * scale)))
            if width >= current.width:
                break
            height = max(1, round(current.height * width / current.width))
            current = current.resize((width, height), PILImage.Resampling.LANCZOS)
            data = _encode_jpeg(current, _BASE_QUALITY, cheap=True)
            if len(data) <= target:
                return _finish_image(current, data, target)
            scale = min(1.0, (target / len(data)) ** (1 / _SCALE_EXPONENT)) * 0.99

        # 4) 缩到下限仍超限：退到兜底质量，交给调用方决定是否降级为文字
        for quality in _FALLBACK_QUALITIES:
            data = _encode_jpeg(current, quality, cheap=True)
            if len(data) <= target:
                break
        final_bytes = _encode_jpeg(current, quality, cheap=False)
        return final_bytes, _image_meta(f"JPEG q{quality}", current, len(final_bytes))


def _finish_image(
    image: "PILImage.Image",
    cheap_bytes: bytes,
    target: int,
) -> tuple[bytes, dict[str, Any]]:
    """对已达标的版本做最终封装：有余量就提质量，并只付一次 optimize。"""
    quality = _BASE_QUALITY
    if len(cheap_bytes) < target * 0.8:
        bumped = _encode_jpeg(image, _QUALITY_BUMP, cheap=True)
        if len(bumped) <= target:
            quality, cheap_bytes = _QUALITY_BUMP, bumped
    final_bytes = _encode_jpeg(image, quality, cheap=False)
    if len(final_bytes) > target and len(cheap_bytes) <= target:
        # optimize 反而略超上限（罕见），退回未优化版本保证能发出去
        final_bytes = cheap_bytes
    return final_bytes, _image_meta(f"JPEG q{quality}", image, len(final_bytes))


def _flatten_to_rgb(image: "PILImage.Image") -> "PILImage.Image":
    """统一转成不透明 RGB；带透明通道时按模板背景色合成。"""
    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    if not has_alpha:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    canvas = PILImage.new("RGB", rgba.size, _DOC_BACKGROUND)
    canvas.paste(rgba, mask=rgba.getchannel("A"))
    return canvas


def _encode_png(image: "PILImage.Image") -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _encode_jpeg(image: "PILImage.Image", quality: int, *, cheap: bool) -> bytes:
    """编码为渐进式 JPEG。

    ``cheap=True`` 跳过 Huffman 统计（``optimize``），体积约大 5%，但单次编码
    快得多；用于上限试探。最终版本用 ``cheap=False`` 换取更小体积。
    """
    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=quality,
        optimize=not cheap,
        progressive=True,
    )
    return output.getvalue()


def _image_meta(fmt: str, image: "PILImage.Image", size: int) -> dict[str, Any]:
    return {
        "format": fmt,
        "width": image.width,
        "height": image.height,
        "bytes": size,
        "kb": max(1, round(size / 1024)),
    }


def normalize_render_result(value: Any) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif hasattr(value, "getvalue"):
        raw = bytes(value.getvalue())
    elif isinstance(value, str):
        raw = _decode_render_string(value)
    else:
        raise ValueError("html_render 返回了不支持的图片类型")
    if not raw:
        raise ValueError("html_render 返回了空图片")
    try:
        with PILImage.open(BytesIO(raw)) as image:
            image.load()
            output = BytesIO()
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.mode else "RGB")
            image.save(output, format="PNG", optimize=True)
            return output.getvalue()
    except Exception as error:
        raise ValueError("html_render 返回的内容不是有效图片") from error


def _decode_render_string(value: str) -> bytes:
    value = value.strip()
    if value.startswith("base64://"):
        return _decode_base64(value[9:])
    if value.startswith("data:image/") and "," in value:
        return _decode_base64(value.split(",", 1)[1])
    if value.startswith("file:"):
        return Path(unquote(urlparse(value).path)).read_bytes()
    path = Path(value)
    if path.is_file():
        return path.read_bytes()
    return _decode_base64(value)


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("无效的 Base64 图片") from error


def _safe(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _tier_label(value: str) -> str:
    return _TIER_LABELS.get(str(value or "Unknown"), str(value or "Unknown"))


def _tier_class(value: str) -> str:
    text = str(value or "").casefold()
    for name in ("prismatic", "gold", "silver", "bronze"):
        if name in text:
            return name
    return "unknown"


def _image_tag(data_uri: str, alt: str, class_name: str) -> str:
    if data_uri.startswith("data:image/"):
        return f'<img class="{class_name}" src="{html.escape(data_uri, quote=True)}" alt="{_safe(alt)}">'
    return f'<div class="{class_name} image-placeholder">HEX</div>'
