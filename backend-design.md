# 门窗企业装箱方案系统 — 后端架构设计文档

> 版本: v1.0  
> 日期: 2026-04-14  
> 作者: backend-dev specialist

---

## 1. 项目背景与需求摘要

- **对接报价单系统**：直接拉取订单参数（门窗编号、位置、规格、宽度、高度、数量、面积等）。
- **多工厂支持**：不同产品按规则分配到不同工厂。
- **工厂箱型库**：每个工厂拥有独立的箱型数据库（如 C1-C30）。
- **核心输出**：装箱方案预览 + PDF 导出。

---

## 2. 技术栈建议

| 层级 | 选型 | 理由 |
|------|------|------|
| **开发语言** | Go (Gin) 或 Node.js (NestJS) | 高并发、强类型、生态成熟；若团队熟悉 JS 可选 NestJS |
| **数据库** | PostgreSQL (主库) + Redis (缓存/锁/队列) | PG 支持 JSONB 和强事务，适合复杂订单与方案数据 |
| **消息队列** | RabbitMQ 或 NATS | 异步任务解耦（算法调用、PDF 生成），RabbitMQ 可靠性高 |
| **文件存储** | MinIO / 阿里云 OSS | 存储生成的 PDF 与装箱预览图 |
| **算法通信** | gRPC + 异步任务 (MQ) | 实时计算用 gRPC；耗时计算走 MQ 异步 |
| **外部对接** | RESTful API + Webhook | 报价单系统通常提供 HTTP 接口 |
| **文档/监控** | Swagger/OpenAPI + Prometheus/Grafana | 接口文档与可观测性 |

---

## 3. 后端 API 架构设计（RESTful）

### 3.1 接口总览

| 模块 | 接口 | 方法 | 说明 |
|------|------|------|------|
| **报价单同步** | `/api/v1/quotations/sync` | POST | 手动触发同步报价单数据 |
| **报价单同步** | `/api/v1/quotations/webhook` | POST | 接收报价单系统推送 |
| **订单管理** | `/api/v1/orders` | GET/POST | 查询/创建订单 |
| **订单管理** | `/api/v1/orders/:id` | GET/PUT/DELETE | 单订单 CRUD |
| **工厂分配** | `/api/v1/orders/:id/factory-assign` | POST | 为订单分配工厂 |
| **算法服务** | `/api/v1/orders/:id/packing/calculate` | POST | 提交装箱计算任务 |
| **算法服务** | `/api/v1/packing-tasks/:taskId/status` | GET | 查询计算任务状态 |
| **预览输出** | `/api/v1/orders/:id/packing/preview` | GET | 获取装箱方案预览数据 |
| **PDF 导出** | `/api/v1/orders/:id/packing/pdf` | POST | 提交 PDF 生成任务 |
| **PDF 导出** | `/api/v1/packing-tasks/:taskId/download` | GET | 下载生成的 PDF |
| **工厂/箱型** | `/api/v1/factories` | GET/POST | 工厂管理 |
| **工厂/箱型** | `/api/v1/factories/:id/box-types` | GET/POST | 箱型管理 |

### 3.2 报价单系统对接方式

**推荐组合：Webhook 为主 + 定时同步兜底**

1. **Webhook 实时推送**
   - 报价单系统配置回调地址：`POST /api/v1/quotations/webhook`
   - 推送事件：`quotation.created`、`quotation.updated`
   - 本系统收到后写入 `quotation_raw` 表，异步解析为订单数据。

2. **定时同步兜底**
   - 每日凌晨 2:00 执行定时任务，调用报价单系统查询接口（如 `/external/quotations?updated_after=xxx`）。
   - 比对差异，补漏或修正。

3. **数据一致性保障**
   - Webhook 接收端幂等：以 `quotation_no + version` 为唯一键。
   - 失败重试：报价单系统未收到 200 时按指数退避重试。
   - 对账任务：每日比对两边订单总数与关键字段哈希。

### 3.3 工厂分配接口

```http
POST /api/v1/orders/:id/factory-assign
Content-Type: application/json

{
  "factory_id": "F-2024-SH",
  "operator_id": "user_001",
  "reason": "铝合金门窗 → 上海工厂"
}
```

