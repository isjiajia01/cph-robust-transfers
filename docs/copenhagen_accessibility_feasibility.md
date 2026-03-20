# Copenhagen 可达性地图项目可行性研究

日期：2026-03-15

## 结论

这个项目对 Copenhagen 是可行的，而且更适合走两阶段路线：

1. 推荐路线：先做 API-first MVP，直接基于 Rejseplanen Labs API 2.0 的 `Reachability Search` 做可达性地图，复用当前仓库的 GTFS、实时延误和 dashboard 能力做增强层。
2. 后续路线：如果要做成可控、可解释、可叠加稳健性研究的产品，再补一个本地时刻表路由内核（RAPTOR/CSA 一类）。

总体判断：

- MVP 可行性：高
- 研究延展性：高
- 商业化前置合规复杂度：中
- 纯本地自研路由首版成本：中偏高

## 研究范围与假设

本报告按以下目标评估：

- 目标产品是一个类似 X 帖子中展示的 Copenhagen 公共交通可达性地图
- 用户可以设置起点、出发时间、最大通勤时长、交通方式
- 地图展示在指定时长内可到达的站点/区域，并可进一步叠加延误风险或换乘稳健性

不把本次研究范围扩展到：

- 支付体系
- 多城市通用 SaaS 平台
- 高频实时地图动画

## 为什么说它可行

### 1. 官方数据与 API 是通的

Rejseplanen Labs 官方 API 2.0 概览页列出了：

- `Trip Search`
- `Location Search by Name`
- `Reachability Search`
- `Journey Detail`

这意味着 Copenhagen 版 MVP 不必先自研完整时刻表路由，就可以先拿官方 reachability 能力做产品原型。

另外，Rejseplanen 的开放数据概览页明确写了可提供：

- `GTFS SCHEDULE`
- `GTFS-RT`
- `NeTEx`
- `SIRI ET`

也就是说，如果后续不想长期依赖 reachability API，丹麦公共交通的静态与实时数据链路仍然存在可替代方案。

### 2. 你现有仓库已经具备一半以上的底座

仓库已经有这些可直接复用的部分：

- GTFS 下载入口：`src/gtfs_ingest/download.py`
- GTFS 解析入口：`src/gtfs_ingest/parse.py`
- 静态 stop graph 构建：`src/graph/build_stop_graph.py`
- 实时采样与 BigQuery/GCP 路径：`docs/runbook.md`
- 风险模型与路径打分框架：`src/robustness/risk_model.py`、`src/robustness/router.py`
- 离线 HTML dashboard 渲染器：`src/app/results_dashboard.py`

这说明你不是从零开始做一个交通可达性产品，而是在一个已有 Copenhagen 交通研究仓库上补“交互地图产品层”。

### 3. Copenhagen 这个城市本身很适合做第一城

原因很直接：

- 城市规模适中，不像超大都市那样在计算和前端渲染上立刻爆炸
- 公共交通模式丰富，地图展示效果会明显
- 你现有项目本来就围绕 Copenhagen transit network
- 时区、数据源、分析语义已经在仓库内固定为 `Europe/Copenhagen`

## 与现有仓库的差距

这里是最关键的工程判断。

### 已有能力

1. 你已经能下载和解析 GTFS。
2. 你已经能做 stop-level 图结构分析。
3. 你已经有实时采样、延误分位数、风险模型和 dashboard。
4. 你已经有基础 CLI 和 docs/runbook，不需要先补项目骨架。

### 还缺的能力

#### A. 真正的“时刻表级可达性引擎”

当前 `src/graph/build_stop_graph.py` 做的是把 `stop_times` 压成 stop-to-stop 的中位旅行时间边，适合图结构分析，不适合直接做某一时刻出发的 reachability/isochrone。

原因是它把时刻依赖信息折叠掉了：

- 保留了边的中位旅行时间
- 但没有保留完整班次、发车时刻、到达时刻、服务日历和换乘时序

