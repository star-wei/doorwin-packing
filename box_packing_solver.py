#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
箱体尺寸匹配推荐工具
根据产品尺寸自动推荐最合适的箱型
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from itertools import permutations
import json


@dataclass
class Box:
    """箱型数据结构"""
    box_id: str           # 箱号，如 C1
    brand: str            # 品牌/类别
    length: float         # 长 (mm)
    width: float          # 宽 (mm)
    height: float         # 高 (mm)
    volume: float         # 体积 (m³)
    net_weight: float     # 净重 (kg)
    gross_weight: float   # 毛重 (kg)
    remark: str = ""      # 备注

    @property
    def dimensions(self) -> Tuple[float, float, float]:
        """返回箱子三边尺寸（已排序）"""
        return tuple(sorted((self.length, self.width, self.height)))

    @property
    def volume_mm3(self) -> float:
        """返回箱子体积（mm³）"""
        return self.length * self.width * self.height


@dataclass
class Product:
    """产品数据结构"""
    name: str
    length: float         # 长 (mm)
    width: float          # 宽 (mm)
    height: float         # 高 (mm)
    weight: float = 0.0   # 产品重量 (kg)

    @property
    def dimensions(self) -> Tuple[float, float, float]:
        """返回产品三边尺寸（已排序）"""
        return tuple(sorted((self.length, self.width, self.height)))

    @property
    def volume_mm3(self) -> float:
        """返回产品体积（mm³）"""
        return self.length * self.width * self.height


@dataclass
class MatchResult:
    """匹配结果数据结构"""
    box: Box
    product: Product
    fits: bool                    # 是否能装下
    rotation: Tuple[float, float, float]  # 产品旋转后的尺寸
    volume_utilization: float     # 体积利用率 (%)
    leftover_space: float         # 剩余空间 (mm³)
    weight_ok: bool               # 重量是否满足
    score: float                  # 综合评分（越高越好）
    margin_mm: Tuple[float, float, float]  # 各边余量 (mm)


# ============================================
# 箱型数据库（从图片提取）
# ============================================
BOX_DATABASE: List[Box] = [
    Box("C1",  "极筑",   2600, 500,  1230, 1.60, 365,  430,  ""),
    Box("C2",  "极筑",   5350, 450,  450,  1.08, 45,   110,  ""),
    Box("C3",  "绿盾",   3160, 980,  1740, 5.39, 858,  993,  ""),
    Box("C4",  "绿盾",   2910, 780,  2150, 4.88, 950,  1072, ""),
    Box("C5",  "绿盾",   3000, 800,  2150, 5.16, 1003, 1132, ""),
    Box("C6",  "车库门", 3760, 580,  790,  1.72, 265,  299,  "钢质门"),
    Box("C7",  "车库门", 3760, 580,  790,  1.72, 265,  299,  "钢质门"),
    Box("C8",  "车库门", 4060, 580,  790,  1.86, 295,  332,  "钢质门"),
    Box("C9",  "车库门", 4260, 860,  800,  2.93, 552,  611,  ""),
    Box("C10", "车库门", 3160, 630,  760,  1.51, 230,  260,  ""),
    Box("C11", "车库门", 4560, 630,  830,  2.38, 373,  421,  ""),
    Box("C12", "车库门", 5580, 630,  760,  2.67, 421,  474,  ""),
    Box("C13", "折叠门", 3760, 630,  790,  1.87, 304,  341,  ""),
    Box("C14", "折叠门", 3760, 630,  790,  1.87, 304,  341,  ""),
    Box("C15", "折叠门", 2885, 680,  1390, 2.73, 510,  590,  ""),
    Box("C16", "折叠门", 5070, 245,  295,  0.37, 31,   63,   ""),
    Box("C17", "折叠门", 2590, 900,  1360, 3.17, 903,  982,  ""),
    Box("C18", "凯研",   3660, 760,  1540, 4.28, 1121, 1228, ""),
    Box("C19", "凯研",   3210, 900,  1430, 4.13, 1038, 1142, ""),
    Box("C20", "凯研",   3210, 760,  1430, 3.49, 893,  980,  ""),
    Box("C21", "凯研",   2600, 900,  1200, 2.81, 647,  717,  ""),
    Box("C22", "凯研",   2600, 900,  1050, 2.46, 662,  723,  ""),
    Box("C23", "凯研",   3290, 760,  1200, 3.00, 697,  772,  ""),
    Box("C24", "凯研",   3380, 680,  1680, 3.86, 1058, 1155, ""),
    Box("C25", "凯研",   3070, 800,  1520, 3.73, 1002, 1096, ""),
    Box("C26", "凯研",   5530, 620,  1330, 4.56, 989,  1103, ""),
    Box("C27", "凯研",   4980, 560,  1120, 3.12, 424,  502,  ""),
    Box("C28", "凯研",   2265, 610,  1435, 1.98, 866,  916,  "钢化玻璃"),
    Box("C29", "凯研",   2530, 550,  1460, 2.03, 617,  667,  "钢化玻璃"),
    Box("C30", "凯撒",   4300, 1650, 2480, 7.60, 920,  950,  "斜撑铁架"),
]


