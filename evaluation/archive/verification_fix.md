# 可信度数字核对的修复说明（verification fix）— 同步给组员

> TL;DR：我们补了一套评估，发现工具**分不出真假财务数字**（AUC≈0.5，还输给一个笨办法），
> 定位到 `verify_numeric_claim` 的一个 bug——它"**比年份不比金额**"。修好后，同一套 100 题
> benchmark 上 AUC 从 0.52 → **1.00**，判对率 69% → **100%**。
> 关键结论：**问题不在 AI，在核对逻辑**；写对的确定性规则比硬塞 LLM 更有效。

---

## 1. 我们补了什么（评估）

项目原本缺 rubric 要求的「Evaluation & evidence」。新增 `evaluation/`：

- `build_dataset.py`：从 **SEC EDGAR**（免费、无需 key）抓真实年报数字，自动生成
  **100 句带标签声明** = 20 真 + 80 假，假话分 4 类（每类 20）：
  - `number_big`：金额改 ±50%
  - `number_small`：金额只改 ±4%
  - `wrong_company`：把 B 公司的真实数字安到 A 公司头上
  - `wrong_time`：真实金额，但财年/日期写错
- `run_eval.py`：把每句真上网喂给工具，输出成绩单（AUC、分类抓出率、混淆、与基线对比、失败案例），
  逐条结果存 `results_*.json`。

数据源只用 SEC → **零 key、可一键复现**（rubric 看重的「可复现」直接满足）。

## 2. 发现的 bug（改之前）

原 `verify_numeric_claim` 逻辑：把句子里**所有数字**和证据里**所有数字**都拿出来，
**只要任意一个对上就判 verified**，不比大小、也永远不会判「矛盾」。

因为 SEC 证据几乎不含那个确切大金额、却一定含**年份**，于是它总是靠年份"蒙对"：

```
真句：营收 402,836,000,000 ... 2025  →  matched 2025 with 2025  →  verified
假句：营收 604,254,000,000 ... 2025  →  matched 2025 with 2025  →  verified   ← 一样!
```

→ 真句和它的假孪生兄弟**评级完全相同** → AUC=0.50（纯抛硬币），矛盾检出 0/80。

## 3. 改了哪些文件

| 文件 | 改动 |
|---|---|
| `src/financial_credibility/verification.py` | 重写 `verify_numeric_claim`：**金额必须真匹配**；按声明的**财年**去核对；金额对、年份对才 `verified`；该年份有数据但金额不符则判 **`contradicted`**；年份/日期不再当金额。新增 helper `_money_values`/`_claim_year`/`_period_values`/`_close`。 |
| `src/financial_credibility/data_sources.py` | `sec_company_facts`：原来每个指标只留最近 2 个数、季度/年度混杂。改为**按"财年→金额"清晰列出最近 6 个年度值**，证据里能查到对应年份的真实数字。 |
| `src/financial_credibility/config.py` + `judges.py` | 新增 `OPENAI_BASE_URL` 支持，使 `OpenAIJudge` 可指向任何 OpenAI 兼容地址（OpenAI 官方或 OpenRouter）。 |
| `evaluation/`（新增） | `build_dataset.py`、`run_eval.py` + 结果文件。 |

## 4. 新的核对逻辑（一句话）

> **公司**（按 ticker 检索锁定）+ **金额**（必须匹配，容差 0.5%）+ **财年**（按年份对应核对），
> 三者一致才 `verified`；同财年有数据但金额不符 → `contradicted`；查不到 → `not_found`。

## 5. 结果（before / after，同一套 100 题）

| 指标 | 无AI 修复前 | 有AI 修复前 | 无AI 修复后 | 有AI 修复后 |
|---|---|---|---|---|
| 真假区分 AUC | 0.52 | 0.55 | **1.00** | **1.00** |
| 矛盾检出 | 0/80 | 9/80 | **80/80** | **80/80** |
| 判对率 | 69% | 52% | **100%** | **100%** |
| 笨办法基线 | 80% | 80% | 80% | 80% |

**对"AI 有没有用"的直接回答：**
- 修复前：AI 只比无AI 好一丢丢（AUC 0.52→0.55，多抓 9 个矛盾），但**判对率反而更低**（爱给"中等"含糊评级），且两者都输给笨办法。
- 修复后：**有AI 和无AI 完全一样（都 100%）**——AI 唯一的作用是把真句的置信度从 High 抬到 Very High，**没改变任何一个判断**。
- **结论：在"核对结构化财务数字"这个任务上，AI 没有带来价值；真正解决问题的是修对了那段确定性逻辑。** 这正是 rubric 鼓励的诚实结论（"if the AI component doesn't help, say so"）。
- 言下之意：AI 的价值应放在确定性规则做不到的地方（措辞多变、观点/推理类声明）——这是 v2 该测的。

结果文件：`results_heuristic.json` / `results_ai.json`（修复前·无AI / 有AI）、
`results_heuristic_fixed.json` / `results_ai_fixed.json`（修复后·无AI / 有AI）；
四组对比用 `python3 evaluation/compare.py` 一键生成。

## 6. 怎么复现

```bash
cd finm33200_Project_CredenceAnalytics
python3 evaluation/build_dataset.py      # 从 SEC 重建 100 题数据集
python3 evaluation/run_eval.py           # 跑评估（配了 .env 里的 OPENAI key 则走 AI，否则走无AI）
```
（无 key 时自动用本地 HeuristicJudge；要跑 AI 版，在 `.env` 填 `OPENAI_API_KEY` 等。）

## 7. 已知局限（答辩可能会被问，务必如实说）

- **100% 有水分边界**：benchmark 是**干净、模板化、且真相同源于 SEC**。它证明
  "修复后的核对逻辑是对的"，**不代表真实世界完美**。真实声明措辞多变、可能含多个数字、
  来自新闻/网页、还有观点类——会难很多。
- **AI 没参与这个数字核对**：数字核对在本地完成，所以满分是确定性规则的功劳，不是 LLM 的。
  → 课程结论：在"核对结构化财务数字"这件事上，**确定性规则 > LLM**；AI 的价值应放在
  它擅长的地方（语义/观点/推理）。
- `wrong_time` 的识别依赖 SEC 证据里含该年份的年度值（目前取最近 6 年）；更久远的年份可能漏。
- 数据集目前 20 真 / 80 假不均衡，单看"判对率"会偏高；应以 **AUC + 分类抓出率** 为准。

## 8. 待办（v2，可选）

- 数据集加 **改写/换语序的真句**，测工具是不是只会套模板（鲁棒性）。
- 真假更均衡（如各 50）。
- 补 AI 修复后那一列，确认 AI 是否还能再加一点价值。