**分配规则引擎（可扩展）**
- 按产品类型 → 工厂能力匹配
- 按地理位置 → 就近分配
- 按工厂产能负载 → 动态调度
- 支持自动分配 + 人工复核

### 3.4 算法服务通信

**双通道设计：**

| 场景 | 通道 | 说明 |
|------|------|------|
| 快速试算（< 3s） | gRPC / HTTP | 同步返回初步装箱结果 |
| 正式排产计算（> 3s） | MQ 异步任务 | 提交任务 → 算法消费 → 回写结果 |

**异步任务状态流转：**

```
PENDING → RUNNING → SUCCESS / FAILED
```

**算法服务契约（gRPC/HTTP）**

```protobuf
service PackingAlgorithm {
  rpc Calculate (PackingRequest) returns (PackingResponse);
}

message PackingRequest {
  string task_id = 1;
  string factory_id = 2;
  repeated ProductItem items = 3;
  repeated BoxTypeSpec box_types = 4;
}

message PackingResponse {
  string task_id = 1;
  bool success = 2;
  repeated BoxResult boxes = 3;
  string error_msg = 4;
}
```

### 3.5 预览与 PDF 导出

- **预览**：直接从 `packing_solution` 表组装 JSON 返回前端，支持 3D/2D 渲染数据。
- **PDF 导出**：
  1. 用户请求 → 系统生成 `pdf_task` 记录。
  2. 消费者从 MQ 拉取任务，调用 `wkhtmltopdf` / `Playwright` / `Python-ReportLab` 生成 PDF。
  3. PDF 上传至对象存储，回写 `download_url`。
  4. 用户轮询或 WebSocket 通知获取下载链接。

---

## 4. 数据库模型设计

### 4.1 ER 图（文字描述）

```
[quotation_raw] 1-->* [order]
[order] 1-->* [order_item]
[order_item] *--1 [factory]
[factory] 1-->* [box_type]
[order] 1-->* [packing_task]
[packing_task] 1--1 [packing_solution]
[packing_solution] 1-->* [box_instance]
[box_instance] 1-->* [packed_item]
```

### 4.2 核心表结构

#### `quotation_raw` — 报价单原始数据

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| quotation_no | VARCHAR(64) | 报价单号 |
| version | INT | 版本号（幂等） |
| payload | JSONB | 原始 JSON |
| status | VARCHAR(20) | `pending` / `parsed` / `error` |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

#### `order` — 订单主表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| order_no | VARCHAR(64) UNIQUE | 订单编号（来自报价单） |
| quotation_no | VARCHAR(64) | 关联报价单号 |
| customer_name | VARCHAR(128) | 客户名称 |
| total_area | DECIMAL(10,2) | 总面积 |
| status | VARCHAR(20) | `draft` / `assigned` / `calculated` / `exported` |
| assigned_factory_id | UUID FK → factory | 分配工厂 |
| created_at | TIMESTAMPTZ | 创建时间 |
| updated_at | TIMESTAMPTZ | 更新时间 |

#### `order_item` — 订单明细（门窗产品）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| order_id | UUID FK → order | 订单 ID |
| product_code | VARCHAR(64) | 门窗编号 |
| location | VARCHAR(128) | 安装位置 |
| spec | VARCHAR(64) | 规格型号 |
| width_mm | INT | 宽度 |
| height_mm | INT | 高度 |
| quantity | INT | 数量 |
| area | DECIMAL(10,2) | 面积 |
| material_type | VARCHAR(32) | 材质（用于工厂分配） |

#### `factory` — 工厂

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| factory_code | VARCHAR(32) UNIQUE | 工厂编码 |
| name | VARCHAR(128) | 工厂名称 |
| location | VARCHAR(128) | 地理位置 |
| capabilities | JSONB | 支持的产品类型/材质 |
| is_active | BOOLEAN | 是否启用 |

#### `box_type` — 箱型库

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| factory_id | UUID FK → factory | 所属工厂 |
| box_code | VARCHAR(16) | 箱型代码（如 C1） |
| length_mm | INT | 箱长 |
| width_mm | INT | 箱宽 |
| height_mm | INT | 箱高 |
| max_weight_kg | DECIMAL(8,2) | 最大承重 |
| is_active | BOOLEAN | 是否启用 |

