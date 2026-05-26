# 评估中发现的 Bug + 修复说明（同步给组员）

> 我用一套**真实新闻语句的 benchmark**（从 Yahoo Finance 抓的 113 条,标好资产类别/claim 类型,
> 事实类的数字/日期做了扰动造假;标签都对 SEC/FRED 核验过)整批跑了我们的 pipeline,
> 发现**前端(实体提取/分类/路由)基本能用,但"判定(verdict)"环节有系统性 bug**。
> 这份文档说清楚:发现了什么、为什么、我改了哪里、还剩什么没修。

---

## TL;DR

| 阶段 | 表现 | 状态 |
|---|---|---|
| 实体/资产提取 | 规则 80.5% → **+LLM 89.4%** | ✅ 能用(AI 有帮助) |
| claim 类型分类 | 84.5%(纯本地规则) | ✅ 能用 |
| fact-check 路由 | 84.1% | ⚠️ 宏观有漏(见 Bug 2) |
| **判定 verdict** | **真话确认 0/50(真实新闻)、0/20(SEC锚定)** | ❌ **坏了,见 Bug 1** |

核心问题:**它几乎把所有声明都判 `contradicted`/`not_applicable`,连和 SEC 一字不差的真值都判矛盾**;
真假按置信度完全分不开(AUC 0.345,比抛硬币还差)。一个"永远说假"的笨基线(80%)都能赢它(74%)。

---

## Bug 1（根因,已修)：`sec_company_facts` 没把"声明对应期间"的数字捞进证据

**现象**:真话(如 "Apple FY2025 营收 416,161,000,000",和 SEC 完全一致)被判 `not_found` → 进而 `contradicted`。

**根因**:`src/financial_credibility/data_sources.py` 的 `sec_company_facts` 里:
```python
clean_values.sort(key=lambda v: v.get("filed",""), reverse=True)
for value in clean_values[:2]:   # 每个指标只留最近 2 个“已申报”值
```
SEC 同一指标有大量**重叠期间**(年度/季度/半年/9个月)。只取"最近申报的 2 个" →
近期季度把**声明真正引用的那个财年/季度值挤掉了**。结果要核对的数字根本不在证据里 → 匹配不到。
(她的数字匹配本身没问题——`_numbers_match` 能处理 "$81.62 billion" 词形 + 1.2% 容差;
问题纯粹是"对的那个数没被捞出来"。)

**修复(Fix A,已改 `data_sources.py`)**:改成**按"报告期间(期末日 + 期间类型)"去重,年度值和季度值都保留**,
每个指标列出最近若干个,并标注 `for fiscal year/quarter ending YYYY-MM-DD: <值>`。
这样声明引用的那个期间值一定在证据里。

**验证**:修复后,"416B 年度""$81.62B 季度""$111.2B 季度"的**数字匹配都从 `not_found` → `verified`**。

---

## Bug 2（路由漏洞,建议修)：宏观类没被路由到 FRED

**现象**:"美国 CPI 同比 +3.8%" 这类宏观声明 → **检索到 0 条证据** → 无法核对。

**根因**:FRED 取数靠关键词匹配(`_fred_series_for_claim`),"consumer prices" 没命中任何 series。

**建议**:扩充 FRED 关键词/别名映射(consumer prices→CPIAUCSL、unemployment→UNRATE、payrolls→PAYEMS、
oil/WTI→DCOILWTICO 等),或在 source_selection 里对 macro_indicator 资产类强制走 FRED。
(注:FRED 的免费 CSV 端点 `fredgraph.csv?id=...` 不需要 key,也可作兜底。)

---

## Bug 3（判定层残留,建议修 = Fix B)：找不到/不确定时,不该判"矛盾"

即便 Fix A 让数字匹配上了,**atomic 判定层仍不稳**(同一句真话:有的 `supported`、有的 `not_applicable`、
有的 `contradicted`):
- **`not_applicable`**:`decompose_claims` 偶尔把明显的事实声明误分成"非事实"而跳过(分类不稳)。
- **`contradicted`**:atomic 那条路径(`claim_verification.py` / `derivations.py`)有时仍拿声明的数字
  去比**错误期间**的值,或 LLM logic judge 把"没看到数字"当成"矛盾"。

**建议(Fix B)**:
1. 在 `_claim_verdict` 里:**只有"找到同期间的数、且明显不符"才判 `contradicted`**;
   "没找到对应期间的数" → 判 `insufficient` / 需人工复核,**绝不判矛盾**(止住"真话被判假")。
2. atomic 的数字核对要**按声明期间对齐**(年度声明比年度值、季度声明比季度值),复用 Fix A 的期间标注。
3. 稳定 `decompose_claims` 的类型判定(减少 LLM 抖动导致的 `not_applicable`)。

---

## 我们是怎么发现的(评估方法)

- benchmark:`evaluation/claims_news.json`(113 条 Yahoo 真实语句)+ `evaluation/claims.json`(100 条 SEC 锚定)。
- 脚本:`evaluation/eval_news.py`(实体/分类/路由)、`evaluation/eval_verdict.py`(读 atomic `verdict` 算准确率)。
- 关键证据:
  - SEC 锚定(简单):准确率 74%,但**真话 0/20**、AUC 0.50。
  - 真实新闻:准确率 36%,**真话 0/50**、AUC 0.345。
  - 对比说明:**用权威源造的题会虚高(74%);真实新闻一上,真实水平(36%)就露馅。**
  - 失败案例:NVDA "$81.62B"(=SEC 81,615M,真)、Apple Q2 "$111.2B"(=SEC 111,184M,真)都被判 contradicted。

## 改了哪些文件 / 怎么复现

- 已改:`src/financial_credibility/data_sources.py`（`sec_company_facts`,Fix A)。
- 建议改:`claim_verification.py` / `derivations.py`（Fix B）、`data_sources.py` 的 FRED 关键词（Bug 2)。
- 复现:
  ```bash
  cd credence_latest
  PYTHONPATH=src python3 evaluation/eval_news.py        # 实体/分类/路由(免费)
  python3 evaluation/eval_verdict.py                     # verdict 准确率(SEC,默认 claims.json)
  CLAIMS_FILE=evaluation/claims_news.json python3 evaluation/eval_verdict.py   # 真实新闻版
  ```

## 修复前 → 修复后(Fix A)  — claims.json(100 条 SEC 锚定),她的 pipeline

| 指标 | 修复前 | 修复后(Fix A) |
|---|---|---|
| 真话被判 **contradicted**(冤枉真话) | **19/20** | **0/20** ✅ |
| 真话最终 verdict | 19 矛盾 + 1 partial | **20 partially_supported** |
| 真假区分 **AUC** | 0.50(=抛硬币) | **0.83** |
| 假话抓出(contradicted) | 74/80 | **79/80** |
| 人工复核精度(被标记的里判错的) | 15/69 | **1/56** |
| 总准确率(supported=可信) | 74% | 79% |

**结论**:Fix A 解决了最严重的问题——**真话不再被判"矛盾"**(19→0),AUC 0.50→0.83,假话抓得更全,
复核标记也更精准。**但真话目前停在 `partially_supported`、未升到 `supported`**:它不再冤枉真话,
但还没"确认"真话。这一步需要 **Fix B**(numeric 在 atomic 路径上对齐期间后,
让"数字匹配 + 逻辑不反对"的真话判为 `supported`),根因在 atomic 路径的证据筛选/verdict 逻辑偏保守。
