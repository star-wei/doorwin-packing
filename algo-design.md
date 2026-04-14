# 门窗企业装箱方案系统 — 核心算法设计文档

## 1. 概述

### 1.1 系统目标
为门窗企业设计一套从报价单 → 拆件 → 工厂分配 → 装箱推荐的自动化算法系统。

### 1.2 数据流

```
报价单系统
    ↓
原始门窗订单（W1: 4572×3048mm，W2: 6400.8×2438.4mm）
    ↓
图纸拆件模块（CAD/PDF 解析 或 人工拆件）
    ↓
组件清单（W1-P1, W1-P2, ...）+ 成品尺寸 + 重量
    ↓
工厂分配算法
    ↓
各工厂组件子集
    ↓
装箱分配算法（单件/多件同箱 bin-packing）
    ↓
装箱方案（箱型、组件列表、摆放方向）
```

---

## 2. 工厂分配算法

### 2.1 设计原则
- 不同工厂有各自擅长的产品类型、品牌、尺寸范围
- 分配目标：满足工厂产能约束的前提下，最小化运输/生产成本
- 现阶段以**规则匹配**为主，未来可扩展为**优化模型**

### 2.2 输入
```python
@dataclass
class FactoryAssignmentInput:
    product_type: str       # 产品类型：铝合金门、车库门、折叠门、钢化玻璃门等
    brand: str              # 品牌/系列：极筑、绿盾、凯研、凯撒等
    dimensions: Tuple[float, float, float]  # 成品尺寸 (mm)
    weight: float           # 重量 (kg)
    quantity: int = 1       # 数量
    custom_factory_id: Optional[str] = None  # 客户指定工厂
```

### 2.3 工厂配置结构
```python
@dataclass
class Factory:
    factory_id: str
    name: str
    supported_brands: List[str]
    supported_types: List[str]
    max_dimensions: Tuple[float, float, float]  # 该工厂能处理的最大尺寸
    max_weight: float
    capacity_daily: int  # 日产能（件数），可选
    priority: int = 0    # 优先级，数字越小越优先
```

### 2.4 分配规则（优先级从高到低）
1. **客户指定**：若 `custom_factory_id` 存在且合法，直接分配
2. **品牌匹配**：产品品牌必须在工厂的 `supported_brands` 列表中
3. **类型匹配**：产品类型必须在工厂的 `supported_types` 列表中
4. **尺寸/重量约束**：产品尺寸和重量不得超过工厂上限
5. **优先级选择**：满足以上条件的工厂中，选 `priority` 最小者
6. **冲突处理**：若多个工厂优先级相同，选产能利用率最低者（负载均衡）

### 2.5 输出
```python
@dataclass
class FactoryAssignmentResult:
    factory_id: str
    factory_name: str
    reason: str           # 分配原因说明
    is_fallback: bool     # 是否为降级分配
```

---

## 3. 拆件算法框架

### 3.1 现状说明
- 当前拆件规则**依赖 CAD/PDF 图纸**，自动化解析难度大
- 算法框架需**预留图纸解析接口**，同时支持**人工拆件结果录入**

### 3.2 输入层

#### 输入 A：图纸文件（未来自动化）
```python
@dataclass
class DrawingInput:
    order_id: str
    window_id: str
    file_path: str          # CAD/PDF 文件路径
    file_type: str          # "pdf" | "dwg" | "dxf"
```

#### 输入 B：预解析组件清单（现阶段主要使用）
```python
@dataclass
class ComponentInput:
    component_id: str       # 如 W1-P1
    window_id: str          # 所属门窗编号
    component_type: str     # 窗扇、横梁、竖框、中梃、玻璃等
    length: float
    width: float
    height: float
    weight: float
    material: str = ""      # 材质备注
```

### 3.3 输出层
```python
@dataclass
class ComponentOutput:
    component_id: str
    window_id: str
    finished_dimensions: Tuple[float, float, float]  # 成品尺寸
    packaging_dimensions: Tuple[float, float, float]  # 包装尺寸（已加 padding）
    weight: float
```

### 3.4 图纸解析接口（预留）
```python
class DrawingParserInterface(ABC):
    @abstractmethod
    def parse(self, drawing: DrawingInput) -> List[ComponentInput]:
        """解析图纸，返回组件清单"""
        pass

class ManualInputAdapter(DrawingParserInterface):
    """人工拆件结果适配器：直接接收预录入的组件清单"""
    def __init__(self, pre_parsed_components: List[ComponentInput]):
        self.components = pre_parsed_components

    def parse(self, drawing: DrawingInput) -> List[ComponentInput]:
        return [c for c in self.components if c.window_id == drawing.window_id]
```