所以它不是一个真正的 earliest-arrival router。

#### B. 当前 router 不是路径生成器

当前 `src/robustness/router.py` 是“对外部给定候选路径做风险打分”的工具，不是“从起点自动生成所有可达路径”的路由器。

证据很明确：

- 输入要求是 `--candidates`
- 输出是 Pareto-ready table
- 它基于 `candidates` 行里的 `travel_time_min`、`transfers`、`line`、`mode` 做风险估计

这对研究很有用，但离地图产品还差一步核心能力：从起点、时间、限制条件自动枚举可达站点或路径。

#### C. 还没有真正的地图交互层

当前仓库有离线 research dashboard，但还没有一个面向最终用户的交互式地图应用：

- 没有起点搜索与拖点
- 没有 reachability heatmap/等时圈渲染
- 没有请求节流、缓存、shareable URL

## 两条实现路线

## 路线 A：API-first MVP

### 做法

- 前端地图：MapLibre GL JS 或等价轻量前端地图层
- 位置搜索：Rejseplanen `Location Search by Name`
- 可达性计算：Rejseplanen `Reachability Search`
- 详情补充：必要时调用 `Journey Detail`
- 风险增强：用你仓库已有的 delay quantiles / risk model 给可达结果附加可靠性标签

### 优点

- 落地快
- 不需要先实现完整本地时刻表路由
- 可直接验证产品交互是否成立
- 官方数据覆盖和更新由对方维护

### 缺点

- 依赖外部 API 配额和可用性
- 商业化需要进入正式协议
- 如果 `Reachability Search` 返回的是 reachable stops/locations 而不是连续多边形，地图上的“面状热力层”需要你自己插值或转成网络染色

最后一点是一个真实但可控的产品风险。基于官方服务描述，我判断它至少能返回可达站点/地点；是否天然返回能直接绘图的 polygon，需要在拿到实际响应后确认。

### 适合的目标

- 先做一个可演示的 Copenhagen demo
- 验证“找房/选酒店/选办公地点”的使用场景
- 快速形成面试或作品集级展示

## 路线 B：本地自研时刻表路由

### 做法

- 用 GTFS static 建立 timetable index
- 建立 footpath/transfer graph
- 用 RAPTOR 或 CSA 生成 earliest-arrival reachability
- 把 reachability 结果转成 stop layer、network layer、hex layer 或 polygon layer
- 再把现有 realtime/risk model 叠上去

### 优点

- 可控性高
- 可解释性强
- 更容易和你当前“稳健换乘/延误风险”研究深度耦合
- 后续可扩展到“最快 vs 最稳健”的双目标地图

### 缺点

- 首版成本明显更高
- 需要额外处理 calendar、calendar_dates、午夜跨天、步行换乘、footpath 半径、服务日切换
- 若要接实时，还要决定用 GTFS-RT、SIRI ET 还是继续复用现有 Rejseplanen collector

### 适合的目标

- 你要把它做成研究资产或长期产品资产
- 你想把风险模型直接作为路由目标之一，而不是事后打分

## 可行性分项评分

按 1 到 5 分评估：

| 维度 | 评分 | 判断 |
| --- | --- | --- |
| 数据可得性 | 5 | 官方 API 和开放数据路径都存在 |
| MVP 工程可落地性 | 4.5 | API-first 几乎没有根本性阻碍 |
| 现有仓库复用度 | 4 | 数据、分析、dashboard 可复用，缺产品路由层 |
| 纯本地自研首版难度 | 3 | 可做，但不是低成本首发 |
| 合规/商业化确定性 | 3 | 非商业试用容易，正式商业化需要协议 |
| 展示效果潜力 | 5 | Copenhagen 网络密度和模式丰富，演示效果好 |

## 接入与合规风险

### 1. Labs access 不是零门槛匿名开放

Rejseplanen Labs 的接入页写明：

