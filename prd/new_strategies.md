# 账单分类器 - 4 个新策略 PRD

> 状态：v1（已与用户对齐设计，待回测后开始实施）
> 涉及范围：`bill_classifier/` pipeline 内新增 step、`detail_sheet.py` 输出改造、新增 `tools/` 下回测脚本与 `feishu_history_loader`
> 不在范围：账单之外的开销（现金、信用卡直接消费、银行扣款）；策略本身的调度/UI 改动

---

## 1. 背景

程序已运行多年，逐月在飞书表格里产出"账单明细 YYYYMM"，并由人工补全分类。多年累积的标注数据可被反过来增强 pipeline。本 PRD 解决以下 4 类问题：

1. 单条账单看 payee/item_name 想不出是什么，但**同 payee 多次出现过**且历史已标注 → 用历史回填。
2. **淘宝购物金**机制（充 1000 得 1030，消费时不上账，退购物金时才上账）导致同 order_id 内合并不上的金额。
3. **跨月退款/购物金退款**导致上月已经入账、本月又出现一条无法关联的反向条目，无法还原真实消费金额。
4. **美团/点评/京东**等渠道，payee/item_name 都没语义信息，单条无法分类，需借助前后账单上下文。

---

## 2. 现有 Pipeline 速查（约束基础）

```
parse → meican_filter → merge_payee → merge_refund → exact_match → regex_match → skip_keywords → wet_market → gpt → 输出
```

关键约束（影响新策略设计）：

- `merge_refund` 仅处理**同 order_id**（淘宝预付款 + 尾款 + 退款），跨 order_id 不管；无 order_id 直接 SKIP。
- `wet_market` 是「锚点扩散」典范：锚点必须 `ClassifyAlg.MATCH`，1 小时窗口。
- `gpt` 显式跳过 `payee in {美团, 美团平台商户}` 和 `payee=京东 + item_name 含"订单编号"`（信息不足）。
- `bill.py` 解析时，**微信"已退款"** 状态会直接把原 amount 扣减（同月内），所以**同月退款** pipeline 已闭合；**跨月退款**则在本月成为孤立条目。
- `detail_sheet.fill_income_data()` 已存在，被 `main.py:62` 注释掉，目前主表右侧列空白可用。
- `main.py:159-189` 输出时按 `ClassifyAlg` 分组：`MATCH → REGULAR → WET_MARKET → GPT → UNKNOWN → OTHER → SKIP → INCOME`。

---

## 3. 共享架构原则

### 3.1 BillItem 作为策略上下文（context）

策略需要的额外信息**直接挂在 `BillItem` 上**新增可选字段，不另开容器。这是后续所有策略共享的扩展机制。

约定（按需新增，每个策略只用自己关心的字段）：

| 字段 | 类型 | 含义 | 谁写入 |
|------|------|------|--------|
| `neighbor_group` | `Optional[str]` | 相邻账单组 ID，同组紧邻输出 | 策略 4 |
| `cross_month_origin` | `Optional[dict]` | 跨月退款关联到的原支出条目（payee/amount/bill_time/category 等） | 策略 3 |
| `taobao_balance_extra` | `Optional[str]` | 购物金合并后追加的说明文本（如 "购物金消费余额: 868.95"） | 策略 2 |
| `display_section` | `Optional[str]` | 输出位置标签：`"main"` / `"right_extra"` | 策略 3 |

修改 `BillItem.__init__` 时把这些字段缺省 `None`，对现有 step 透明无感。

### 3.2 飞书历史数据加载器（共享基建）

策略 1、3 都需要拉历史"账单明细 YYYYMM" sheet 数据。新增模块：

- `bill_classifier/feishu_history_loader.py`
  - 接口 `load_year_months(year, sheet_token, months) → List[HistoryItem]`
  - `HistoryItem` 含 `payee, item_name, amount, bill_type, category, bill_time, order_id, bill_source, owner`（即原表 9 列）
  - 内置本地 cache：`<repo_root>/.cache/bill_classifier/history/<year>/<month>.csv`，命中 cache 不调飞书
  - `--refresh` 命令行参数强制重新拉
  - cache 目录加入 `.gitignore`