### 3.5 Padding 规则
```python
def apply_padding(finished_dims: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """
    包装尺寸 = 成品尺寸 + 固定余量
    规则：宽/高 + 60mm，厚度 + 30mm
    假设三边中：最大的两维为宽/高，最小的一维为厚度
    """
    sorted_dims = sorted(finished_dims)
    thickness = sorted_dims[0]
    width, height = sorted_dims[1], sorted_dims[2]
    return tuple(sorted((thickness + 30, width + 60, height + 60)))
```

---

## 4. 装箱分配算法

### 4.1 问题定义
- **输入**：同一工厂内的多个组件（含包装尺寸、重量）
- **输出**：每个组件被分配到哪个箱子，以及同箱组件的列表
- **约束**：
  1. 箱子内所有组件尺寸不超限（考虑摆放方向）
  2. 箱子内总重量 ≤ 箱子净重 × 安全系数
  3. 优先提高体积利用率，减少总箱数

### 4.2 核心思路
采用**两阶段启发式算法**：
1. **阶段一：单件匹配** — 为每个组件找出所有能装下的箱型
2. **阶段二：多件聚合** — 在满足约束的前提下，尝试将多个组件合并到同一个箱子

### 4.3 单件装箱（已有基础）
基于 `box_packing_solver.py` 的 `can_fit` 和 `evaluate_match`：
- 产品可旋转，尝试 6 种方向
- 评分考虑体积利用率、余量均匀度、重量约束

### 4.4 多件同箱（Bin-Packing 扩展）

#### 4.4.1 箱子内可用空间模型
采用**剩余空间列表（Residual Space List）**的简化版：
- 初始剩余空间 = 箱子内部尺寸
- 每放入一个组件，更新剩余空间
- 为简化实现，采用**按某一维度切分**的策略

```python
@dataclass
class ResidualSpace:
    x: float; y: float; z: float
    length: float; width: float; height: float
```

#### 4.4.2 多件装箱判定
```python
def can_fit_multiple(components: List[Product], box: Box, padding_mm: float = 0.0) -> bool:
    """
    判定多个组件是否能放入同一个箱子。
    采用贪心策略：按体积从大到小排序，依次尝试放入。
    """
```

#### 4.4.3 多件装箱贪心算法
```
算法：GreedyMultiPacking
输入：组件列表 C，箱型列表 B
输出：装箱方案 P

1. 对每个组件 c ∈ C，计算其所有可行的单箱匹配结果
2. 将组件按体积降序排序
3. 初始化空箱子列表 boxes_used = []
4. 对每个组件 c：
   a. 遍历 boxes_used，尝试将 c 放入已有箱子
   b. 若成功，更新该箱子内的组件列表和剩余空间
   c. 若失败，从 B 中选择评分最高的新箱子装入 c，并加入 boxes_used
5. 返回装箱方案
```

### 4.5 评分与优化
- **总箱数最少**为主要目标
- **次目标**：体积利用率均衡（避免某个箱子过空）
- **可选**：对结果做局部搜索（尝试交换组件到不同箱子）

---

## 5. 算法原型文件说明

### 5.1 `box_packing_solver_v2.py`
包含以下模块：
1. `factory_assignment.py` 逻辑 — `Factory`, `assign_factory()`
2. `component_framework.py` 逻辑 — `Component`, `DrawingParserInterface`, `ManualInputAdapter`, `apply_padding()`
3. `packing_algorithm.py` 逻辑 — `can_fit_multiple()`, `greedy_multi_packing()`, `PackingPlan`
4. 扩展现有的 `BOX_DATABASE`，按工厂分组
5. 示例运行：完整流程从订单 → 拆件 → 工厂分配 → 装箱方案

---

## 6. 后续优化方向

1. **图纸解析**：引入 CAD 解析库（如 `ezdxf`）或 PDF 图纸识别（OCR + 规则）
2. **装箱算法**：升级为 3D Bin-Packing（如 OR-Tools CP-SAT、专用启发式库）
3. **工厂分配**：引入线性规划/整数规划，优化全局产能分配
4. **重量估算**：根据材质和尺寸建立重量估算模型，减少人工录入
