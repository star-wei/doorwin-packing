#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
箱体尺寸匹配推荐工具 V2
新增：工厂分配、拆件框架、多件同箱(bin-packing)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
from itertools import permutations
import json


# ============================================
# 基础数据结构
# ============================================

@dataclass
class Box:
    """箱型数据结构"""
    box_id: str
    brand: str
    length: float
    width: float
    height: float
    volume: float
    net_weight: float
    gross_weight: float
    remark: str = ""
    factory_id: str = ""  # 所属工厂

    @property
    def dimensions(self) -> Tuple[float, float, float]:
        return tuple(sorted((self.length, self.width, self.height)))

    @property
    def volume_mm3(self) -> float:
        return self.length * self.width * self.height


@dataclass
class Product:
    """产品/组件数据结构"""
    name: str
    length: float
    width: float
    height: float
    weight: float = 0.0
    product_type: str = ""
    brand: str = ""
    window_id: str = ""  # 所属门窗编号

    @property
    def dimensions(self) -> Tuple[float, float, float]:
        return tuple(sorted((self.length, self.width, self.height)))

    @property
    def volume_mm3(self) -> float:
        return self.length * self.width * self.height


@dataclass
class MatchResult:
    """单件匹配结果"""
    box: Box
    product: Product
    fits: bool
    rotation: Tuple[float, float, float]
    volume_utilization: float
    leftover_space: float
    weight_ok: bool
    score: float
    margin_mm: Tuple[float, float, float]


# ============================================
# 箱型数据库（按品牌/工厂分组）
# ============================================

BOX_DATABASE: List[Box] = [
    # 极筑工厂
    Box("C1", "极筑", 2600, 500, 1230, 1.60, 365, 430, "", factory_id="F1"),
    Box("C2", "极筑", 5350, 450, 450, 1.08, 45, 110, "", factory_id="F1"),
    # 绿盾工厂
    Box("C3", "绿盾", 3160, 980, 1740, 5.39, 858, 993, "", factory_id="F2"),
    Box("C4", "绿盾", 2910, 780, 2150, 4.88, 950, 1072, "", factory_id="F2"),
    Box("C5", "绿盾", 3000, 800, 2150, 5.16, 1003, 1132, "", factory_id="F2"),
    # 车库门工厂
    Box("C6", "车库门", 3760, 580, 790, 1.72, 265, 299, "钢质门", factory_id="F3"),
    Box("C7", "车库门", 3760, 580, 790, 1.72, 265, 299, "钢质门", factory_id="F3"),
    Box("C8", "车库门", 4060, 580, 790, 1.86, 295, 332, "钢质门", factory_id="F3"),
    Box("C9", "车库门", 4260, 860, 800, 2.93, 552, 611, "", factory_id="F3"),
    Box("C10", "车库门", 3160, 630, 760, 1.51, 230, 260, "", factory_id="F3"),
    Box("C11", "车库门", 4560, 630, 830, 2.38, 373, 421, "", factory_id="F3"),
    Box("C12", "车库门", 5580, 630, 760, 2.67, 421, 474, "", factory_id="F3"),
    # 折叠门工厂
    Box("C13", "折叠门", 3760, 630, 790, 1.87, 304, 341, "", factory_id="F4"),
    Box("C14", "折叠门", 3760, 630, 790, 1.87, 304, 341, "", factory_id="F4"),
    Box("C15", "折叠门", 2885, 680, 1390, 2.73, 510, 590, "", factory_id="F4"),
    Box("C16", "折叠门", 5070, 245, 295, 0.37, 31, 63, "", factory_id="F4"),
    Box("C17", "折叠门", 2590, 900, 1360, 3.17, 903, 982, "", factory_id="F4"),
    # 凯研工厂
    Box("C18", "凯研", 3660, 760, 1540, 4.28, 1121, 1228, "", factory_id="F5"),
    Box("C19", "凯研", 3210, 900, 1430, 4.13, 1038, 1142, "", factory_id="F5"),
    Box("C20", "凯研", 3210, 760, 1430, 3.49, 893, 980, "", factory_id="F5"),
    Box("C21", "凯研", 2600, 900, 1200, 2.81, 647, 717, "", factory_id="F5"),
    Box("C22", "凯研", 2600, 900, 1050, 2.46, 662, 723, "", factory_id="F5"),
    Box("C23", "凯研", 3290, 760, 1200, 3.00, 697, 772, "", factory_id="F5"),
    Box("C24", "凯研", 3380, 680, 1680, 3.86, 1058, 1155, "", factory_id="F5"),
    Box("C25", "凯研", 3070, 800, 1520, 3.73, 1002, 1096, "", factory_id="F5"),
    Box("C26", "凯研", 5530, 620, 1330, 4.56, 989, 1103, "", factory_id="F5"),
    Box("C27", "凯研", 4980, 560, 1120, 3.12, 424, 502, "", factory_id="F5"),
    Box("C28", "凯研", 2265, 610, 1435, 1.98, 866, 916, "钢化玻璃", factory_id="F5"),
    Box("C29", "凯研", 2530, 550, 1460, 2.03, 617, 667, "钢化玻璃", factory_id="F5"),
    # 凯撒工厂
    Box("C30", "凯撒", 4300, 1650, 2480, 7.60, 920, 950, "斜撑铁架", factory_id="F6"),
]