- 已验证可访问的 4 个表 token：
  - 23 年：`shtcnsqbKMuExxV1Eryr2fAS8hh`（老格式 sheet）
  - 24 年：`N63SsTTpMhbKgDteGYjcEmu2nDb`
  - 25 年：`NQ6hsZttrh4hU3tNDcRc7Aqsnsd`
  - 26 年：`OjoKwUtrPi5uqgkxgbfccYHWn5f`（wiki 链接里的 token，直接当 sheet token 用即可，不需要 wiki scope）

### 3.3 输出右侧列（策略 3 用）

激活并改造 `detail_sheet.fill_income_data()`：

- 主表区列：金额 / 分类 / payee / item_name / 账单类型 / 时间 / 来源 / 账单人 / 分类算法 / 日常·额外（10 列，现状）
- 间隔 1 列
- 右侧补充列：标签 / 时间 / 金额 / 关联说明（4 列，新增）
  - 标签枚举：`跨月退款 / 购物金跨月 / 工资收入 / 利息 / 转账收 / 其他`

`main.py` 把 `display_section == "right_extra"` 的条目分到右侧列写入；其余写主表。

**月度汇总（summary_sheet）保持不变**：右侧列纯展示，不参与 SUMIF。

---

## 4. 策略详设

### 策略 1：history_payee（历史商户分类回填）

#### 主目标场景
微信转账类（按摩账户、阿姨、定期理发等）：payee 是人名/账户名，难以维护到分类字典里，但同一对象往往多次出现且分类一致。商户类（淘宝/京东）也能受益。

#### 算法
1. 通过 `feishu_history_loader` 拉**历史**月份的"账单明细"。
2. 对每条历史 EXPENSE，提取 `(payee, category)`。
3. 聚合：每个 payee 统计每个 category 的次数 `count_by_cat`，得到 `dominant_category` 和 `dominant_ratio`。
4. 命中条件：`total_count >= COUNT_THRESHOLD` 且 `dominant_ratio >= RATIO_THRESHOLD`。
5. 在 pipeline 中：UNKNOWN 的 EXPENSE，payee **完全相等**于 history_map 中的 key 时，赋分类，标 `ClassifyAlg.HISTORY`。

**关键约束**：history_map 构建时**当月数据不参与**，避免 leakage。具体做法：传入"截止月"，过滤 `bill_time < 截止月第一天` 的数据。

#### 实施位置
`regex_match` 之后、`skip_keywords` 之前。理由：
- exact / regex 是用户在分类表显式维护的"权威"规则，应优先；
- history 是从过去数据归纳的"近似规则"，置于其后；
- 但要先于 wet_market 和 gpt——history 命中后**不允许**作为 wet_market 锚点（与 REGULAR 同等对待，避免链式污染）。

#### 决策点（已对齐）
| 决策点 | 结论 |
|--------|------|
| payee 匹配方式 | **完全相等**（不做 substring，不做 normalize） |
| 是否区分 owner | 默认 **不分**（zrz/cwx 共用 history_map），回测时也跑一份分组版对比 |
| 是否允许做 wet_market 锚点 | **不允许** |
| 阈值 | 待回测后定，候选组合见下文 |

#### 回测方案（实施前先做）

> 这是策略 1 落代码前的**前置门槛**，不达标就不上。

**数据源**：飞书 24 年表 + 25 年表的"账单明细 YYYYMM"。

**滚动测试**：6 个测试月（25 年 7 ~ 12 月），每月跑两种 mode：

| mode | history 数据来源（截至该测试月） |
|------|----------------------------------|
| `fixed_6m` | 测试月之前的 6 个月 |
| `cumulative` | 24 年初到测试月之前 |

**阈值组合**（每组都跑）：
- `(count>=2, ratio>=80%)`
- `(count>=3, ratio>=80%)` — 默认
- `(count>=3, ratio>=90%)`
- `(count>=5, ratio>=80%)`