- 个人/组织需要申请 access
- 典型处理时间约 5 个工作日
- 免费计划适用于非商业使用
- 免费计划默认每月 50,000 次 API 调用
- 付费计划从每月 1,500,000 次调用起步，并要求商业协议

这意味着：

- 做 demo/作品集/内部验证问题不大
- 一旦面向更大规模用户或收费用途，就要尽早处理合同与配额问题

### 2. 需要核对归属与缓存条款

开放数据概览页写有 `CC BY 4.0`，但真正上线前仍然要分别核查：

- Labs API 的调用条款
- 地图底图供应商条款
- 是否允许长期缓存 reachability 响应

这里不能偷懒，因为产品形态和研究使用在条款上常常不完全相同。

## 成本与时间预估

## 方案 A：API-first MVP

### 范围

- Copenhagen 单城
- 起点搜索或地图点选
- 出发时间选择
- 最大通勤时长滑块
- 交通方式/机构筛选
- 地图上显示可达站点和颜色分层

### 预估

- 技术 PoC：2 到 4 天
- 可演示 MVP：1 到 2 周
- 加上风险 overlay、分享链接、缓存：再加 3 到 5 天

这是在不额外追求账户体系和复杂后端治理的前提下。

## 方案 B：本地自研路由

### 范围

- GTFS timetable index
- reachability 计算
- 地图渲染
- 可选的实时/风险叠加

### 预估

- 第一版可用原型：3 到 6 周
- 如果要做到“结果稳定 + 参数可解释 + 可持续维护”，会更长

## 推荐的最小落地路径

我建议按这个顺序做：

1. 先申请并确认 Rejseplanen Labs access。
2. 先打通 `Location Search by Name` 和 `Reachability Search` 的最小调用链路。
3. 做一个 stop-based 的 Copenhagen reachability map，不追求连续 polygon。
4. 把你已有的 realtime/risk model 作为第二层增强，而不是第一天就做成本地路由核心。
5. 只有当产品交互被证明成立，再决定是否投资本地 RAPTOR/CSA 引擎。

这个顺序的好处是：

- 前 20% 的投入就能验证 80% 的产品价值
- 不会在真正有用户反馈之前，先把时间砸进底层路由重写
- 也不会浪费你现有仓库在 Copenhagen 研究上的积累

## 我对这个项目的最终判断

如果你的目标是“尽快做出一个 Copenhagen 版、能拿给别人看、能说明问题的 demo”，这个项目是明显值得做的，优先级可以定为高。

如果你的目标是“一开始就做成完全自研、可商用、可扩到多城市的底层平台”，那它仍然可行，但不适合直接从这一步起跑，应该先用 API-first 版本验证需求。

一句话结论：

可做，值得做，但第一阶段不要把自己锁死在“先自研完整路由内核”这条最慢路径上。

## 主要依据

### 官方来源

- Rejseplanen Labs API 2.0 Overview: https://labs.rejseplanen.dk/hc/en-us/articles/22694768420114-API-2-0
- Rejseplanen Labs Access to Labs: https://labs.rejseplanen.dk/hc/en-us/articles/29752913572002-Access-to-Labs
- Rejseplanen Open Data Overview: https://labs.rejseplanen.dk/hc/en-us/articles/28397043873426-Open-Data-Overview

### 仓库内依据

- `README.md`
- `docs/runbook.md`
- `src/gtfs_ingest/download.py`
- `src/graph/build_stop_graph.py`
- `src/robustness/router.py`
- `src/robustness/risk_model.py`
- `src/app/results_dashboard.py`

## 需要补的一个最小验证

要把“可行”升级成“已验证”，还差一个很小但很关键的动作：

- 用真实 Labs key 实际调用一次 `Reachability Search`
- 确认响应结构到底是 stop list、location list、network path 还是 polygon-like geometry

这一步会决定前端第一版到底做：

- stop heatmap
- network reachability
- 还是直接等时圈面图

在拿到真实响应前，这一点我保留为唯一核心未知项。
