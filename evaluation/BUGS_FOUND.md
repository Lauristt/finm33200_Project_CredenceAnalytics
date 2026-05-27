# 评估中发现的 Bug + 修复说明（同步给组员）

> 我用一套**真实新闻 benchmark**（Yahoo Finance 113 条,标好资产类别/claim 类型,事实类的数字/日期做了
> 扰动造假,标签都对 SEC/FRED 核验过）整批跑了我们的 pipeline。结论:**前端(实体提取/分类/路由)基本能用,
> 但"判定(verdict)"环节几乎不确认真话**——50 条真话只确认 1 条。这份文档说清楚:发现了什么、改了哪里、还剩什么没修。

---

## TL;DR

| 阶段 | 表现 | 状态 |
|---|---|---|
| 实体/资产提取 | 规则 80.5% → **+LLM 89.4%** | ✅ 能用(AI 有帮助) |
| claim 类型分类 | 84.5%(纯规则) | ⚠️ 偶尔把事实误判成 forecast/opinion |
| fact-check 路由 | 84.1% | ✅ 修了 FRED 关键词后,"没取到数据"从 ~44% 降到 ~6% |
| **判定 verdict** | **真话确认 1/50,AUC 0.34** | ❌ **两个durable bug,见下** |

改完路由后,"没数据"基本消失,错误压到了**两件事**上:**① 时间错配**(取错时点的值去比 → 真话被判 `contradicted`)
和 **② 全有或全无 / 不肯确认**(取到证据也只给 `partially_supported`)。

50 条真话的失败分布(post-fix,`results_news_routingfix`):
**冤判成假 `contradicted` 18(36%)** · **卡在 `partially_supported` 17(34%)** · 误分类跳过 12(24%) · 确认 1。

---

## Bug 1（核心,建议修）：判定逻辑"全有或全无",取到证据也不肯判 `verified`

**现象**:即使数字对得上,verdict 也停在 `partially_supported`,几乎到不了 `verified`/`supported`。
50 条真话只确认 1 条。最铁的证据是它自己的日志——某条真话上写着
*"All material numeric values in the claim were matched directly in the evidence"*,**却仍返回 `partially_supported`**。

**根因**(`src/financial_credibility/verification.py`,`verify_numeric_claim`):
```python
matches = _fuzzy_numeric_matches(claim_numbers, evidence)
if len(matches) == len(claim_numbers):   # 必须“每一个”实质数字都匹配
    verdict = VERIFIED
elif matches:
    verdict = PARTIALLY_VERIFIED          # 少一个就降级
```
真实新闻一句话常带**官方源装不下的额外数字**。例:*"Nvidia 一季度营收 $81.62B,超预期 $79.18B"* ——
$81.62B 在 SEC 财报里能对上,但**分析师预期 $79.18B 任何官方源都没有**,于是 `len(matches) != len(claim_numbers)`,
真话被降级。这不是"置信度阈值太高"——根本没那道闸,是这条"全有或全无"规则。

**建议**:把硬编码匹配换成 **LLM 推理判 verdict**(让它能判"$81.62B 对上了;$79.18B 是预期、非官方数字" → 确认);
或给"部分匹配"打分,允许核心数字匹配 + 逻辑不反对的 claim 升到 `supported`。

---

## Bug 2（核心,建议修）：时间错配——取了错误时点/期间的值去比

**现象**:真话被判 `contradicted`(把真的说成假的),占真话失败的 36%(18/50)。逐条看,头号机制是时间错配。

两种:
1. **FRED 取最新、无视日期**:*"4 月新增 115,000 非农"*、*"布伦特 ~$105/桶"*、*"铜 $6.11/磅"* → 取的是该序列**最新值**,
   不是 claim 指定那天 → 对不上 → `contradicted`。取数靠 `fred()`(`data_sources.py`)默认 `sort_order=desc, limit=3`。
2. **SEC 期间颗粒度**:同一指标有 Q2/半年/全年等**重叠期间**,挑错了行。例:*"Apple Q2 营收 $111.2B"*(真)被拿去和
   半年 $254.9B 比 → `contradicted`。

**说明(诚实定位)**:我们这个 agent 做的是**判断"当下"是否属实**,所以默认取最新值是**合理的**——
这条只在**带历史日期的陈述**上才算 bug。

**建议(提升泛用性)**:加 **as-of-date 控制**——`fred()` 按 claim 日期查(`observation_start/end`)、按口径查
(`units=pc1` 对应"涨 X%");SEC 按 claim 的财年期间(Q2/半年/全年)挑对应窗口。

**注意:这个 bug 是双向的。** 时间错配不仅把真话冤判成假(36% 的真话),也让少数**假话蒙混过关**:
36 条假话漏掉 6 条,其中 1 条假的 Alphabet 声明被判 `supported`——因为 agent 把它对到了**错的年份**
(截止 2023-12-31 财年 $307.39B)。所以**修好时间对齐能同时改善两个方向**。

---

## 我已经改了什么 / 还剩什么

- **已改**:`routing.py` 的 FRED 关键词/别名映射(consumer prices→CPIAUCSL、payrolls→PAYEMS、oil/WTI→DCOILWTICO、
  s&p 500→SP500、eur/usd→DEXUSEU 等);`data_sources.py` 的 `sec_company_facts` 按报告期间去重(Fix A)。
  → 效果:**"没取到数据"从 ~44% 降到 ~6%**,真话冤判数下降,但**准确率没动(还是 ~36%)**,因为瓶颈转移到了上面的
  Bug 1 / Bug 2。
- **还没改(建议)**:Bug 1(verdict 逻辑换 LLM 推理 / 部分打分)、Bug 2(as-of-date + 期间匹配)。这两个才是现在的天花板。

诚实提醒:Fix A 在**自造题(全年度指标)**上效果很亮(AUC 0.50→0.83),但那是同质化数据放大了单点修复;
在**真实新闻**上几乎不动准确率。**单点修复救不了,得动 verdict 逻辑本身。**

---

## 怎么复现

```bash
cd credence_latest
PYTHONPATH=src python3 evaluation/eval_news.py        # 实体/分类/路由(免费)
python3 evaluation/eval_verdict.py                     # verdict 准确率 -> results_news_verdict.{json,csv}
python3 evaluation/error_analysis.py                   # 失败分类 A–E -> error_analysis_results.csv
```
逐条结果见 `results_news_verdict.csv`;记分卡见 `scorecard_*.txt`。