# ============================================
# 核心匹配算法
# ============================================

def can_fit(product_dims: Tuple[float, ...],
            box_dims: Tuple[float, ...],
            padding_mm: float = 0.0) -> Optional[Tuple[float, float, float]]:
    """
    判断产品（可旋转）是否能放入箱子，考虑各边余量 padding_mm。
    返回能放入时的旋转后尺寸，否则返回 None。
    """
    # 产品各边加上余量后，尝试所有 6 种旋转
    for perm in permutations(product_dims):
        padded = (perm[0] + padding_mm, perm[1] + padding_mm, perm[2] + padding_mm)
        if all(p <= b for p, b in zip(padded, box_dims)):
            return perm
    return None


def evaluate_match(box: Box,
                   product: Product,
                   padding_mm: float = 20.0,
                   min_margin_per_side: float = 10.0,
                   weight_safety_factor: float = 0.9) -> MatchResult:
    """
    评估某个箱型对某个产品的匹配度，返回 MatchResult。

    参数:
        padding_mm: 整体防震/填充余量 (mm)，默认 20mm
        min_margin_per_side: 每边最小余量 (mm)，默认 10mm
        weight_safety_factor: 重量安全系数，产品重量不得超过 净重 * 该系数
    """
    box_dims = box.dimensions
    prod_dims = product.dimensions

    # 1. 能否装下（考虑整体 padding）
    rotation = can_fit(prod_dims, box_dims, padding_mm)
    fits = rotation is not None

    # 2. 计算各边余量
    if fits:
        margins = tuple(b - (r + padding_mm) for b, r in zip(box_dims, rotation))
        # 重新按原始箱子维度对齐（box_dims 已排序，rotation 也已排序）
        margin_mm = margins
    else:
        margin_mm = (float('-inf'),) * 3

    # 3. 体积利用率
    if fits:
        leftover = box.volume_mm3 - product.volume_mm3
        utilization = (product.volume_mm3 / box.volume_mm3) * 100.0
    else:
        leftover = float('inf')
        utilization = 0.0

    # 4. 重量检查（产品重量 vs 箱子净重 * 安全系数）
    weight_limit = box.net_weight * weight_safety_factor
    weight_ok = product.weight <= weight_limit

    # 5. 综合评分
    #    - 体积利用率越高越好（但不超过 95%，避免太挤）
    #    - 箱子越小越好（优先选体积小的箱子）
    #    - 余量越均匀越好
    #    - 重量必须满足
    score = 0.0
    if fits and weight_ok:
        # 体积利用率得分（理想 70%-95%）
        util_score = 100.0 - abs(utilization - 80.0)

        # 箱子体积惩罚（避免选过大的箱子）
        volume_penalty = box.volume_mm3 / 1e9  # 归一化

        # 余量均匀度得分（标准差越小越好）
        if all(m >= 0 for m in margin_mm):
            avg_margin = sum(margin_mm) / 3.0
            variance = sum((m - avg_margin) ** 2 for m in margin_mm) / 3.0
            uniformity_score = max(0, 100.0 - variance / 100.0)
        else:
            uniformity_score = 0.0

        # 最小边距惩罚
        min_margin_penalty = 0.0
        if any(m < min_margin_per_side for m in margin_mm):
            min_margin_penalty = 50.0

        score = util_score - volume_penalty * 5.0 + uniformity_score * 0.3 - min_margin_penalty

    return MatchResult(
        box=box,
        product=product,
        fits=fits,
        rotation=rotation if rotation else (0.0, 0.0, 0.0),
        volume_utilization=utilization,
        leftover_space=leftover,
        weight_ok=weight_ok,
        score=score,
        margin_mm=margin_mm if fits else (0.0, 0.0, 0.0),
    )


