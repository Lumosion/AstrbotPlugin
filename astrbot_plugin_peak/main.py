from __future__ import annotations

from io import BytesIO
import re
import tempfile
from typing import List, Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

PLUGIN_NAME = "astrbot_plugin_peak"
DEFAULT_URL = "https://peak.joaqu1m.com/zh-cn/"

VARIANT_TRANSLATIONS = {
    "Bombs": "炸弹",
    "Geyser Hell": "间歇泉地狱",
    "Blue Beach": "蓝灰色沙滩",
    "Red Beach": "红色沙滩",
    "Black Sand": "黑沙",
    "Jelly Hell": "水母",
    "Snake Beach": "蛇滩",
    "Ivy": "常春藤",
    "Lava": "熔岩",
    "Pillars": "柱状地形",
    "Sky Jungle": "天空丛林",
    "Thorny": "荆棘",
    "Cave Mania": "洞穴狂热",
    "Clearcut": "砍伐林",
    "Deep Water": "深水",
    "Deep Woods": "深林",
    "Spikes": "冰刺",
    "Cactus Forest": "仙人掌森林",
    "Cactus Hell": "仙人掌地狱",
    "Dynamite Hell": "炸药地狱",
    "Scorpions Hell": "蝎子地狱",
    "Tumbler Hell": "翻滚者地狱",
}
REGION_TRANSLATIONS = {
    "Shore": "海岸",
    "Tropics": "雨林",
    "Roots": "森蕈",
    "Alpine": "雪山",
    "Mesa": "方山",
    "Caldera": "火山",
    "Gloom": "雾沼",
    "The Kiln": "熔炉",
    "The Citadel": "城塞",
    "The Peak": "顶峰",
}
BIOME_TABLE = [
    (
        "海岸",
        "标准海滩区域。",
        [
            ("Default", "标准海滩"),
            ("Blue Beach", "蓝灰色沙滩"),
            ("Red Beach", "红色沙滩"),
            ("Black Sand", "黑沙；巨型海胆更多，桥变为锁链"),
            ("Jelly Hell", "水母大量增加"),
            ("Snake Beach", "出现大型蛇形岩石"),
        ],
    ),
    (
        "雨林",
        "标准雨林区域。",
        [
            ("Default", "标准雨林"),
            ("Bombs", "炸弹；蘑菇大量增加"),
            ("Ivy", "紫色环境，毒性植物增加"),
            ("Lava", "出现熔岩管"),
            ("Pillars", "柱状地形更多、更高"),
            ("Sky Jungle", "大量浮空岛"),
            ("Thorny", "带刺巨型藤蔓大量增加"),
        ],
    ),
    (
        "森蕈",
        "标准红杉森林区域。",
        [
            ("Default", "标准红杉森林"),
            ("Cave Mania", "中央岩石和洞穴地形增加"),
            ("Clearcut", "前段几乎没有红杉，替换为大量弹跳蘑菇"),
            ("Deep Water", "深水、红色水体和瀑布更多，水会持续产生孢子"),
            ("Deep Woods", "树木大量增加，森林极其密集"),
        ],
    ),
    (
        "雪山",
        "标准雪山区域。",
        [
            ("Default", "标准雪山"),
            ("Geyser Hell", "间歇泉大量增加"),
            ("Lava", "出现熔岩管"),
            ("Spikes", "巨型冰刺大量出现"),
        ],
    ),
    (
        "方山",
        "标准沙漠区域。",
        [
            ("No Variant", "无变体，标准沙漠"),
            ("Cactus Forest", "方山上的仙人掌大量增加"),
            ("Cactus Hell", "攀爬区域的仙人掌大量增加"),
            ("Dynamite Hell", "地面炸药大量增加"),
            ("Scorpions Hell", "蝎子大量增加"),
            ("Tumbler Hell", "翻滚者出现率约为普通的 2.5 倍"),
        ],
    ),
    (
        "火山",
        "火山区域，目前没有独立 Variant 系统。",
        [("-", "当前没有独立变体")],
    ),
    (
        "雾沼",
        "雾沼区域，目前没有独立 Variant 系统。",
        [("-", "当前没有独立变体")],
    ),
    (
        "熔炉",
        "熔炉区域，目前没有独立 Variant 系统。",
        [("-", "当前没有独立变体")],
    ),
    (
        "城塞",
        "城塞区域，主要通过楼层和陷阱布局变化。",
        [("-", "当前没有传统变体")],
    ),
    ("顶峰", "终点区域，无传统 Variant。", [("-", "终点区域，无传统变体")]),
]
FONT_PATHS = [
    "C:\\Windows\\Fonts\\msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


class PeakFetchError(Exception):
    """PEAK 数据获取异常。"""


@register(
    PLUGIN_NAME,
    "OpenAI",
    "获取 PEAK 每日地图，无需 AI。",
    "1.0.0",
    "https://peak.joaqu1m.com/zh-cn/",
)
class PeakPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.url = DEFAULT_URL
        self.timeout = httpx.Timeout(
            connect=10.0,
            read=15.0,
            write=10.0,
            pool=10.0,
        )

    async def _fetch_page(self) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=headers,
                follow_redirects=True,
            ) as client:
                response = await client.get(self.url)

            response.raise_for_status()

        except httpx.TimeoutException as exc:
            raise PeakFetchError("请求 PEAK 网站超时。") from exc
        except httpx.HTTPStatusError as exc:
            raise PeakFetchError(
                f"PEAK 网站返回 HTTP {exc.response.status_code}。"
            ) from exc
        except httpx.RequestError as exc:
            raise PeakFetchError(f"无法连接 PEAK 网站：{exc}") from exc

        return response.text

    @staticmethod
    def _clean_text(text: str) -> str:
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n+", "\n", text)
        return text.strip()

    @staticmethod
    def _extract_map_date(text: str) -> Optional[str]:
        patterns = [
            r"今天[（(](\d{4}-\d{2}-\d{2})[）)]",
            r"今日[（(](\d{4}-\d{2}-\d{2})[）)]",
            r"Today[ \t]*[（(](\d{4}-\d{2}-\d{2})[）)]",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
        return match.group(1) if match else None

    @staticmethod
    def _extract_route(text: str) -> Optional[str]:
        patterns = [
            r"今天[（(]\d{4}-\d{2}-\d{2}[）)]：(.+?)。PEAK地图每天",
            r"今天[（(]\d{4}-\d{2}-\d{2}[）)]：(.+?)。地图每天",
            r"今天[（(]\d{4}-\d{2}-\d{2}[）)]：(.+?)。",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                route = match.group(1).strip()
                route = route.split("PEAK地图每天")[0]
                route = route.split("地图每天")[0]
                return route.strip()

        return None

    @staticmethod
    def _normalize_stage(stage: str) -> str:
        stage = stage.replace("(", "（").replace(")", "）")
        for english, chinese in REGION_TRANSLATIONS.items():
            stage = re.sub(
                rf"(?<![\u4e00-\u9fff]){re.escape(english)}(?![\u4e00-\u9fff])",
                chinese,
                stage,
                flags=re.IGNORECASE,
            )
        for english, chinese in VARIANT_TRANSLATIONS.items():
            stage = re.sub(english, chinese, stage, flags=re.IGNORECASE)
        return re.sub(r"\s+（", "（", stage).strip()

    @staticmethod
    def _extract_route_stages(route: str) -> List[str]:
        return [
            PeakPlugin._normalize_stage(stage.strip())
            for stage in re.split(r"\s*(?:→|->)\s*", route)
            if stage.strip()
        ]

    @staticmethod
    def _stage_description(stage: str) -> str:
        stage_parts = stage.split("（", 1)
        base_name = stage_parts[0].strip()
        variant_name = ""
        if len(stage_parts) == 2:
            variant_name = stage_parts[1].rstrip("）").strip()

        for region, description, _ in BIOME_TABLE:
            if base_name == region:
                if variant_name:
                    for variant, variant_description in _:
                        normalized_variant = PeakPlugin._normalize_stage(variant)
                        if variant_name == normalized_variant:
                            return variant_description
                return description
        return "网页暂未提供该区域的简介。"

    @staticmethod
    def _format_variant_table() -> str:
        result = ["📚 PEAK 全部地图变体总表", ""]
        for index, (region, description, variants) in enumerate(BIOME_TABLE, start=1):
            result.extend([f"{index}. {region}", f"简介：{description}"])
            for variant, variant_description in variants:
                if variant == "Default":
                    variant_name = "默认"
                elif variant == "No Variant":
                    variant_name = "无变体"
                elif variant == "-":
                    variant_name = "无独立变体"
                else:
                    variant_name = PeakPlugin._normalize_stage(variant)
                result.append(f"  - {variant_name}：{variant_description}")
            result.append("")
        return "\n".join(result)

    @staticmethod
    def _load_font(size: int) -> ImageFont.ImageFont:
        for font_path in FONT_PATHS:
            try:
                return ImageFont.truetype(font_path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _extract_stage_icon_urls(
        soup: BeautifulSoup,
        stages: List[str],
    ) -> dict[str, str]:
        region_icons: dict[str, str] = {}
        image_candidates = soup.find_all("img")

        for text_node in soup.find_all(string=re.compile(r"今日.*生效中")):
            container = text_node.parent
            for _ in range(6):
                if container is None:
                    break
                card_images = container.find_all("img")
                card_urls = []
                for image in card_images:
                    source = (
                        image.get("src")
                        or image.get("data-src")
                        or image.get("data-lazy-src")
                    )
                    if source:
                        image_url = urljoin(DEFAULT_URL, source)
                        image_path = image_url.lower().split("?", 1)[0]
                        if image_path.endswith((".jpg", ".jpeg", ".png", ".webp")):
                            card_urls.append(image_url)
                if len(card_urls) >= len(stages):
                    for stage, image_url in zip(stages, card_urls):
                        region = stage.split("（", 1)[0].strip()
                        region_icons[region] = image_url
                    return region_icons
                container = container.parent

        for stage in stages:
            region = stage.split("（", 1)[0].strip()
            english_names = [
                english
                for english, chinese in REGION_TRANSLATIONS.items()
                if chinese == region
            ]
            names = [region, *english_names]

            for image in image_candidates:
                source = (
                    image.get("src")
                    or image.get("data-src")
                    or image.get("data-lazy-src")
                )
                if not source:
                    continue

                image_url = urljoin(DEFAULT_URL, source)
                image_path = image_url.lower().split("?", 1)[0]
                if not image_path.endswith((".jpg", ".jpeg", ".png", ".webp")):
                    continue

                attributes = " ".join(
                    str(value)
                    for key, value in image.attrs.items()
                    if key in {"alt", "title", "class", "id"}
                )
                if any(name.lower() in attributes.lower() for name in names):
                    region_icons[region] = image_url
                    break

        return region_icons

    async def _create_route_image(
        self,
        html: str,
        date: Optional[str],
        stages: List[str],
    ) -> Optional[str]:
        try:
            soup = BeautifulSoup(html, "html.parser")
            icon_urls = self._extract_stage_icon_urls(soup, stages)
            stage_icons: dict[str, Image.Image] = {}

            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                for region, icon_url in icon_urls.items():
                    try:
                        response = await client.get(icon_url)
                        response.raise_for_status()
                        with Image.open(BytesIO(response.content)) as icon:
                            stage_icons[region] = icon.convert("RGBA")
                    except (httpx.HTTPError, OSError) as exc:
                        logger.warning(f"无法加载 {region} 地图图标 {icon_url}: {exc}")

            width = 900
            row_height = 125
            height = 150 + row_height * len(stages)
            canvas = Image.new("RGB", (width, height), "#101820")
            draw = ImageDraw.Draw(canvas)
            title_font = self._load_font(42)
            date_font = self._load_font(24)
            stage_font = self._load_font(30)
            badge_font = self._load_font(36)

            draw.text((55, 32), "PEAK 今日地图", fill="#F7C873", font=title_font)
            if date:
                draw.text((58, 88), date, fill="#B8C7D9", font=date_font)

            colors = ["#F28F3B", "#63B66B", "#6FA8DC", "#9B7EDE", "#D96C75"]
            for index, stage in enumerate(stages):
                y = 150 + index * row_height
                draw.rounded_rectangle(
                    (40, y, width - 40, y + 100),
                    radius=18,
                    fill="#1B2935",
                    outline=colors[index % len(colors)],
                    width=3,
                )
                draw.text(
                    (65, y + 29),
                    str(index + 1),
                    fill=colors[index % len(colors)],
                    font=stage_font,
                )

                base_name = stage.split("（", 1)[0].strip()
                icon = stage_icons.get(base_name)
                if icon is not None:
                    icon = icon.copy()
                    icon.thumbnail((78, 78))
                    icon_x = 113
                    icon_y = y + (100 - icon.height) // 2
                    canvas.paste(icon, (icon_x, icon_y), icon)

                badge_colors = {
                    "海岸": "#2D8CCB",
                    "雨林": "#3D9B57",
                    "森蕈": "#9A6B45",
                    "雪山": "#78B7E8",
                    "方山": "#C58A43",
                    "火山": "#D85A3A",
                    "熔炉": "#E17935",
                    "城塞": "#857B9E",
                    "雾沼": "#806BC2",
                    "顶峰": "#A6D5F2",
                }
                if icon is None:
                    badge_color = badge_colors.get(base_name, "#607D8B")
                    draw.ellipse(
                        (115, y + 15, 190, y + 90),
                        fill=badge_color,
                        outline="#F7C873",
                        width=3,
                    )
                    badge_width = draw.textbbox((0, 0), base_name[0], font=badge_font)[
                        2
                    ]
                    draw.text(
                        (152 - badge_width / 2, y + 31),
                        base_name[0],
                        fill="#FFFFFF",
                        font=badge_font,
                    )

                draw.text((220, y + 18), stage, fill="#FFFFFF", font=stage_font)
                draw.text(
                    (220, y + 62),
                    self._stage_description(stage),
                    fill="#B8C7D9",
                    font=date_font,
                )

            output = tempfile.NamedTemporaryFile(
                prefix="astrbot_peak_",
                suffix=".png",
                delete=False,
            )
            output.close()
            canvas.save(output.name, format="PNG")
            return output.name
        except Exception as exc:
            logger.warning(f"生成 PEAK 地图汇总图片失败：{exc}")
            return None

    def _extract_route_data(self, html: str) -> tuple[Optional[str], List[str]]:
        soup = BeautifulSoup(html, "html.parser")
        text = self._clean_text(soup.get_text("\n", strip=True))

        if not text:
            raise PeakFetchError("PEAK 页面没有返回有效内容。")

        date = self._extract_map_date(text)
        route = self._extract_route(text)
        if not route:
            raise PeakFetchError(
                "已经成功访问 PEAK 网站，但没有识别出今日地图路线。"
                "可能是网站页面结构发生变化。"
            )

        return date, self._extract_route_stages(route)

    def _parse(self, html: str) -> str:
        date, stages = self._extract_route_data(html)

        result: List[str] = [
            "🏔️ PEAK 今日地图",
            "",
        ]

        if date:
            result.append(f"📅 {date}")

        result.extend(
            [
                "",
                f"🗺️ {' -> '.join(stages)}",
            ]
        )

        return "\n".join(result)

    @filter.command("peak")
    async def peak(self, event: AstrMessageEvent):
        """获取 PEAK 今日地图类型和变体名称。"""

        try:
            message = getattr(event, "message_str", "") or ""
            arguments = message.strip().lower().split()
            if any(
                argument in ("变体", "总表", "地图表", "variants", "variant")
                for argument in arguments
            ):
                yield event.plain_result(self._format_variant_table())
                return

            html = await self._fetch_page()
            result = self._parse(html)
            date, stages = self._extract_route_data(html)
            image_path = await self._create_route_image(html, date, stages)
            yield event.plain_result(result)

            if image_path:
                if hasattr(event, "track_temporary_local_file"):
                    event.track_temporary_local_file(image_path)
                yield event.image_result(image_path)

        except PeakFetchError as exc:
            logger.warning(f"PEAK 插件获取数据失败：{exc}")
            yield event.plain_result(f"❌ 获取 PEAK 今日地图失败\n\n{exc}")

        except Exception:
            logger.exception("PEAK 插件发生未预期错误")
            yield event.plain_result(
                "❌ 获取 PEAK 今日地图时发生未知错误，请查看 AstrBot 日志。"
            )

    async def terminate(self):
        logger.info("PEAK 插件已停止。")