**指标**：
- `coverage = 命中数 / 当月 EXPENSE 总数`
- `precision = 命中且 category 与实际标注一致 / 命中数`
- `coverage_wechat_transfer` — 单独看微信转账类（bill_source=wechat 且 item_name/交易类型含"转账"），这是用户最关心的子集
- `precision_wechat_transfer` — 同上子集的 precision
- 错配 dump：命中但 category 错的条目，每月最多 30 条，记 (payee, item_name, amount, history 推断, 实际)

**输出**：
- 报告表（在对话里展示）：6 月 × 2 mode × 4 阈值 = 48 行指标
- 错配明细：`tools/backtest_results/mismatch_<month>_<mode>_<threshold>.csv`（路径已被 `.gitignore`）
- 决策：用户审阅后确定上线阈值

#### 代码改动
- 新增 `bill_classifier/feishu_history_loader.py`
- 新增 `tools/backtest_history_payee.py`（独立运行脚本，不入 pipeline）
- 新增 `bill_classifier/classifiers/history_payee.py`（回测 OK 后实现）
- `bill_item.py`：`ClassifyAlg` 新增 `HISTORY = "历史推断"`
- `bill_classifier/classifiers/__init__.py`：注册到 `STEP_REGISTRY` 和 `DEFAULT_STEPS`

---

### 策略 2：taobao_balance_merge（淘宝购物金合并 - 同月内）

#### 数据现象（来自 202510 实样本）
- 充值条目：`item_name` 含 `购物金 充值享折上折【充1000得1030】`，bill_type=支出。
- 退款条目：`item_name` 以 `退款-` 开头并含 `购物金`，bill_type=不计收支。
- order_id 形如 `2025102023001101601400100131*3007421472149123455_236787279472125534`。**下划线第二段（如 `3007421472149123455`）是核心订单号**，多笔部分退款共用此核心。
- `_advance` 后缀的退款属于"退预付款"，也按同核心订单号合并。
- 实际购物金消费**不出现在账单中**。

#### 算法
1. 提取每个 item 的 `core_order_id = order_id.split('_')[1] if '_' in order_id else order_id`（拆失败降级到整 order_id）。
2. 找出"购物金组"：item_name 含 `购物金` 的支出 + 同 core_order_id 的退款（item_name 以 `退款-` 开头）。
3. 仅当**充值 + 退款都在本月**时合并：
   - 输出一条记录，**继承充值条目的 payee/item_name**。
   - `amount = 充值 - 退款总额`。
   - `taobao_balance_extra = "购物金消费余额: <amount>"`，附加到 item_name 末尾（实际写表时拼上去）。
   - `category` 留 UNKNOWN，让后续 history_payee / GPT 兜底（充值条目的 payee/item_name 仍带店铺名，可被识别）。
4. 跨月场景**本 step 不处理**，全部走策略 3。

#### 实施位置
`merge_refund` 之后、`exact_match` 之前。理由：跟 `merge_refund` 同属合并阶段，且必须在分类前完成。

#### 决策点（已对齐）
| 决策点 | 结论 |
|--------|------|
| 识别关键字 | item_name 含 `购物金` 单一关键字；item_name 以 `退款-` 开头判断为退款侧 |
| 是否新增 ExpenseCategory | **不新增**，category 留 UNKNOWN |
| 跨月处理 | **不在本 step**，由策略 3 接管 |
| 适用渠道 | **仅淘宝**（通过 order_id 中含下划线 + item_name 含购物金特征过滤） |
| `_advance` 后缀的退款 | **算入合并**，不特殊对待 |
| "充 1000 得 1030"赠送差额 | **忽略**，因为购物金消费不在账单中体现 |
| 充值后全退（amount=0） | 跟现 merge_refund 行为一致，整条 SKIP |

