# coding=utf-8
"""
High school geography weekly candidate report.

This module intentionally uses only the Python standard library so it can run
after a crawler job even when optional AI dependencies are unavailable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class CurriculumRule:
    name: str
    priority: str
    module: str
    terms: tuple[str, ...]


@dataclass
class SourceEvidence:
    platform_id: str
    platform_name: str
    best_rank: int
    first_time: str
    last_time: str
    crawl_count: int
    url: str = ""
    mobile_url: str = ""


@dataclass
class TopicCandidate:
    title: str
    category: CurriculumRule
    matched_terms: list[str]
    sources: dict[str, SourceEvidence] = field(default_factory=dict)
    first_date: str = ""
    last_date: str = ""
    score: float = 0.0
    is_international: bool = False

    @property
    def best_rank(self) -> int:
        ranks = [source.best_rank for source in self.sources.values() if source.best_rank > 0]
        return min(ranks) if ranks else 999

    @property
    def total_crawl_count(self) -> int:
        return sum(max(0, source.crawl_count) for source in self.sources.values())

    @property
    def platform_names(self) -> list[str]:
        names = [source.platform_name or source.platform_id for source in self.sources.values()]
        return sorted(set(names))

    @property
    def urls(self) -> list[str]:
        seen = set()
        urls = []
        for source in self.sources.values():
            for raw_url in (source.url, source.mobile_url):
                if raw_url and raw_url not in seen:
                    seen.add(raw_url)
                    urls.append(raw_url)
        return urls


@dataclass(frozen=True)
class AuthorityReference:
    title: str
    url: str
    reason: str


@dataclass(frozen=True)
class CurriculumReference:
    title: str
    path: str
    available: bool
    sha256: str = ""
    note: str = ""


CURRICULUM_RULES: tuple[CurriculumRule, ...] = (
    CurriculumRule(
        name="P1-必修地理1-自然环境与实践",
        priority="P1",
        module="必修 地理1",
        terms=(
            "暴雨", "强降雨", "洪水", "洪涝", "内涝", "台风", "寒潮", "冷空气", "高温",
            "热浪", "气温", "升温", "降温", "融化", "冰雪", "干旱", "沙尘", "沙尘暴", "雷暴", "冰雹", "龙卷风", "山火",
            "森林火灾", "地震", "余震", "滑坡", "泥石流", "崩塌", "海啸", "气象",
            "预警", "河流", "湖泊", "水库", "流域", "冰川", "冻土", "水循环",
            "喀斯特", "丹霞", "雅丹", "沙漠", "戈壁", "湿地", "红树林", "土壤",
            "植被", "生物多样性", "自然保护区", "国家公园", "生态保护",
        ),
    ),
    CurriculumRule(
        name="P1-必修地理2-人口城市产业",
        priority="P1",
        module="必修 地理2",
        terms=(
            "人口", "出生率", "老龄化", "迁徙", "流动人口", "春运", "返乡", "城镇化",
            "城市更新", "新区", "都市圈", "城市群", "地铁", "高铁", "机场", "港口",
            "航运", "物流", "农业", "粮食", "耕地", "种植", "养殖", "乡村振兴",
            "产业转移", "产业带", "制造业", "服务业", "文旅", "旅游", "景区",
        ),
    ),
    CurriculumRule(
        name="P2-选择性必修1-自然地理基础",
        priority="P2",
        module="选择性必修1 自然地理基础",
        terms=(
            "大气环流", "季风", "锋面", "气旋", "反气旋", "厄尔尼诺", "拉尼娜",
            "气候变化", "水文", "径流", "补给", "地质", "地貌", "板块", "断裂",
            "褶皱", "侵蚀", "沉积", "自然带", "垂直地带性", "地方性分异",
        ),
    ),
    CurriculumRule(
        name="P2-选择性必修2-区域发展",
        priority="P2",
        module="选择性必修2 区域发展",
        terms=(
            "京津冀", "长三角", "珠三角", "粤港澳", "大湾区", "成渝", "长江经济带",
            "黄河流域", "东北振兴", "西部开发", "中部崛起", "海南自贸港", "雄安",
            "边疆", "西藏", "新疆", "内蒙古", "青藏高原", "黄土高原", "云贵高原",
            "四川盆地", "塔里木", "准噶尔", "区域协同", "区域协调",
        ),
    ),
    CurriculumRule(
        name="P2-选择性必修3-资源环境与国家安全",
        priority="P2",
        module="选择性必修3 资源、环境与国家安全",
        terms=(
            "碳达峰", "碳中和", "双碳", "新能源", "风电", "光伏", "水电", "核电",
            "储能", "电力保供", "煤炭", "石油", "天然气", "矿产", "稀土", "水资源",
            "南水北调", "海水淡化", "生态修复", "污染治理", "空气质量", "水质",
            "土壤污染", "垃圾分类", "粮食安全", "耕地保护", "海洋权益",
        ),
    ),
    CurriculumRule(
        name="P3-选修与地理技术",
        priority="P3",
        module="选修模块",
        terms=(
            "遥感", "卫星", "北斗", "GIS", "地理信息", "地图", "测绘", "导航",
            "无人机巡检", "海洋牧场", "潮汐", "海冰", "极地", "天文", "日食",
            "月食", "流星雨", "城乡规划", "国土空间规划", "研学旅行",
        ),
    ),
)

PRIORITY_SCORE = {"P1": 3000, "P2": 2000, "P3": 1000}
CHINA_HINTS = (
    "中国", "我国", "国内", "北京", "上海", "天津", "重庆", "河北", "山西", "辽宁", "吉林",
    "黑龙江", "江苏", "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东",
    "海南", "四川", "贵州", "云南", "陕西", "甘肃", "青海", "台湾", "内蒙古", "广西", "西藏",
    "宁夏", "新疆", "香港", "澳门", "长江", "黄河", "珠江",
)
INTERNATIONAL_HINTS = (
    "美国", "日本", "韩国", "朝鲜", "俄罗斯", "印度", "英国", "法国", "德国", "欧洲", "非洲",
    "南美", "北美", "东南亚", "澳大利亚", "加拿大", "巴西", "印尼", "越南", "泰国", "菲律宾",
)
DISQUALIFY_HINTS = (
    "票房", "口碑", "电影", "电视剧", "综艺", "演唱会", "端游", "手游", "游戏", "赛季",
    "地图上线", "皮肤", "角色", "抽卡", "直播间", "带货", "猪肉", "食道", "内脏",
    "好哭", "树洞", "心智", "生命的河流", "指示牌",
)
DEFAULT_CURRICULUM_PDF = r"D:\BaiduNetdiskDownload\普通高中地理课程标准（2017年版2020年修订).pdf"

AUTHORITY_REFERENCE_RULES: tuple[tuple[tuple[str, ...], tuple[AuthorityReference, ...]], ...] = (
    (
        ("地震", "余震", "震级"),
        (
            AuthorityReference("中国地震台网", "https://news.ceic.ac.cn/", "核验地震时间、震级、震中和震源深度"),
            AuthorityReference("中国地震局", "https://www.cea.gov.cn/", "查询防震减灾与地震科普资料"),
        ),
    ),
    (
        ("暴雨", "强降雨", "洪水", "洪涝", "内涝", "台风", "寒潮", "冷空气", "高温", "热浪", "气温", "升温", "降温", "冰雪", "融化", "沙尘", "沙尘暴", "气象"),
        (
            AuthorityReference("中国气象局", "https://www.cma.gov.cn/", "核验天气气候事实、预警和气象科普"),
            AuthorityReference("中央气象台", "https://www.nmc.cn/", "核验实时天气过程、预警和天气图资料"),
        ),
    ),
    (
        ("滑坡", "泥石流", "崩塌", "地质", "地貌", "灾害预警"),
        (
            AuthorityReference("自然资源部", "https://www.mnr.gov.cn/", "核验地质灾害、国土空间与自然资源信息"),
            AuthorityReference("应急管理部", "https://www.mem.gov.cn/", "核验灾害应急、防灾减灾和事故通报"),
        ),
    ),
    (
        ("河流", "湖泊", "水库", "流域", "水资源", "南水北调", "防汛", "抗旱", "灌溉"),
        (
            AuthorityReference("水利部", "http://www.mwr.gov.cn/", "核验水情、流域治理、防汛抗旱和水资源数据"),
        ),
    ),
    (
        ("高铁", "铁路"),
        (
            AuthorityReference("国家铁路局", "https://www.nra.gov.cn/", "核验铁路行业政策、规划和监管信息"),
            AuthorityReference("中国国家铁路集团", "https://www.china-railway.com.cn/", "核验铁路运营、里程和运输数据"),
        ),
    ),
    (
        ("地铁", "交通", "机场", "港口", "航运", "物流"),
        (
            AuthorityReference("交通运输部", "https://www.mot.gov.cn/", "核验综合交通、港口航运和运输政策数据"),
            AuthorityReference("中国民用航空局", "https://www.caac.gov.cn/", "核验机场、航线和民航运行信息"),
        ),
    ),
    (
        ("农业", "粮食", "耕地", "种植", "养殖", "乡村振兴", "灌溉"),
        (
            AuthorityReference("农业农村部", "http://www.moa.gov.cn/", "核验农业生产、粮食安全和乡村振兴信息"),
            AuthorityReference("国家统计局", "https://www.stats.gov.cn/", "核验农业、人口、区域经济等统计数据"),
        ),
    ),
    (
        ("人口", "出生率", "老龄化", "流动人口", "城镇化"),
        (
            AuthorityReference("国家统计局", "https://www.stats.gov.cn/", "核验人口、城镇化和区域统计数据"),
        ),
    ),
    (
        ("文旅", "旅游", "景区", "研学旅行"),
        (
            AuthorityReference("文化和旅游部", "https://www.mct.gov.cn/", "核验文旅政策、市场数据和景区管理信息"),
        ),
    ),
    (
        ("生态", "湿地", "红树林", "生物多样性", "自然保护区", "国家公园", "污染治理", "空气质量", "水质", "土壤污染", "碳达峰", "碳中和", "双碳"),
        (
            AuthorityReference("生态环境部", "https://www.mee.gov.cn/", "核验生态环境质量、污染治理和双碳政策信息"),
            AuthorityReference("国家林业和草原局", "https://www.forestry.gov.cn/", "核验自然保护地、湿地和国家公园信息"),
        ),
    ),
    (
        ("新能源", "风电", "光伏", "水电", "核电", "储能", "电力保供", "煤炭", "石油", "天然气"),
        (
            AuthorityReference("国家能源局", "https://www.nea.gov.cn/", "核验能源供需、新能源和电力运行信息"),
        ),
    ),
    (
        ("遥感", "卫星", "北斗", "GIS", "地理信息", "地图", "测绘"),
        (
            AuthorityReference("自然资源部", "https://www.mnr.gov.cn/", "核验测绘地理信息、遥感和国土空间资料"),
            AuthorityReference("北斗卫星导航系统", "http://www.beidou.gov.cn/", "核验北斗导航系统官方资料"),
        ),
    ),
)


def normalize_title(title: str) -> str:
    title = re.sub(r"\s+", "", title or "")
    title = re.sub(r"[#【】\[\]（）()]+", "", title)
    return title.lower()


def parse_db_date(path: Path) -> date | None:
    stem = path.stem
    if not DATE_PATTERN.match(stem):
        return None
    try:
        return date.fromisoformat(stem)
    except ValueError:
        return None


def available_dates(output_dir: Path) -> list[date]:
    news_dir = output_dir / "news"
    if not news_dir.exists():
        return []
    dates = [parsed for parsed in (parse_db_date(path) for path in news_dir.glob("*.db")) if parsed]
    return sorted(dates)


def resolve_end_date(raw_end_date: str | None, output_dir: Path) -> date:
    if raw_end_date == "latest":
        dates = available_dates(output_dir)
        if not dates:
            raise SystemExit(f"No news databases found under {output_dir / 'news'}")
        return dates[-1]
    if raw_end_date:
        return date.fromisoformat(raw_end_date)
    return date.today()


def iter_db_paths(output_dir: Path, start_date: date, end_date: date) -> Iterable[tuple[date, Path]]:
    news_dir = output_dir / "news"
    if not news_dir.exists():
        return
    for db_path in sorted(news_dir.glob("*.db")):
        db_date = parse_db_date(db_path)
        if db_date and start_date <= db_date <= end_date:
            yield db_date, db_path


def iter_rss_db_paths(output_dir: Path, start_date: date, end_date: date) -> Iterable[tuple[date, Path]]:
    rss_dir = output_dir / "rss"
    if not rss_dir.exists():
        return
    for db_path in sorted(rss_dir.glob("*.db")):
        db_date = parse_db_date(db_path)
        if db_date and start_date <= db_date <= end_date:
            yield db_date, db_path


def classify_title(title: str) -> tuple[CurriculumRule | None, list[str]]:
    normalized = normalize_title(title)
    if any(hint.lower() in normalized for hint in DISQUALIFY_HINTS):
        return None, []

    best_rule = None
    best_terms: list[str] = []

    for rule in CURRICULUM_RULES:
        matched = [term for term in rule.terms if term.lower() in normalized]
        if not matched:
            continue
        if best_rule is None:
            best_rule = rule
            best_terms = matched
            continue
        current_key = (PRIORITY_SCORE[rule.priority], len(matched))
        best_key = (PRIORITY_SCORE[best_rule.priority], len(best_terms))
        if current_key > best_key:
            best_rule = rule
            best_terms = matched

    return best_rule, best_terms


def is_international_topic(title: str) -> bool:
    normalized = normalize_title(title)
    has_foreign_hint = any(hint.lower() in normalized for hint in INTERNATIONAL_HINTS)
    has_china_hint = any(hint.lower() in normalized for hint in CHINA_HINTS)
    return has_foreign_hint and not has_china_hint


def calculate_score(candidate: TopicCandidate) -> float:
    best_rank_score = max(0, 120 - candidate.best_rank)
    platform_score = min(6, len(candidate.sources)) * 90
    persistence_score = min(120, candidate.total_crawl_count * 3)
    match_score = min(8, len(candidate.matched_terms)) * 45
    china_bonus = 200 if not candidate.is_international else -250
    return (
        PRIORITY_SCORE[candidate.category.priority]
        + best_rank_score
        + platform_score
        + persistence_score
        + match_score
        + china_bonus
    )


def resolve_curriculum_reference(raw_path: str | None = None) -> CurriculumReference:
    configured_path = (
        raw_path
        or os.environ.get("GEOGRAPHY_CURRICULUM_PDF")
        or DEFAULT_CURRICULUM_PDF
    )
    pdf_path = Path(configured_path)
    if not pdf_path.exists():
        return CurriculumReference(
            title="普通高中地理课程标准（2017年版2020年修订）",
            path=str(pdf_path),
            available=False,
            note="未找到课标 PDF，已使用内置课标模块规则进行匹配",
        )

    digest = hashlib.sha256()
    with pdf_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return CurriculumReference(
        title="普通高中地理课程标准（2017年版2020年修订）",
        path=str(pdf_path),
        available=True,
        sha256=digest.hexdigest(),
        note="已定位本地课标 PDF；候选排序使用与该课标一致的模块优先级规则",
    )


def _dedupe_references(refs: list[AuthorityReference]) -> list[AuthorityReference]:
    seen = set()
    deduped = []
    for ref in refs:
        key = (ref.title, ref.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ref)
    return deduped


def get_authority_references(candidate: TopicCandidate) -> list[AuthorityReference]:
    normalized_title = normalize_title(candidate.title)
    matched_refs: list[AuthorityReference] = []

    for terms, refs in AUTHORITY_REFERENCE_RULES:
        if any(term.lower() in normalized_title for term in terms):
            matched_refs.extend(refs)
            continue
        if any(term in candidate.matched_terms for term in terms):
            matched_refs.extend(refs)

    if not matched_refs:
        if candidate.category.priority == "P1" and "地理2" in candidate.category.module:
            matched_refs.append(
                AuthorityReference("国家统计局", "https://www.stats.gov.cn/", "核验人口、产业、区域发展等基础数据")
            )
        elif candidate.category.priority == "P1":
            matched_refs.append(
                AuthorityReference("中国气象局", "https://www.cma.gov.cn/", "核验自然地理与天气气候背景资料")
            )
        else:
            matched_refs.append(
                AuthorityReference("自然资源部", "https://www.mnr.gov.cn/", "核验区域、资源与地理信息资料")
            )

    return _dedupe_references(matched_refs)[:3]


def serialize_reference(ref: AuthorityReference) -> dict:
    return {
        "title": ref.title,
        "url": ref.url,
        "reason": ref.reason,
    }


def serialize_curriculum_reference(ref: CurriculumReference) -> dict:
    return {
        "title": ref.title,
        "path": ref.path,
        "available": ref.available,
        "sha256": ref.sha256,
        "note": ref.note,
    }


def load_candidates(output_dir: Path, start_date: date, end_date: date) -> list[TopicCandidate]:
    candidates: dict[str, TopicCandidate] = {}

    query = """
        SELECT
            n.title,
            n.platform_id,
            COALESCE(p.name, n.platform_id) AS platform_name,
            n.rank,
            n.url,
            n.mobile_url,
            n.first_crawl_time,
            n.last_crawl_time,
            n.crawl_count
        FROM news_items n
        LEFT JOIN platforms p ON p.id = n.platform_id
        WHERE n.title IS NOT NULL AND TRIM(n.title) != ''
    """

    for db_date, db_path in iter_db_paths(output_dir, start_date, end_date):
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query).fetchall()
        except sqlite3.Error as exc:
            print(f"[geography-weekly] Skip unreadable database {db_path}: {exc}")
            continue
        finally:
            try:
                conn.close()
            except Exception:
                pass

        for row in rows:
            title = str(row["title"]).strip()
            rule, matched_terms = classify_title(title)
            if not rule:
                continue

            key = normalize_title(title)
            candidate = candidates.get(key)
            if not candidate:
                candidate = TopicCandidate(
                    title=title,
                    category=rule,
                    matched_terms=matched_terms,
                    first_date=db_date.isoformat(),
                    last_date=db_date.isoformat(),
                    is_international=is_international_topic(title),
                )
                candidates[key] = candidate
            else:
                existing_priority = PRIORITY_SCORE[candidate.category.priority]
                new_priority = PRIORITY_SCORE[rule.priority]
                if (new_priority, len(matched_terms)) > (existing_priority, len(candidate.matched_terms)):
                    candidate.category = rule
                    candidate.matched_terms = matched_terms
                candidate.first_date = min(candidate.first_date, db_date.isoformat())
                candidate.last_date = max(candidate.last_date, db_date.isoformat())

            platform_id = str(row["platform_id"])
            rank = int(row["rank"] or 999)
            existing_source = candidate.sources.get(platform_id)
            if existing_source:
                existing_source.best_rank = min(existing_source.best_rank, rank)
                existing_source.first_time = min(existing_source.first_time, str(row["first_crawl_time"] or ""))
                existing_source.last_time = max(existing_source.last_time, str(row["last_crawl_time"] or ""))
                existing_source.crawl_count += int(row["crawl_count"] or 0)
                if not existing_source.url:
                    existing_source.url = str(row["url"] or "")
                if not existing_source.mobile_url:
                    existing_source.mobile_url = str(row["mobile_url"] or "")
            else:
                candidate.sources[platform_id] = SourceEvidence(
                    platform_id=platform_id,
                    platform_name=str(row["platform_name"] or platform_id),
                    best_rank=rank,
                    first_time=str(row["first_crawl_time"] or ""),
                    last_time=str(row["last_crawl_time"] or ""),
                    crawl_count=int(row["crawl_count"] or 0),
                    url=str(row["url"] or ""),
                    mobile_url=str(row["mobile_url"] or ""),
                )

    for candidate in candidates.values():
        candidate.score = calculate_score(candidate)

    return sorted(candidates.values(), key=lambda item: item.score, reverse=True)


def load_rss_references(output_dir: Path, start_date: date, end_date: date, limit: int = 20) -> list[dict]:
    references: list[dict] = []
    seen_urls = set()
    query = """
        SELECT
            r.title,
            r.url,
            r.published_at,
            r.feed_id,
            COALESCE(f.name, r.feed_id) AS feed_name
        FROM rss_items r
        LEFT JOIN rss_feeds f ON f.id = r.feed_id
        WHERE r.title IS NOT NULL AND TRIM(r.title) != ''
        ORDER BY r.published_at DESC, r.last_crawl_time DESC
        LIMIT ?
    """

    for db_date, db_path in iter_rss_db_paths(output_dir, start_date, end_date):
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, (limit,)).fetchall()
        except sqlite3.Error as exc:
            print(f"[geography-weekly] Skip unreadable RSS database {db_path}: {exc}")
            continue
        finally:
            try:
                conn.close()
            except Exception:
                pass

        for row in rows:
            url = str(row["url"] or "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            references.append(
                {
                    "date": db_date.isoformat(),
                    "title": str(row["title"] or ""),
                    "url": url,
                    "published_at": str(row["published_at"] or ""),
                    "feed_id": str(row["feed_id"] or ""),
                    "feed_name": str(row["feed_name"] or row["feed_id"] or ""),
                }
            )
            if len(references) >= limit:
                return references

    return references


def select_candidates(candidates: list[TopicCandidate], limit: int) -> list[TopicCandidate]:
    selected = []
    international_count = 0

    for candidate in candidates:
        if candidate.is_international:
            if international_count >= 2:
                continue
            international_count += 1
        selected.append(candidate)
        if len(selected) >= limit:
            break

    return selected


def make_entry_angle(candidate: TopicCandidate, has_authority_refs: bool) -> str:
    terms = "、".join(candidate.matched_terms[:4]) or "区域背景、人地关系"
    if candidate.category.priority == "P1":
        classroom = f"可作为课堂导入或基础概念案例，从{terms}切入，连接{candidate.category.module}。"
        creation = "适合写成公众号/知乎科普短文，突出热点背后的地理概念、空间差异或人地关系。"
    elif candidate.category.priority == "P2":
        classroom = f"可作为区域比较、过程分析或综合题素材，从{terms}切入，连接{candidate.category.module}。"
        creation = "适合写成公众号/知乎深度分析，解释成因、过程、影响和区域差异。"
    else:
        classroom = f"可作为拓展阅读或课后探究素材，从{terms}切入，连接{candidate.category.module}。"
        creation = "适合写成地理科普补充或选题线索，不宜直接作为主线论证。"
    boundary = (
        "已给出权威核验入口，成稿前需核对具体事件页面、数据口径和发布时间。"
        if has_authority_refs
        else "需补充政府部门、正规媒体、学术期刊或国际组织等权威信源后再写成完整说明。"
    )
    return f"课堂/备课：{classroom}\n内容创作：{creation}\n核验边界：{boundary}"


def make_evidence(candidate: TopicCandidate) -> str:
    return (
        f"{len(candidate.sources)}个平台；最高排名 {candidate.best_rank}；"
        f"累计抓取 {candidate.total_crawl_count} 次；"
        f"{candidate.first_date} 至 {candidate.last_date}"
    )


def to_report_dict(candidate: TopicCandidate, curriculum_ref: CurriculumReference) -> dict:
    authority_refs = get_authority_references(candidate)
    entry_angle = make_entry_angle(candidate, bool(authority_refs))
    return {
        "topic": candidate.title,
        "platforms": candidate.platform_names,
        "evidence": make_evidence(candidate),
        "curriculum_module": candidate.category.module,
        "priority": candidate.category.priority,
        "matched_terms": candidate.matched_terms,
        "entry_angle": entry_angle,
        "teaching_note": entry_angle,
        "original_urls": candidate.urls,
        "authority_reference_status": "已提供权威核验入口，需复核具体事件页面",
        "authority_references": [serialize_reference(ref) for ref in authority_refs],
        "curriculum_reference": serialize_curriculum_reference(curriculum_ref),
        "is_international": candidate.is_international,
        "score": round(candidate.score, 2),
    }


def markdown_link_list(urls: list[str]) -> str:
    if not urls:
        return "无"
    parts = []
    for idx, url in enumerate(urls[:3], start=1):
        parts.append(f"[链接{idx}]({url})")
    if len(urls) > 3:
        parts.append(f"另 {len(urls) - 3} 个")
    return "；".join(parts)


def markdown_reference_list(refs: list[dict]) -> str:
    if not refs:
        return "需补充"
    return "；".join(
        f"[{escape_table(ref.get('title', '权威信源'))}]({ref.get('url', '')})"
        for ref in refs[:3]
        if ref.get("url")
    ) or "需补充"


def escape_table(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", "<br>")


def render_markdown(
    rows: list[dict],
    rss_references: list[dict],
    start_date: date,
    end_date: date,
    total_candidates: int,
    curriculum_ref: CurriculumReference,
) -> str:
    curriculum_status = (
        f"已读取课标 PDF：{curriculum_ref.path}（SHA256: {curriculum_ref.sha256[:12]}...）"
        if curriculum_ref.available
        else f"未读取到课标 PDF：{curriculum_ref.path}；使用内置课标模块规则"
    )
    lines = [
        f"# 高中地理热点候选周报（{start_date.isoformat()} 至 {end_date.isoformat()}）",
        "",
        f"- 候选池：{total_candidates} 条",
        f"- 入选：{len(rows)} 条",
        f"- 课标依据：{curriculum_status}",
        "- 说明：本报告用于地理热点初筛，可服务于高中地理备课、课堂案例设计、地理科普写作、公众号或知乎选题参考；正式使用前必须打开权威链接核对具体事件页面，不使用百度百科、百家号作为依据。",
        "",
        "| # | 原始话题 | 来源平台 | 热度证据 | 课标模块 | 优先级 | 切入角度 | 原始链接 | 权威引用 | 核验状态 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for idx, row in enumerate(rows, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(idx),
                    escape_table(row["topic"]),
                    escape_table("、".join(row["platforms"])),
                    escape_table(row["evidence"]),
                    escape_table(row["curriculum_module"]),
                    escape_table(row["priority"]),
                    escape_table(row["entry_angle"]),
                    markdown_link_list(row["original_urls"]),
                    markdown_reference_list(row.get("authority_references", [])),
                    escape_table(row["authority_reference_status"]),
                ]
            )
            + " |"
        )

    if rows:
        lines.extend(
            [
                "",
                "## 核验提醒",
                "",
                "以下入选热点已给出权威核验入口；正式成稿前仍需打开对应官网或正规媒体页面，核对事件事实、数据口径和发布时间：",
            ]
        )
        for row in rows:
            lines.append(f"- {row['topic']}：{row['authority_reference_status']}")

    if rss_references:
        lines.extend(["", "## 权威 RSS 参考", ""])
        for item in rss_references[:10]:
            link = f"[原文]({item['url']})" if item.get("url") else "无链接"
            published = f"，发布时间：{item['published_at']}" if item.get("published_at") else ""
            lines.append(f"- {item['feed_name']}：{item['title']}（{link}{published}）")

    return "\n".join(lines) + "\n"


def write_outputs(
    rows: list[dict],
    rss_references: list[dict],
    output_dir: Path,
    start_date: date,
    end_date: date,
    total_candidates: int,
    output_format: str,
    curriculum_ref: CurriculumReference,
) -> list[Path]:
    report_dir = output_dir / "geography"
    report_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{end_date.isoformat()}-weekly-geography"
    written: list[Path] = []

    payload = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_candidates": total_candidates,
        "selected_count": len(rows),
        "curriculum_reference": serialize_curriculum_reference(curriculum_ref),
        "rss_references": rss_references,
        "items": rows,
    }

    if output_format in {"json", "both"}:
        json_path = report_dir / f"{base_name}.json"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(json_path)

    if output_format in {"markdown", "both"}:
        md_path = report_dir / f"{base_name}.md"
        md_path.write_text(
            render_markdown(rows, rss_references, start_date, end_date, total_candidates, curriculum_ref),
            encoding="utf-8",
        )
        written.append(md_path)

    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate high school geography weekly candidate report.")
    parser.add_argument("--output-dir", default="output", help="TrendRadar output directory.")
    parser.add_argument("--days", type=int, default=7, help="Number of days to include.")
    parser.add_argument("--end-date", default=None, help="End date YYYY-MM-DD, or 'latest'. Defaults to today.")
    parser.add_argument("--limit", type=int, default=15, help="Maximum selected topics. International topics are capped at 2.")
    parser.add_argument("--format", choices=("markdown", "json", "both"), default="both", help="Output format.")
    parser.add_argument("--curriculum-pdf", default=None, help="Path to 普通高中地理课程标准 PDF.")
    parser.add_argument("--stdout", action="store_true", help="Also print Markdown report to stdout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_dir = Path(args.output_dir)
    end_date = resolve_end_date(args.end_date, output_dir)
    start_date = end_date - timedelta(days=max(1, args.days) - 1)
    curriculum_ref = resolve_curriculum_reference(args.curriculum_pdf)
    candidates = load_candidates(output_dir, start_date, end_date)
    rss_references = load_rss_references(output_dir, start_date, end_date)
    selected = select_candidates(candidates, max(1, args.limit))
    rows = [to_report_dict(candidate, curriculum_ref) for candidate in selected]
    written = write_outputs(
        rows,
        rss_references,
        output_dir,
        start_date,
        end_date,
        len(candidates),
        args.format,
        curriculum_ref,
    )

    for path in written:
        print(f"[geography-weekly] Wrote {path}")

    if args.stdout:
        print(render_markdown(rows, rss_references, start_date, end_date, len(candidates), curriculum_ref))

    if not rows:
        print("[geography-weekly] No geography candidates found in the selected date range.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