# ============================================
# 1. 工厂分配算法
# ============================================

@dataclass
class Factory:
    """工厂配置"""
    factory_id: str
    name: str
    supported_brands: List[str]
    supported_types: List[str]
    max_dimensions: Tuple[float, float, float]
    max_weight: float
    capacity_daily: int = 9999
    priority: int = 0


FACTORY_DATABASE: List[Factory] = [
    Factory("F1", "极筑工厂", ["极筑"], ["铝合金门", "系统窗"], (6000, 2000, 2500), 1000, priority=1),
    Factory("F2", "绿盾工厂", ["绿盾"], ["防盗门", "防火门"], (3500, 2500, 2500), 1200, priority=1),
    Factory("F3", "车库门工厂", ["车库门"], ["车库门", "钢质门"], (1000, 2500, 6500), 800, priority=1),
    Factory("F4", "折叠门工厂", ["折叠门"], ["折叠门", "推拉门"], (1000, 2500, 6500), 1000, priority=1),
    Factory("F5", "凯研工厂", ["凯研"], ["铝合金门", "系统窗", "钢化玻璃门"], (6000, 2000, 2500), 1200, priority=1),
    Factory("F6", "凯撒工厂", ["凯撒"], ["大型门", "特种门"], (5000, 3000, 3000), 1500, priority=1),
]


@dataclass
class FactoryAssignmentResult:
    factory_id: str
    factory_name: str
    reason: str
    is_fallback: bool = False


def assign_factory(
    product_type: str,
    brand: str,
    dimensions: Tuple[float, float, float],
    weight: float,
    custom_factory_id: Optional[str] = None,
) -> FactoryAssignmentResult:
    """
    工厂分配核心逻辑：
    1. 客户指定优先
    2. 品牌+类型匹配
    3. 尺寸/重量约束
    4. 优先级最小
    """
    candidates: List[Factory] = []
    for f in FACTORY_DATABASE:
        if custom_factory_id and f.factory_id == custom_factory_id:
            return FactoryAssignmentResult(
                factory_id=f.factory_id,
                factory_name=f.name,
                reason="客户指定工厂",
                is_fallback=False,
            )
        brand_ok = brand in f.supported_brands
        type_ok = product_type in f.supported_types
        size_ok = all(d <= m for d, m in zip(sorted(dimensions), f.max_dimensions))
        weight_ok = weight <= f.max_weight
        if brand_ok and type_ok and size_ok and weight_ok:
            candidates.append(f)

    if candidates:
        best = min(candidates, key=lambda f: (f.priority, -f.capacity_daily))
        return FactoryAssignmentResult(
            factory_id=best.factory_id,
            factory_name=best.name,
            reason=f"品牌/类型匹配，优先级={best.priority}",
            is_fallback=False,
        )

    # 降级策略：仅按尺寸+重量匹配
    fallback = [f for f in FACTORY_DATABASE if all(d <= m for d, m in zip(sorted(dimensions), f.max_dimensions)) and weight <= f.max_weight]
    if fallback:
        best = min(fallback, key=lambda f: f.priority)
        return FactoryAssignmentResult(
            factory_id=best.factory_id,
            factory_name=best.name,
            reason="降级分配（品牌/类型不完全匹配，但尺寸/重量满足）",
            is_fallback=True,
        )

    return FactoryAssignmentResult(
        factory_id="",
        factory_name="无",
        reason="没有工厂能满足该产品的尺寸/重量要求",
        is_fallback=True,
    )