#### 代码改动
- 新增 `bill_classifier/classifiers/taobao_balance_merge.py`
- `bill_item.py`：`BillItem` 新增字段 `taobao_balance_extra: Optional[str] = None`
- 注册到 `STEP_REGISTRY` 和 `DEFAULT_STEPS`

---

### 策略 3：cross_month_unified（跨月统一识别）

#### 职责
统一处理所有"上月已经入账，本月才出现的反向条目"，三种情形：
1. 跨月退款（支付宝 + 微信）
2. 跨月购物金（充值在上月，退款在本月）
3. 跨月小红书 / 抖音退货（实施时另抽样验证格式）

#### 关键说明：微信跨月退款的特点

> 这是策略 3 设计的核心约束，由用户和我对齐过。

- **同月内退款** pipeline 已闭合：`bill.py` 在解析时，看到 `当前状态` 列含 `已退款` / `已全额退款`，会直接把原条目的 amount 扣减。所以同月退款不会成为孤立条目。
- **跨月退款**：上月账单里原条目当时状态还没变（退款发生在下月），所以**上月真的扣了钱**。本月账单里则出现一条独立退款收入条目，例如：
  ```
  交易类型 = "北京大学国际医院-退款"
  payee = "北京大学国际医院"
  item_name = "北京大学国际医院"
  bill_type = 收入
  amount = ¥50.00
  交易单号 = 50303404872025102869693538887
  ```
- **关键**：这条退款的"交易单号"跟原支出的"交易单号" **完全不共享** —— 微信不像支付宝那样在退款 order_id 里嵌入原 order_id 核心段。
- 后果：微信跨月退款**无法用 order_id 反查**，只能用 `(payee + amount)` 严格匹配。

#### 反查策略（按渠道分流）

| 渠道 / 类型 | 反查方式 | 严格度 |
|-------------|---------|--------|
| 支付宝退款 | order_id 核心段相等 | 命中即关联 |
| 支付宝购物金跨月 | order_id 核心段相等 | 命中即关联 |
| 支付宝（其它） | order_id 核心段优先；不行则 (payee + amount 严格相等) | 唯一才关联 |
| **微信跨月退款** | (payee 剥离 `-退款` 后缀 + amount 严格相等)，时间窗 6 个月 | **必须候选唯一**；多候选不处理 |
| 小红书 / 抖音 | 实施时另抽样验证 | 暂留 TODO |

#### 输出
关联成功的退款条目：
- `display_section = "right_extra"`
- `cross_month_origin = {payee, amount, bill_time, category}`
- 写入右侧列（4 列结构）：
  ```
  [类型]            [日期]       [金额]    [关联说明]
  跨月退款          2025-10-28   ¥50.00   原支出: 2025-09-15 北京大学国际医院 50.00 (医疗)
  购物金跨月        2025-10-28   ¥125.64  原充值: 2025-09 戴维贝拉购物金 1000.00
  ```

关联失败：保留现状（OTHER 不计支出 + 警告日志）。

#### 实施位置
`merge_refund` 之后（专门处理 merge_refund 漏掉的跨月情形），策略 2 之后（让购物金的同月情形先合并掉）。

#### 决策点（已对齐）
| 决策点 | 结论 |
|--------|------|
| 反查窗口 | 6 个月 |
| order_id 优先 vs payee+amount | **能用 order_id 用 order_id**；不能用的（微信）规则从严 |
| 微信反查多候选 | **不处理**（保持原 OTHER 状态 + 警告日志） |
| 微信部分退款（金额不等） | **不处理**（部分退款放弃，保持现状可接受） |
| 月度汇总公式 | **不改**（右侧列纯展示，不入 SUMIF） |
| 小红书 / 抖音 | 实施时另抽样几个月样本再写细则 |

#### 代码改动
- 新增 `bill_classifier/classifiers/cross_month_unified.py`
- `bill_item.py`：`BillItem` 新增字段 `cross_month_origin: Optional[dict] = None`、`display_section: Optional[str] = None`
- `detail_sheet.py`：扩展 `fill_income_data` 为通用"右侧补充列"写入；接受 (label, time, amount, ref) 4 列。
- `main.py`：取消 `fill_income_data` 注释，按 `display_section` 分流；激活右侧列。
- 复用 `feishu_history_loader`。