#### `packing_task` — 装箱计算任务

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| task_no | VARCHAR(64) UNIQUE | 任务编号 |
| order_id | UUID FK → order | 订单 ID |
| task_type | VARCHAR(20) | `preview` / `pdf` |
| status | VARCHAR(20) | `pending` / `running` / `success` / `failed` |
| algorithm_payload | JSONB | 提交给算法的参数 |
| result_payload | JSONB | 算法返回结果 |
| download_url | VARCHAR(512) | PDF 下载地址（仅 pdf 任务） |
| started_at | TIMESTAMPTZ | 开始时间 |
| completed_at | TIMESTAMPTZ | 完成时间 |
| created_at | TIMESTAMPTZ | 创建时间 |

#### `packing_solution` — 装箱方案

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID PK | 主键 |
| task_id | UUID FK → packing_task | 任务 ID |
| order_id | UUID FK → order | 订单 ID |
| total_boxes | INT | 总箱数 |
| total_volume | DECIMAL(12,4) | 总体积利用率 |
| boxes_json | JSONB | 箱列表及内部摆放详情 |
| created_at | TIMESTAMPTZ | 创建时间 |

---

## 5. 核心流程时序图

### 5.1 报价单同步 → 订单生成

```
报价单系统          本系统(API)         本系统(Worker)       数据库
    |                   |                   |                  |
    |-- webhook: 报价单变更 --------------->|                  |
    |                   |-- 写入 quotation_raw (幂等) -------->|
    |<-- 200 OK --------|                   |                  |
    |                   |-- 发布解析任务 --->|                  |
    |                   |                   |-- 读取 raw payload
    |                   |                   |-- 解析为 order + order_item
    |                   |                   |-- 写入 order / order_item
    |                   |                   |-- 更新 raw.status = parsed
```

### 5.2 工厂分配 → 装箱计算 → 预览

```
前端          API Gateway       业务服务         MQ          算法服务        数据库
 |               |               |              |              |             |
 |-- 分配工厂 -->|               |              |              |             |
 |               |-- 调用工厂分配接口 --------->|              |             |
 |               |               |-- 更新 order.assigned_factory_id ------->|
 |<-- 分配成功 --|               |              |              |             |
 |               |               |              |              |             |
 |-- 计算装箱 -->|               |              |              |             |
 |               |-- 提交计算任务 ----------->|              |             |
 |               |               |-- 创建 packing_task (pending) --------->|
 |               |               |-- 推送 MQ 任务 ----------> |             |
 |<-- taskId ----|               |              |              |             |
 |               |               |              |              |             |
 |-- 轮询状态 -->|               |              |              |             |
 |               |-- 查询 task status ------->|              |             |
 |               |               |-- 读取 packing_task <--------------------|
 |<-- running ---|               |              |              |             |
 |               |               |              |<-- 消费任务 --|             |
 |               |               |              |              |-- 执行装箱算法
 |               |               |              |-- 返回结果 -->|             |
 |               |               |              |              |             |
 |               |               |<-- 回调/消费结果 ----------|             |
 |               |               |-- 写入 packing_solution --------------->|
 |               |               |-- 更新 packing_task.status = success --->|
 |-- 轮询状态 -->|               |              |              |             |
 |<-- success ---|               |              |              |             |
 |               |               |              |              |             |
 |-- 获取预览 -->|               |              |              |             |
 |               |-- 查询 packing_solution --->|              |             |
 |<-- preview JSON -------------|              |              |             |
```

### 5.3 PDF 生成与下载