# ============================================
# 2. 拆件算法框架
# ============================================

@dataclass
class ComponentInput:
    """预解析组件清单输入"""
    component_id: str
    window_id: str
    component_type: str
    length: float
    width: float
    height: float
    weight: float
    material: str = ""


@dataclass
class ComponentOutput:
    """拆件+padding后输出"""
    component_id: str
    window_id: str
    finished_dimensions: Tuple[float, float, float]
    packaging_dimensions: Tuple[float, float, float]
    weight: float
    component_type: str = ""
    material: str = ""


class DrawingParserInterface(ABC):
    """图纸解析接口（预留）"""
    @abstractmethod
    def parse(self, file_path: str, window_id: str) -> List[ComponentInput]:
        pass


class ManualInputAdapter(DrawingParserInterface):
    """人工拆件结果适配器"""
    def __init__(self, pre_parsed_components: List[ComponentInput]):
        self.components = pre_parsed_components

    def parse(self, file_path: str, window_id: str) -> List[ComponentInput]:
        return [c for c in self.components if c.window_id == window_id]


def apply_padding(finished_dims: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """
    包装尺寸 = 成品尺寸 + 固定余量
    规则：最大的两维（宽/高）+60mm，最小的一维（厚度）+30mm
    """
    sorted_dims = sorted(finished_dims)
    thickness = sorted_dims[0]
    width, height = sorted_dims[1], sorted_dims[2]
    return tuple(sorted((thickness + 30, width + 60, height + 60)))


def build_components_from_manual(
    inputs: List[ComponentInput],
) -> List[ComponentOutput]:
    """将人工拆件结果转换为带包装尺寸的组件输出"""
    outputs = []
    for inp in inputs:
        finished = tuple(sorted((inp.length, inp.width, inp.height)))
        packaging = apply_padding(finished)
        outputs.append(ComponentOutput(
            component_id=inp.component_id,
            window_id=inp.window_id,
            finished_dimensions=finished,
            packaging_dimensions=packaging,
            weight=inp.weight,
            component_type=inp.component_type,
            material=inp.material,
        ))
    return outputs


# ============================================
# 3. 装箱分配算法（单件 + 多件同箱）
# ============================================

def can_fit(product_dims: Tuple[float, ...], box_dims: Tuple[float, ...], padding_mm: float = 0.0) -> Optional[Tuple[float, float, float]]:
    for perm in permutations(product_dims):
        padded = (perm[0] + padding_mm, perm[1] + padding_mm, perm[2] + padding_mm)
        if all(p <= b for p, b in zip(padded, box_dims)):
            return perm
    return None


def evaluate_match(
    box: Box,
    product: Product,
    padding_mm: float = 20.0,
    min_margin_per_side: float = 10.0,
    weight_safety_factor: float = 0.9,
) -> MatchResult:
    box_dims = box.dimensions
    prod_dims = product.dimensions
    rotation = can_fit(prod_dims, box_dims, padding_mm)
    fits = rotation is not None

    if fits:
        margins = tuple(b - (r + padding_mm) for b, r in zip(box_dims, rotation))
        margin_mm = margins
        leftover = box.volume_mm3 - product.volume_mm3
        utilization = (product.volume_mm3 / box.volume_mm3) * 100.0
    else:
        margin_mm = (float('-inf'),) * 3
        leftover = float('inf')
        utilization = 0.0

    weight_limit = box.net_weight * weight_safety_factor
    weight_ok = product.weight <= weight_limit

    score = 0.0
    if fits and weight_ok:
        util_score = 100.0 - abs(utilization - 80.0)
        volume_penalty = box.volume_mm3 / 1e9
        if all(m >= 0 for m in margin_mm):
            avg_margin = sum(margin_mm) / 3.0
            variance = sum((m - avg_margin) ** 2 for m in margin_mm) / 3.0
            uniformity_score = max(0, 100.0 - variance / 100.0)
        else:
            uniformity_score = 0.0
        min_margin_penalty = 50.0 if any(m < min_margin_per_side for m in margin_mm) else 0.0
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


def recommend_box(
    product: Product,
    box_list: Optional[List[Box]] = None,
    top_k: int = 3,
    padding_mm: float = 20.0,
    min_margin_per_side: float = 10.0,
    weight_safety_factor: float = 0.9,
    preferred_brands: Optional[List[str]] = None,
) -> List[MatchResult]:
    if box_list is None:
        box_list = BOX_DATABASE
    results = []
    for box in box_list:
        result = evaluate_match(box, product, padding_mm, min_margin_per_side, weight_safety_factor)
        if preferred_brands and result.box.brand in preferred_brands:
            result.score += 20.0
        results.append(result)
    results.sort(key=lambda r: (r.fits and r.weight_ok, r.score), reverse=True)
    valid = [r for r in results if r.fits and r.weight_ok]
    return valid[:top_k]


# ============================================
# 多件同箱 Bin-Packing
# ============================================

@dataclass
class PackedBox:
    """一个实际使用的箱子及其装载的组件"""
    box: Box
    items: List[Product] = field(default_factory=list)
    total_weight: float = 0.0
    total_volume: float = 0.0

    @property
    def volume_utilization(self) -> float:
        if self.box.volume_mm3 <= 0:
            return 0.0
        return (self.total_volume / self.box.volume_mm3) * 100.0

    @property
    def weight_ok(self, weight_safety_factor: float = 0.9) -> bool:
        return self.total_weight <= self.box.net_weight * weight_safety_factor


def can_fit_multiple(
    components: List[Product],
    box: Box,
    padding_mm: float = 20.0,
    weight_safety_factor: float = 0.9,
) -> bool:
    """
    简化版多件装箱判定：
    - 总重量约束
    - 总尺寸约束（简化：各组件单件都能装入，且总体积不超过箱子体积的 85%）
    - 长条形组件额外检查：最长边之和不超过箱子最长边
    """
    total_weight = sum(c.weight for c in components)
    if total_weight > box.net_weight * weight_safety_factor:
        return False

    total_volume = sum(c.volume_mm3 for c in components)
    if total_volume > box.volume_mm3 * 0.95:
        return False

    # 每个组件单独必须能装入
    for c in components:
        if can_fit(c.dimensions, box.dimensions, padding_mm) is None:
            return False

    # 长条形组件长度和检查（防止多个长条堆叠超长）
    sorted_box_dims = box.dimensions
    max_box_dim = sorted_box_dims[-1]
    long_items = [c for c in components if max(c.dimensions) > max_box_dim * 0.6]
    if long_items:
        sum_longest = sum(max(c.dimensions) for c in long_items)
        if sum_longest > max_box_dim * 1.5:
            return False

    return True


def greedy_multi_packing(
    components: List[Product],
    box_list: Optional[List[Box]] = None,
    padding_mm: float = 20.0,
    weight_safety_factor: float = 0.9,
    preferred_brands: Optional[List[str]] = None,
) -> List[PackedBox]:
    """
    贪心多件装箱算法：
    1. 为每个组件找出最佳单箱匹配
    2. 按体积从大到小排序组件
    3. 依次尝试放入已有箱子，失败则开新箱
    """
    if box_list is None:
        box_list = BOX_DATABASE

    # 过滤出每个组件的可行箱型（取 top 3）
    component_candidates: Dict[str, List[MatchResult]] = {}
    for c in components:
        component_candidates[c.name] = recommend_box(
            c, box_list=box_list, top_k=3,
            padding_mm=padding_mm,
            weight_safety_factor=weight_safety_factor,
            preferred_brands=preferred_brands,
        )

    # 按体积降序
    sorted_components = sorted(components, key=lambda c: c.volume_mm3, reverse=True)
    used_boxes: List[PackedBox] = []

    for comp in sorted_components:
        placed = False
        # 尝试放入已有箱子
        for pb in used_boxes:
            trial_items = pb.items + [comp]
            if can_fit_multiple(trial_items, pb.box, padding_mm, weight_safety_factor):
                pb.items.append(comp)
                pb.total_weight += comp.weight
                pb.total_volume += comp.volume_mm3
                placed = True
                break

        if not placed:
            # 开新箱：选评分最高的可行箱型
            candidates = component_candidates.get(comp.name, [])
            if not candidates:
                print(f"⚠️ 组件 {comp.name} 无合适箱型，跳过")
                continue
            best = candidates[0]
            new_pb = PackedBox(
                box=best.box,
                items=[comp],
                total_weight=comp.weight,
                total_volume=comp.volume_mm3,
            )
            used_boxes.append(new_pb)

    return used_boxes


# ============================================
# 辅助函数
# ============================================

def format_packed_box(pb: PackedBox, idx: int) -> str:
    lines = [
        f"\n📦 箱子 #{idx + 1}: {pb.box.box_id} ({pb.box.brand}) | 工厂: {pb.box.factory_id}",
        f"   箱子尺寸: {pb.box.length}×{pb.box.width}×{pb.box.height} mm",
        f"   装载组件数: {len(pb.items)} | 总重量: {pb.total_weight:.1f} kg / 限重: {pb.box.net_weight * 0.9:.1f} kg",
        f"   体积利用率: {pb.volume_utilization:.1f}%",
        "   组件列表:",
    ]
    for item in pb.items:
        lines.append(f"      - {item.name}: {item.length}×{item.width}×{item.height} mm, {item.weight} kg")
    return "\n".join(lines)


# ============================================
# 示例运行
# ============================================

if __name__ == "__main__":
    print("=" * 70)
    print("🏭 工厂分配示例")
    print("=" * 70)

    test_orders = [
        ("铝合金门", "极筑", (2500, 450, 1150), 300),
        ("车库门", "车库门", (3600, 550, 750), 250),
        ("折叠门", "折叠门", (5000, 220, 280), 50),
        ("钢化玻璃门", "凯研", (2200, 580, 1380), 800),
        ("大型特种门", "凯撒", (4200, 1600, 2400), 900),
        ("未知品牌门", "未知", (2000, 800, 2000), 400),
    ]

    for ptype, brand, dims, weight in test_orders:
        result = assign_factory(ptype, brand, dims, weight)
        status = "✅" if not result.is_fallback else "⚠️"
        print(f"{status} {ptype}({brand}) → {result.factory_name} [{result.factory_id}] | {result.reason}")

    print("\n" + "=" * 70)
    print("🔧 拆件 + Padding 示例")
    print("=" * 70)

    manual_components = [
        ComponentInput("W1-P1", "W1", "窗扇", 1100, 100, 2400, 120),
        ComponentInput("W1-P2", "W1", "窗扇", 1100, 100, 2400, 120),
        ComponentInput("W1-P3", "W1", "窗扇", 1100, 100, 2400, 120),
        ComponentInput("W1-P4", "W1", "窗扇", 1100, 100, 2400, 120),
        ComponentInput("W1-B1", "W1", "下部横梁", 2286, 610, 100, 90),
        ComponentInput("W1-B2", "W1", "下部横梁", 2286, 610, 100, 90),
        ComponentInput("W1-V1", "W1", "竖框", 3048, 80, 60, 45),
        ComponentInput("W1-V2", "W1", "竖框", 3048, 80, 60, 45),
    ]

    adapter = ManualInputAdapter(manual_components)
    parsed = adapter.parse("/drawings/W1.pdf", "W1")
    built = build_components_from_manual(parsed)

    for c in built:
        fd = c.finished_dimensions
        pd = c.packaging_dimensions
        print(f"{c.component_id}: 成品 {fd[0]:.0f}×{fd[1]:.0f}×{fd[2]:.0f} → 包装 {pd[0]:.0f}×{pd[1]:.0f}×{pd[2]:.0f} mm")

    print("\n" + "=" * 70)
    print("📦 单件装箱推荐示例")
    print("=" * 70)

    sample_products = [
        Product("铝合金门-1", 2500, 450, 1150, weight=300, product_type="铝合金门", brand="极筑"),
        Product("钢化玻璃门", 2200, 580, 1380, weight=800, product_type="钢化玻璃门", brand="凯研"),
        Product("大型折叠门", 5000, 220, 280, weight=50, product_type="折叠门", brand="折叠门"),
    ]

    for prod in sample_products:
        tops = recommend_box(prod, top_k=2)
        print(f"\n产品: {prod.name} | 尺寸: {prod.length}×{prod.width}×{prod.height} mm")
        if tops:
            for i, r in enumerate(tops, 1):
                print(f"   [{i}] {r.box.box_id}({r.box.brand}) 利用率:{r.volume_utilization:.1f}% 评分:{r.score:.2f}")
        else:
            print("   ⚠️ 无合适箱型")

    print("\n" + "=" * 70)
    print("📦 多件同箱 Bin-Packing 示例")
    print("=" * 70)

    # 同一工厂（凯研）的多个组件
    kaiyan_components = [
        Product("玻璃-1", 2200, 580, 1380, weight=400, product_type="钢化玻璃门", brand="凯研", window_id="W2"),
        Product("玻璃-2", 2200, 580, 1380, weight=400, product_type="钢化玻璃门", brand="凯研", window_id="W2"),
        Product("门框-1", 2200, 100, 100, weight=50, product_type="铝合金门", brand="凯研", window_id="W2"),
        Product("门框-2", 2200, 100, 100, weight=50, product_type="铝合金门", brand="凯研", window_id="W2"),
        Product("配件包", 500, 300, 200, weight=30, product_type="铝合金门", brand="凯研", window_id="W2"),
    ]

    # 只使用凯研工厂的箱子
    kaiyan_boxes = [b for b in BOX_DATABASE if b.factory_id == "F5"]
    packed = greedy_multi_packing(
        kaiyan_components,
        box_list=kaiyan_boxes,
        padding_mm=20.0,
        weight_safety_factor=0.9,
        preferred_brands=["凯研"],
    )

    print(f"\n共使用 {len(packed)} 个箱子:")
    for i, pb in enumerate(packed):
        print(format_packed_box(pb, i))

    print("\n" + "=" * 70)
    print("🔄 完整流程：订单 → 拆件 → 工厂分配 → 装箱")
    print("=" * 70)

    # 模拟一个订单
    order_window = {
        "window_id": "W3",
        "product_type": "车库门",
        "brand": "车库门",
        "components": [
            ComponentInput("W3-P1", "W3", "门板", 3500, 500, 700, 250),
            ComponentInput("W3-P2", "W3", "门板", 3500, 500, 700, 250),
            ComponentInput("W3-P3", "W3", "轨道", 3800, 80, 60, 80),
            ComponentInput("W3-P4", "W3", "配件", 500, 300, 200, 40),
        ],
    }

    # Step 1: 拆件 + padding
    comp_outputs = build_components_from_manual(order_window["components"])

    # Step 2: 工厂分配（按主产品尺寸分配）
    factory_result = assign_factory(
        order_window["product_type"],
        order_window["brand"],
        (3600, 750, 550),
        620,
    )
    print(f"\n订单 {order_window['window_id']} → 分配工厂: {factory_result.factory_name} [{factory_result.factory_id}]")

    # Step 3: 装箱
    factory_boxes = [b for b in BOX_DATABASE if b.factory_id == factory_result.factory_id]
    packing_products = [
        Product(
            name=c.component_id,
            length=c.packaging_dimensions[0],
            width=c.packaging_dimensions[1],
            height=c.packaging_dimensions[2],
            weight=c.weight,
            product_type=order_window["product_type"],
            brand=order_window["brand"],
            window_id=c.window_id,
        )
        for c in comp_outputs
    ]

    final_packed = greedy_multi_packing(
        packing_products,
        box_list=factory_boxes,
        padding_mm=0.0,  # padding 已在拆件阶段应用
        weight_safety_factor=0.9,
    )

    print(f"最终装箱方案：共 {len(final_packed)} 箱")
    for i, pb in enumerate(final_packed):
        print(format_packed_box(pb, i))

    # JSON 汇总输出
    summary = {
        "order_id": order_window["window_id"],
        "factory": {
            "factory_id": factory_result.factory_id,
            "factory_name": factory_result.factory_name,
        },
        "total_boxes": len(final_packed),
        "boxes": [
            {
                "box_id": pb.box.box_id,
                "brand": pb.box.brand,
                "items": [item.name for item in pb.items],
                "total_weight": round(pb.total_weight, 2),
                "volume_utilization": round(pb.volume_utilization, 2),
            }
            for pb in final_packed
        ],
    }
    print("\n📊 JSON 汇总:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