---

### 策略 4：neighbor_inference（相邻账单推断）

#### 数据现象
- 美团团购付费 + 微信扫码补尾款：两笔账单时间相差几分钟，前者 payee=`美团`/`美团平台商户` 无语义，后者明确商户名（如 `北京麻辣啵咔餐饮管理有限公司`）。
- 京东 / 大众点评同理。
- **没有"团购券"专属字段可区分**——金额规律、payee、item_name 都没有。

#### 算法
1. 触发条件：UNKNOWN item，且属于"低信息量"类：
   - `payee in {美团, 美团平台商户, 大众点评, 京东}`，或
   - `item_name` 以订单号特征结尾（含 `订单编号` / `美团订单-` / 纯长串数字）。
2. 在该 item **之后** 5 分钟窗口内查找锚点：
   - 锚点条件：`ClassifyAlg.MATCH`（仅精确匹配，不算 REGULAR / HISTORY / WET_MARKET）
   - 窗口内**严格 1 条**锚点 → 采纳锚点 category。
   - 窗口内 **0 条** 或 **≥ 2 条** → **不处理**（保持 UNKNOWN）。
3. 命中：
   - 当前 item 的 `category = 锚点 category`，`classify_alg = ClassifyAlg.NEIGHBOR`
   - **共享 neighbor_group**：当前 item 和锚点都设置 `neighbor_group = <group_id>`（用锚点 order_id 或时间戳）

#### 输出排序（方案 A）

> 关键：策略 4 命中的两条要在最终表上**紧邻显示**。

`main.py` 输出逻辑改造（在现有按 ClassifyAlg 分组的基础上）：
1. 按现有顺序遍历分组（MATCH → REGULAR → ... → INCOME）
2. 遇到 `neighbor_group != None` 的 item：把同 group 的所有 item 一起写出（紧跟），后续在其它分组里再遇到同 group 成员则跳过（去重）
3. 锚点的 `classify_alg` 仍保留 `MATCH`（不破坏其原始信息），UNKNOWN 命中条目变成 `NEIGHBOR`

效果示意（同组紧邻）：
```
分类         payee              item_name              算法
餐饮         北京麻辣啵咔...     陈记坝坝面三里屯店      完全匹配     ← 锚点（neighbor_group=g1）
餐饮         美团               美团订单-2510...        相邻推断     ← 命中（neighbor_group=g1）
```

#### 决策点（已对齐）
| 决策点 | 结论 |
|--------|------|
| 窗口长度 | 5 分钟 |
| 方向 | **单向**：从 UNKNOWN 团购券**往后** 5 分钟看 |
| 严格 1 条 | 是 |
| 锚点限制 | **仅 MATCH**（不算 REGULAR / HISTORY / WET_MARKET） |
| 输出排序方案 | **方案 A**：BillItem 加 `neighbor_group` 字段，输出时同组紧邻 |
| GPT 跳过逻辑 | 维持不变；NEIGHBOR 不命中的美团/京东条目仍走 GPT 跳过 → UNKNOWN 等人工 |

#### 代码改动
- 新增 `bill_classifier/classifiers/neighbor_inference.py`
- `bill_item.py`：`BillItem` 新增字段 `neighbor_group: Optional[str] = None`；`ClassifyAlg` 新增 `NEIGHBOR = "相邻推断"`
- `main.py` 输出逻辑：增加 neighbor_group 同组紧邻的输出处理
- 注册到 `STEP_REGISTRY` 和 `DEFAULT_STEPS`

---

## 5. 实施顺序