```
前端          API Gateway       业务服务         MQ          PDF Worker      对象存储      数据库
 |               |               |              |              |             |            |
 |-- 导出 PDF -->|               |              |              |             |            |
 |               |-- 提交 PDF 任务 ----------->|              |             |            |
 |               |               |-- 创建 packing_task (pdf/pending) ----->|
 |               |               |-- 推送 MQ 任务 ----------> |             |            |
 |<-- taskId ----|               |              |              |             |            |
 |               |               |              |              |             |            |
 |               |               |              |<-- 消费任务 --|             |            |
 |               |               |              |              |-- 读取 packing_solution
 |               |               |              |              |-- 渲染 PDF 模板
 |               |               |              |              |-- 生成 PDF 文件
 |               |               |              |              |-- 上传 OSS --->|
 |               |               |              |              |<-- 返回 URL --|
 |               |               |              |              |             |            |
 |               |               |<-- 回调结果 ---------------|             |            |
 |               |               |-- 更新 task.download_url + status ----->|
 |               |               |              |              |             |            |
 |-- 轮询/下载 ->|               |              |              |             |            |
 |<-- download_url ---------------|              |              |             |            |
```

---

## 6. 关键设计决策

### 6.1 与外部报价单系统对接

- **首选 Webhook**：实时性高，减少主动轮询压力。
- **定时同步兜底**：防止 Webhook 丢包或网络抖动导致的数据缺失。
- **幂等设计**：`quotation_no + version` 唯一键，重复推送不覆盖已解析数据，而是记录为历史版本。
- **异常隔离**：Webhook 接收只做最小校验和落库，复杂解析交给后台 Worker，避免阻塞外部系统。

### 6.2 与算法服务通信

- **协议分层**：
  - 同步场景（快速试算）用 gRPC/HTTP，用户体验好。
  - 异步场景（正式排产）用 MQ，避免长连接阻塞，支持算法服务弹性扩缩容。
- **任务状态持久化**：所有计算任务落库 `packing_task`，支持断点恢复和审计。
- **超时与重试**：算法任务设置 10 分钟超时，失败后可重试 3 次，最终失败进入死信队列人工介入。

### 6.3 数据一致性

- **订单与报价单**：通过 `quotation_raw` 作为 Source of Truth，解析后的 `order` 表可随时重建。
- **订单与装箱方案**：
  - 订单变更时，旧 `packing_solution` 标记为 `outdated`，不直接删除，保留历史版本。
  - 新计算任务生成新的 `packing_solution`，通过 `task_id` 关联。
- **分布式事务**：
  - 工厂分配、任务创建等本地事务使用 PostgreSQL 事务。
  - 跨服务（算法、PDF）采用**最终一致性** + 任务状态机 + 补偿重试。

### 6.4 扩展性

- **多工厂**：`factory` 表独立，`box_type` 按 `factory_id` 隔离，未来新增工厂只需插入数据。
- **算法服务扩展**：算法作为独立服务，可通过增加消费者实例水平扩展。
- **PDF 生成扩展**：PDF Worker 无状态，可独立部署和扩容。
- **规则引擎扩展**：工厂分配规则初期可写在配置/代码中，后期可迁移到独立的规则引擎服务。

---

## 7. 部署架构建议（简化版）

```
┌─────────────────┐
│   前端 (Vue/React)  │
└────────┬────────┘
         │
    ┌────▼────┐
    │  Nginx  │
    └────┬────┘
         │
┌────────▼────────┐
│  API Gateway    │  ← Gin / NestJS (多实例)
│  (RESTful API)  │
└────────┬────────┘
         │
    ┌────┼────┐
    │    │    │
┌───▼┐ ┌─▼─┐ ┌▼────┐
│ PG │ │Redis│ │RabbitMQ│
│主库 │ │缓存 │ │ 队列   │
└────┘ └───┘ └─┬───┘
               │
        ┌──────┼──────┐
        │      │      │
    ┌───▼─┐ ┌─▼──┐ ┌─▼───┐
    │算法服务│ │PDF Worker│ │ 对账 Worker │
    │(gRPC) │ │(无状态) │ │ (定时)     │
    └─────┘ └────┘ └─────┘
```

---

## 8. 后续建议

1. **接口契约细化**：补充 Swagger/OpenAPI 3.0 文档。
2. **算法服务联调**：确认算法输入输出字段、体积计算方式、箱型匹配规则。
3. **PDF 模板设计**：与前端协作确定预览渲染与 PDF 模板的一致性。
4. **权限设计**：引入 RBAC，区分销售（查看订单）、调度员（分配工厂）、管理员（配置箱型）。
5. **日志与追踪**：接入 OpenTelemetry，实现跨服务 Trace。
