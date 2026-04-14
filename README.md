# Doorwin 装箱方案智能推荐系统

门窗行业装箱方案自动化工具，支持工厂分配、拆件、箱型智能匹配。

## 🎯 核心功能

- **工厂分配**：根据产品类型、品牌、尺寸自动分配到对应工厂
- **智能拆件**：支持人工拆件录入，预留 CAD/PDF 图纸自动解析接口
- **箱型匹配**：基于 30+ 种箱型数据库，采用贪心启发式算法实现多件同箱最优分配
- **Web 预览**：基于 Streamlit 的交互式装箱方案预览界面

## 📁 文件结构

```
├── box_packing_solver.py          # v1 单件装箱推荐算法
├── box_packing_solver_v2.py       # v2 工厂分配 + 多件同箱算法
├── app.py                         # Streamlit 预览应用
├── box_packing_readme.md          # v1 算法说明
├── algo-design.md                 # 算法设计文档
├── backend-design.md              # 后端架构设计文档
└── frontend-design.md             # 前端界面设计文档
```

## 🚀 本地预览

### 1. 安装依赖

```bash
pip install streamlit pandas openpyxl
```

### 2. 启动 Streamlit

```bash
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`

### 3. 在线部署（Streamlit Cloud）

1. Fork 本仓库到个人 GitHub
2. 访问 [share.streamlit.io](https://share.streamlit.io)
3. 选择 `doorwin-packing` 仓库和 `app.py` 文件
4. 点击 Deploy，即可获得在线访问地址

## 🏗️ 系统设计

### 整体架构

```
报价单系统 → 后端 API → 算法服务 → 前端预览/PDF 导出
```

三端设计文档详见：
- [backend-design.md](./backend-design.md)
- [frontend-design.md](./frontend-design.md)
- [algo-design.md](./algo-design.md)

## 🔧 算法说明

### v2 核心流程

1. **工厂分配** (`assign_factory`)：基于规则引擎匹配最优工厂
2. **拆件处理** (`ManualInputAdapter`)：接收拆件清单，自动计算包装尺寸
   - Padding 规则：宽/高 +60mm，厚度 +30mm
3. **装箱算法** (`greedy_multi_packing`)：
   - 为每个组件找出可行箱型 Top-3
   - 按体积从大到小排序
   - 依次尝试放入已有箱子，无法放入则开新箱
   - 同时满足体积利用率、重量限制、长条形约束

## 📄 License

Internal Use Only —  doorwingroup