1. **【先行回测】** 写 `tools/backtest_history_payee.py` + 拉飞书 24 / 25 年数据 → 跑回测 → 报告给用户审阅 → 确认阈值。
2. **【基建】** 写 `feishu_history_loader.py`（含 cache）。
3. **【策略 4】** `neighbor_inference`（独立、不依赖飞书历史，最简单先落） + `BillItem.neighbor_group` + `main.py` 同组紧邻输出。
4. **【策略 1】** `history_payee` step + 集成到 pipeline + `ClassifyAlg.HISTORY`。
5. **【策略 3】** `cross_month_unified` + 改造 `detail_sheet.fill_income_data` + `main.py` 右侧列分流 + 多个 BillItem 字段。
6. **【策略 2】** `taobao_balance_merge`（同月内，跨月已被策略 3 覆盖） + `BillItem.taobao_balance_extra`。

每步独立可发：写完一个 step + 测试 → commit → 跑一次实际账单验证。

---

## 6. 决策对齐索引

便于后续翻查的"已拍板"决策合集：

- BillItem 作为策略 context，按需加可选字段
- 飞书 4 个表（23/24/25/26）都通过 sheets API 直接读，无需 wiki scope
- 策略 1：完全相等 payee；不分 owner（先）；阈值待回测；不做 wet_market 锚点
- 策略 1 回测：fixed_6m + cumulative 双 mode；4 组阈值；6 个测试月
- 策略 2：仅淘宝；仅同月内；UNKNOWN 兜底；忽略充值赠送差额；`_advance` 算入
- 策略 3：order_id 优先；微信严格 (payee+amount) + 候选唯一；不改月度汇总；右侧列纯展示
- 策略 4：5 分钟单向；严格 1 条；MATCH 锚点；方案 A 同组紧邻输出
- 历史数据：本地 cache 路径 `<repo>/.cache/bill_classifier/history/`，加 `.gitignore`
- 回测产物：`tools/backtest_results/`，加 `.gitignore`

---

## 7. 待回测后再细化

- 策略 1 上线阈值（看回测报告决定 `count` / `ratio`）
- 策略 1 是否区分 owner（看分组对照效果）
- 策略 3 小红书 / 抖音格式细节（实施时另抽样）

---

## 8. 实施后发现：淘宝购物金 order_id 真实形态（修订）

实施策略 2 / 3 时，从 202506 / 202510 真实账单抽样发现 PRD 初稿对 order_id 形态的假设有误。**真实形态**（来自 `bill.py` 解析 row[1] 商家订单号字段）：

| 类型 | 真实 oid 形态 | payee | 例子 |
|------|--------------|-------|------|
| 购物金充值 | `T200P<19位数字>` | 总是 `购物金` | `T200P2613628093127195986` |
| 购物金退款 | `<19位数字>_<18位数字>`（两段） | 店铺名脱敏 (`da**店`/`zu**店`) | `2613032798634195986_217847532514198659` |
| 退款 advance | `<prefix>_<19位数字>_advance`（罕见三段，row[0] 形式才有） | 店铺名 | `..._3015081734490123455_advance` |

**核心订单号关联规则**（已在 `_extract_core_order_id` 实现）：
- `T200P<X>` → 核心 = `X`
- `<X>_<sub>` → 核心 = `X`（**第 1 段**）
- 充值 oid 去掉 `T200P` 前缀 = 退款 oid 第 1 段，由此关联

> 早期 PRD 写"下划线第二段是核心"是基于 row[0] 形式（含 `*` 或三段）观察的，但 `bill.py` 实际用的是 row[1]，形态不同。请注意阅读时 PRD 的 `_extract_core_order_id` 实现以代码为准。

**真实数据验证结果**：
- 202506：18 充值 + 5 退款 → 策略 2 同月合并出 5 组（其中 1 组净 0 SKIP）
- 202510：2 笔跨月退款被策略 3 关联（ba**店 / ho**店），7 笔 da**店 购物金跨月退款因为对应充值在 202503 之前（超 6 月反查窗口）→ 保留 OTHER 不计支出。这是数据本身限制，非算法 bug。
- 已加专项单测 `test_extract_core_t200p_charge_format` / `test_extract_core_refund_two_segments_format`