def recommend_box(product: Product,
                  box_list: List[Box] = None,
                  top_k: int = 3,
                  padding_mm: float = 20.0,
                  min_margin_per_side: float = 10.0,
                  weight_safety_factor: float = 0.9,
                  preferred_brands: List[str] = None) -> List[MatchResult]:
    """
    为单个产品推荐最合适的箱型，返回 top_k 个结果。

    参数:
        product: 产品对象
        box_list: 可选自定义箱型列表，默认使用 BOX_DATABASE
        top_k: 返回前几名推荐
        padding_mm: 整体防震余量
        min_margin_per_side: 每边最小余量
        weight_safety_factor: 重量安全系数
        preferred_brands: 优先推荐的品牌/类别列表（可选）
    """
    if box_list is None:
        box_list = BOX_DATABASE

    results: List[MatchResult] = []
    for box in box_list:
        result = evaluate_match(
            box, product,
            padding_mm=padding_mm,
            min_margin_per_side=min_margin_per_side,
            weight_safety_factor=weight_safety_factor,
        )
        # 品牌偏好加分
        if preferred_brands and result.box.brand in preferred_brands:
            result.score += 20.0
        results.append(result)

    # 排序：先按是否装下 & 重量OK，再按综合评分降序
    results.sort(key=lambda r: (r.fits and r.weight_ok, r.score), reverse=True)

    # 只返回能装下的
    valid_results = [r for r in results if r.fits and r.weight_ok]
    return valid_results[:top_k]


def batch_recommend(products: List[Product],
                    box_list: List[Box] = None,
                    **kwargs) -> Dict[str, List[MatchResult]]:
    """
    批量为多个产品推荐箱型。
    返回 {产品名称: [MatchResult, ...]} 的字典。
    """
    if box_list is None:
        box_list = BOX_DATABASE

    return {
        prod.name: recommend_box(prod, box_list=box_list, **kwargs)
        for prod in products
    }


def analyze_packing_plan(products: List[Product],
                         box_list: List[Box] = None,
                         padding_mm: float = 20.0,
                         weight_safety_factor: float = 0.9) -> Dict:
    """
    分析一组产品的整体装箱方案，返回结构化报告。
    适用于一个订单包含多个组件/分拆件的场景。
    """
    if box_list is None:
        box_list = BOX_DATABASE

    plan = {
        "products": [],
        "total_boxes_needed": 0,
        "box_summary": {},
        "unfit_products": [],
    }

    for prod in products:
        results = recommend_box(
            prod, box_list=box_list, top_k=1,
            padding_mm=padding_mm,
            weight_safety_factor=weight_safety_factor,
        )
        if results:
            best = results[0]
            plan["products"].append({
                "name": prod.name,
                "dimensions": prod.dimensions,
                "weight": prod.weight,
                "recommended_box": best.box.box_id,
                "brand": best.box.brand,
                "volume_utilization": round(best.volume_utilization, 2),
                "score": round(best.score, 2),
            })
            plan["total_boxes_needed"] += 1
            key = f"{best.box.box_id}({best.box.brand})"
            plan["box_summary"][key] = plan["box_summary"].get(key, 0) + 1
        else:
            plan["unfit_products"].append({
                "name": prod.name,
                "dimensions": prod.dimensions,
                "weight": prod.weight,
                "reason": "无匹配箱型（尺寸或重量超出所有箱型范围）",
            })

    return plan


# ============================================
# 辅助函数：输出格式化
# ============================================

def format_result(result: MatchResult, rank: int = 1) -> str:
    """将匹配结果格式化为可读字符串"""
    lines = [
        f"  [{rank}] 箱号: {result.box.box_id} | 品牌: {result.box.brand} | 备注: {result.box.remark or '无'}",
        f"      箱子尺寸: {result.box.length}×{result.box.width}×{result.box.height} mm",
        f"      产品旋转后: {result.rotation[0]:.0f}×{result.rotation[1]:.0f}×{result.rotation[2]:.0f} mm",
        f"      体积利用率: {result.volume_utilization:.1f}% | 剩余空间: {result.leftover_space:,.0f} mm³",
        f"      各边余量: {result.margin_mm[0]:.0f}, {result.margin_mm[1]:.0f}, {result.margin_mm[2]:.0f} mm",
        f"      重量限制: {result.box.net_weight:.0f} kg (净重) | 产品重量: {result.product.weight:.0f} kg | 合格: {'✅' if result.weight_ok else '❌'}",
        f"      综合评分: {result.score:.2f}",
    ]
    return "\n".join(lines)


def print_recommendation(product: Product, results: List[MatchResult]):
    """打印单个产品的推荐结果"""
    print(f"\n{'='*60}")
    print(f"产品: {product.name} | 尺寸: {product.length}×{product.width}×{product.height} mm | 重量: {product.weight} kg")
    print(f"{'='*60}")
    if not results:
        print("  ⚠️  没有找到合适的箱型！")
        return
    for i, r in enumerate(results, 1):
        print(format_result(r, i))


