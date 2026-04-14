import streamlit as st
import sys
sys.path.insert(0, ".")
from box_packing_solver_v2 import (
    assign_factory,
    greedy_multi_packing,
    Product,
    FactoryAssignmentResult,
    BOX_DATABASE,
)

st.set_page_config(page_title="Doorwin 装箱方案预览", layout="wide")
st.title("🚪 Doorwin 装箱方案智能推荐系统")
st.markdown("输入订单信息，系统自动分配工厂、拆件并推荐最优箱型。")

with st.sidebar:
    st.header("📋 订单参数")
    order_id = st.text_input("订单编号", "DW2025-1245")
    product_name = st.text_input("产品名称", "110固定窗")
    width = st.number_input("宽度 (mm)", value=4572, step=10)
    height = st.number_input("高度 (mm)", value=3048, step=10)
    thickness = st.number_input("厚度 (mm)", value=110, step=10)
    qty = st.number_input("数量 (套)", value=1, min_value=1, step=1)
    weight = st.number_input("单件重量 (kg)", value=188.0, step=10.0)
    
    st.markdown("---")
    st.header("🔧 拆件规则")
    split_count = st.number_input("拆成几扇", value=4, min_value=1, step=1)
    
    st.markdown("---")
    st.header("📦 Padding 规则")
    pad_wh = st.number_input("宽/高余量 (mm)", value=60, step=10)
    pad_thick = st.number_input("厚度余量 (mm)", value=30, step=10)
    
    st.markdown("---")
    st.header("🏭 工厂分配")
    product_type = st.selectbox("产品类型", ["fixed_window", "sliding_door", "garage_door", "folding_door"])
    brand = st.text_input("品牌", "凯研")

if st.button("🚀 生成装箱方案", type="primary"):
    with st.spinner("计算中..."):
        # 拆件：简单均分宽度
        components = []
        base_width = width / split_count
        for i in range(split_count):
            # 边扇稍宽（模拟框架差异）
            w = base_width + 30 if i == 0 or i == split_count - 1 else base_width
            comp = Product(
                name=f"{order_id}-P{i+1}",
                length=w + pad_wh,
                width=height + pad_wh,
                height=thickness + pad_thick,
                weight=weight,
                product_type=product_type,
                brand=brand,
                window_id=order_id,
            )
            components.append(comp)
        
        # 工厂分配（基于第一个组件）
        first_comp = components[0]
        factory_result = assign_factory(
            product_type=first_comp.product_type,
            brand=first_comp.brand,
            dimensions=(first_comp.length, first_comp.width, first_comp.height),
            weight=first_comp.weight,
        )
        
        # 获取该工厂的箱型（这里简化：用全部箱型过滤品牌）
        factory_boxes = [b for b in BOX_DATABASE if b.factory_id == factory_result.factory_id]
        if not factory_boxes:
            # fallback：用推荐的品牌箱型
            factory_boxes = [b for b in BOX_DATABASE if b.brand == brand] or BOX_DATABASE
        
        # 装箱
        packed_boxes = greedy_multi_packing(components, box_list=factory_boxes)
        
        # 展示结果
        st.success(f"工厂分配：{factory_result.factory_name}（ID: {factory_result.factory_id}）{'[降级匹配]' if factory_result.is_fallback else ''}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("总组件数", len(components))
        col2.metric("使用箱数", len(packed_boxes))
        avg_util = sum(pb.volume_utilization for pb in packed_boxes) / len(packed_boxes) if packed_boxes else 0
        col3.metric("平均体积利用率", f"{avg_util:.1f}%")
        
        st.markdown("---")
        st.subheader("📦 装箱明细")
        
        for idx, pb in enumerate(packed_boxes, 1):
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 1.5, 1, 1.5])
                c1.markdown(f"**箱 {idx}：{pb.box.box_id}**（{pb.box.brand}）")
                c2.markdown(f"尺寸：{pb.box.length:.0f}×{pb.box.width:.0f}×{pb.box.height:.0f} mm")
                c3.markdown(f"利用率：{pb.volume_utilization:.1f}%")
                weight_limit = pb.box.net_weight * 0.9
                status = "✅" if pb.total_weight <= weight_limit else "⚠️ 超重"
                c4.markdown(f"总重：{pb.total_weight:.1f} / {weight_limit:.1f} kg {status}")
                
                data = []
                for comp in pb.items:
                    data.append({
                        "组件编号": comp.name,
                        "包装尺寸": f"{comp.length:.0f}×{comp.width:.0f}×{comp.height:.0f}",
                        "重量(kg)": comp.weight,
                    })
                st.dataframe(data, use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("Powered by Doorwin Packing Solver v2 | 算法文档详见 GitHub 仓库")
