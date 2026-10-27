from __future__ import annotations

import base64
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from astrbot_plugin_hextechmayhem.models import (
    Augment,
    AugmentRecommendation,
    AugmentTrio,
    BuildVariant,
    ChampionSummary,
    ChampionDetail,
    FullBuildRoute,
    HeroReport,
    ItemRef,
    ItemPerformance,
    LoadoutOption,
    RelatedArticle,
    SkillOrderOption,
)
from astrbot_plugin_hextechmayhem.renderer import (
    ReportRenderer,
    finalize_image,
    normalize_render_result,
)


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), "#123456").save(output, format="PNG")
    return output.getvalue()


def noisy_png(width: int = 1120, height: int = 1600) -> bytes:
    """生成难以压缩的噪点图，用于模拟长报告页的体积。"""
    image = Image.effect_noise((width, height), 120).convert("RGB")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class RendererTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.renderer = ReportRenderer()
        champion = ChampionDetail(
            id="Aatrox",
            key="266",
            name="暗裔剑魔",
            title="亚托克斯",
            tags=("Fighter",),
            version="16.17.1",
            splash_url="https://example.invalid/splash.jpg",
            icon_url="",
        )
        augment = Augment(
            "1",
            "Gold",
            "<b>珠光</b>",
            "Jeweled Gauntlet",
            "技能可以暴击。",
            "暴击伤害受修正。",
        )
        items = tuple(ItemRef(str(3000 + i), f"装备{i}") for i in range(6))
        self.report = HeroReport(
            champion=champion,
            patch="16.18",
            tier="2 段位",
            augments={"Prismatic": (), "Gold": (AugmentRecommendation(augment, 1),), "Silver": ()},
            summoner_spells=(LoadoutOption(items[:2]),),
            skill_order=("Q", "E", "W"),
            starter_items=(LoadoutOption(items[:2]),),
            boots=(items[2], items[3]),
            core_builds=(LoadoutOption(items[:3]),),
            build_variants=(
                BuildVariant(
                    "暴击流",
                    "54.00%",
                    "20.00%",
                    "5,000",
                    skill_orders=(SkillOrderOption(("Q", "E", "Q", "W", "R"), "55.00%"),),
                    situational_items=(LoadoutOption(items[3:5]),),
                ),
            ),
            augment_trios=(AugmentTrio((augment, augment, augment), "61.00%", games="200"),),
            item_performance=(ItemPerformance(items[0], "53.00%", "22.00%", "999"),),
            provenance=("英雄统计：tencent / CN",),
            related_articles=(RelatedArticle("测试攻略", "https://example.invalid"),),
            full_builds=(FullBuildRoute("测试路线", "<img src=x>", items),),
            unavailable_sources=("OP.GG<script>",),
            stale_sources=("League Wiki",),
        )

    def test_hero_html_has_all_modules_and_no_skill_archive(self) -> None:
        source = self.renderer.hero_html(self.report, {})
        self.assertNotIn("英雄简介", source)
        self.assertIn("&lt;b&gt;珠光&lt;/b&gt;", source)
        self.assertIn("海克斯推荐", source)
        self.assertIn("召唤师技能", source)
        self.assertIn("技能加点顺序", source)
        self.assertIn("完整六件套", source)
        self.assertIn("流派与完整技能方案", source)
        self.assertIn("三海克斯组合", source)
        self.assertIn("热门单件表现", source)
        self.assertIn("数据说明与相关攻略", source)
        self.assertIn("Mayhempedia 社区攻略", source)
        self.assertNotIn("技能档案", source)
        self.assertNotIn("被动", source)
        self.assertIn("League Wiki 旧缓存", source)

    async def test_renderer_normalizes_bytes_to_png(self) -> None:
        async def render(*_args, **_kwargs):
            return png_bytes()

        result = await self.renderer.hero_report(render, self.report, {})
        self.assertTrue(result.startswith(b"\x89PNG"))

    def test_normalize_supports_base64_data_uri_and_file(self) -> None:
        raw = png_bytes()
        encoded = base64.b64encode(raw).decode("ascii")
        self.assertTrue(normalize_render_result(f"base64://{encoded}").startswith(b"\x89PNG"))
        self.assertTrue(normalize_render_result(f"data:image/png;base64,{encoded}").startswith(b"\x89PNG"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "render.png"
            path.write_bytes(raw)
            self.assertTrue(normalize_render_result(str(path)).startswith(b"\x89PNG"))

    def test_augment_html_contains_card_and_translated_mechanism(self) -> None:
        item = Augment(
            "1",
            "Gold",
            "珠光护手",
            "Jeweled Gauntlet",
            "技能可以暴击。",
            "暴击伤害受修正。",
        )
        source = self.renderer.augment_html([item], {}, query="珠光", total=1, stale=False)
        self.assertIn("珠光护手", source)
        self.assertIn("机制补充", source)
        self.assertIn("黄金阶", source)

    def test_ranking_html_groups_tiers_and_shows_metadata(self) -> None:
        rankings = [
            ChampionSummary(
                "Aatrox",
                "266",
                "亚托克斯",
                "暗裔剑魔",
                tags=("fighter",),
                icon_url="https://example.invalid/aatrox.png",
                win_rate=0.5312,
                pick_rate=0.041,
                stats_tier="1",
                stats_patch="16.19",
                stats_rank=1,
                stats_date="2026-09-27",
                stats_source="tencent",
                stats_region="CN",
                rank_delta="+2",
            )
        ]
        source = self.renderer.ranking_html(rankings, {}, source="aramgg", stale=False)
        self.assertIn("英雄综合强度排名", source)
        self.assertIn("PATCH 16.19", source)
        self.assertIn("2026-09-27", source)
        self.assertIn("腾讯公开快照", source)
        self.assertIn("国服", source)
        self.assertIn("T1", source)
        self.assertIn("战士", source)
        self.assertIn("53.12%", source)
        self.assertIn("+2", source)
        self.assertIn("ARAMGG", source)

    def test_winrate_ranking_html_shows_both_ends(self) -> None:
        top = [
            ChampionSummary(
                "Yasuo",
                "157",
                "亚索",
                "疾风剑豪",
                tags=("fighter",),
                win_rate=0.5612,
                pick_rate=0.1210,
                stats_tier="1",
                stats_patch="16.21",
                stats_date="2026-10-24",
                stats_source="tencent",
                stats_region="CN",
                rank_delta="+3",
            )
        ]
        bottom = [
            ChampionSummary(
                "Teemo",
                "17",
                "提莫",
                "迅捷斥候",
                win_rate=0.4412,
                pick_rate=0.0202,
            )
        ]
        source = self.renderer.winrate_ranking_html(
            top, bottom, {}, source="aramgg", stale=False
        )
        self.assertIn("英雄胜率榜", source)
        self.assertIn("胜率最高", source)
        self.assertIn("胜率最低", source)
        self.assertIn("亚索", source)
        self.assertIn("提莫", source)
        self.assertIn("56.12%", source)
        self.assertIn("44.12%", source)
        self.assertIn("PATCH 16.21", source)
        self.assertIn("2026-10-24", source)
        self.assertIn("腾讯公开快照", source)
        self.assertIn("国服", source)
        self.assertIn("+3", source)
        # 两端各自使用不同的强调色类名
        self.assertIn('class="winrate-value top"', source)
        self.assertIn('class="winrate-value bottom"', source)

    def test_winrate_ranking_html_handles_empty_side(self) -> None:
        source = self.renderer.winrate_ranking_html(
            [], [], {}, source="opgg", stale=True
        )
        self.assertIn("缓存数据", source)
        self.assertIn("暂无数据", source)

    def test_augment_html_renders_stats_when_present(self) -> None:
        item = Augment(
            "1",
            "Gold",
            "珠光护手",
            "Jeweled Gauntlet",
            "技能可以暴击。",
            win_rate="53.12%",
            pick_rate="12.34%",
            games="1,234",
            stats_source="aramgg-client-upload",
            stats_region="WORLD",
        )
        source = self.renderer.augment_html([item], {}, query="珠光", total=1, stale=False)
        self.assertIn('class="augment-stats"', source)
        self.assertIn("53.12%", source)
        self.assertIn("12.34%", source)
        self.assertIn("1,234", source)
        self.assertIn("选取率", source)
        self.assertIn("ARAMGG 客户端匿名上传", source)

    def test_augment_html_omits_stats_block_without_stats(self) -> None:
        item = Augment("1", "Gold", "珠光护手", "Jeweled Gauntlet", "技能可以暴击。")
        source = self.renderer.augment_html([item], {}, query="珠光", total=1, stale=False)
        self.assertNotIn('class="augment-stats"', source)
        self.assertIn("缺失统计不补 0", source)


class ImageSizingTest(unittest.IsolatedAsyncioTestCase):
    """图片体积控制：QQ 富媒体上传对体积敏感，超限会触发发送超时。"""

    def test_small_render_is_kept_as_png(self) -> None:
        data, meta = finalize_image(png_bytes(), max_kb=512)
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertEqual(meta["format"], "PNG")
        self.assertEqual((meta["width"], meta["height"]), (8, 8))
        self.assertEqual(meta["bytes"], len(data))

    def test_large_render_is_compressed_under_limit(self) -> None:
        raw = noisy_png()
        self.assertGreater(len(raw), 512 * 1024, "用例前提：原始图片需超过上限")
        data, meta = finalize_image(raw, max_kb=512)
        self.assertLessEqual(len(data), 512 * 1024)
        self.assertTrue(meta["format"].startswith("JPEG"))
        # JPEG 以 SOI 标记开头
        self.assertTrue(data.startswith(b"\xff\xd8"))
        self.assertGreaterEqual(meta["kb"], 1)

    def test_transparent_pixels_are_flattened_to_theme_background(self) -> None:
        buffer = BytesIO()
        Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(buffer, format="PNG")
        data, meta = finalize_image(buffer.getvalue(), max_kb=512)
        self.assertEqual(meta["format"], "PNG")
        with Image.open(BytesIO(data)) as result:
            self.assertEqual(result.mode, "RGB")
            # 模板背景色 #050914
            self.assertEqual(result.getpixel((5, 5)), (5, 9, 20))

    def test_extreme_target_still_returns_an_image(self) -> None:
        raw = noisy_png(1000, 1400)
        data, meta = finalize_image(raw, max_kb=64)
        self.assertTrue(data)
        self.assertIn("format", meta)
        # 下限目标允许压不到，但不能崩溃或返回空
        self.assertGreater(meta["bytes"], 0)

    async def test_render_applies_configured_limit(self) -> None:
        renderer = ReportRenderer(max_image_kb=512)
        raw = noisy_png()

        async def render(*_args, **_kwargs):
            return raw

        result = await renderer.augment_report(
            render, [], {}, query="体积测试", total=0, stale=False
        )
        self.assertLessEqual(len(result), 512 * 1024)
        self.assertLess(len(result), len(raw), "压缩后体积应明显小于 PNG 原图")
        self.assertTrue(renderer.last_render_meta["format"].startswith("JPEG"))
        self.assertEqual(renderer.last_render_meta["bytes"], len(result))
        # 耗时用于日志排查，必须是数字
        self.assertIsInstance(renderer.last_render_meta["ms"], int)
        self.assertGreaterEqual(renderer.last_render_meta["ms"], 0)


if __name__ == "__main__":
    unittest.main()