# ============================================
# 4591x3067 门窗产品组件定义（从产品图提取）
# ============================================

WINDOW_4591X3067_COMPONENTS: List[Product] = [
    # 整扇门窗（不可直接装箱，作为参考）
    Product("整扇门窗(参考)", 4572, 3048, 150, weight=800),

    # 单个窗扇 P1-P4（估算含边框厚度）
    Product("窗扇-P1", 1100, 100, 2400, weight=120),
    Product("窗扇-P2", 1100, 100, 2400, weight=120),
    Product("窗扇-P3", 1100, 100, 2400, weight=120),
    Product("窗扇-P4", 1100, 100, 2400, weight=120),

    # 下部横梁/门槛组件（整体太长，可能需拆分）
    Product("下部横梁-整体", 4572, 610, 100, weight=180),
    Product("下部横梁-左半", 2286, 610, 100, weight=90),
    Product("下部横梁-右半", 2286, 610, 100, weight=90),

    # 竖框/中梃型材（长条形）
    Product("竖框型材-左侧", 3048, 80, 60, weight=45),
    Product("竖框型材-右侧", 3048, 80, 60, weight=45),
    Product("中梃型材-1", 3048, 60, 60, weight=35),
    Product("中梃型材-2", 3048, 60, 60, weight=35),
    Product("中梃型材-3", 3048, 60, 60, weight=35),
]


# ============================================
# 示例运行
# ============================================

if __name__ == "__main__":
    # 示例产品
    sample_products = [
        Product("铝合金门-1", 2500, 450, 1150, weight=300),
        Product("钢化玻璃门", 2200, 580, 1380, weight=800),
        Product("大型折叠门", 5000, 220, 280,  weight=50),
        Product("车库门组件", 3600, 550, 750,  weight=250),
        Product("超大组件",   4200, 1600, 2400, weight=900),
    ]

    print("=" * 60)
    print("🚀 箱体尺寸智能匹配推荐系统")
    print("=" * 60)

    for prod in sample_products:
        top_boxes = recommend_box(prod, top_k=3)
        print_recommendation(prod, top_boxes)

    # 批量推荐示例
    print("\n" + "=" * 60)
    print("📦 批量推荐结果（JSON 格式）")
    print("=" * 60)
    batch = batch_recommend(sample_products, top_k=1)
    summary = {}
    for name, results in batch.items():
        if results:
            best = results[0]
            summary[name] = {
                "推荐箱号": best.box.box_id,
                "品牌": best.box.brand,
                "体积利用率": round(best.volume_utilization, 2),
                "评分": round(best.score, 2),
            }
        else:
            summary[name] = {"推荐箱号": None, "原因": "无匹配箱型"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # ============================================
    # 4591x3067 门窗产品装箱方案分析
    # ============================================
    print("\n" + "=" * 70)
    print("🏠 4591×3067 门窗产品 — 分拆装箱方案分析")
    print("=" * 70)

    # 对门窗组件做整体装箱方案分析
    window_plan = analyze_packing_plan(
        WINDOW_4591X3067_COMPONENTS,
        padding_mm=20.0,
        weight_safety_factor=0.9,
    )

    for item in window_plan["products"]:
        dims = item["dimensions"]
        print(f"\n📐 {item['name']}")
        print(f"   尺寸: {dims[0]:.0f}×{dims[1]:.0f}×{dims[2]:.0f} mm | 重量: {item['weight']:.0f} kg")
        if item.get("recommended_box"):
            print(f"   ✅ 推荐箱型: {item['recommended_box']} ({item['brand']}) | 利用率: {item['volume_utilization']}% | 评分: {item['score']}")
        else:
            print(f"   ❌ 无合适箱型")

    if window_plan["unfit_products"]:
        print("\n⚠️ 无法直接装箱的组件:")
        for u in window_plan["unfit_products"]:
            dims = u["dimensions"]
            print(f"   - {u['name']}: {dims[0]:.0f}×{dims[1]:.0f}×{dims[2]:.0f} mm | {u['reason']}")

    print("\n📊 箱型使用汇总:")
    for box_key, count in window_plan["box_summary"].items():
        print(f"   - {box_key}: {count} 件")
    print(f"\n📦 预计总箱数: {window_plan['total_boxes_needed']} 箱")
    print(f"📦 无法装箱组件数: {len(window_plan['unfit_products'])} 件")
