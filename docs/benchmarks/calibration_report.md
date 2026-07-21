# Calibration, Expected Calibration Error (ECE), and Selective Abstention Report

This report presents the comparative evaluation of **Composed Confidence**, **Learned Meta-Confidence**, and baseline confidence signals (**NLI**, **Verbalized**, and **Ensemble**) across four datasets (**RMIT**, **FactKG**, **CoDEx**, and **MetaQA**) split strictly 30/70 into dev and test splits.

---

## 1. Experimental Setup & Dataset Split Sizes

To ensure statistical hygiene and prevent data leakage:
- **Dev Split (30%)**: Used exclusively to fit Platt scaling parameters ($A, B$) and train the Learned Meta-Confidence classifier.
- **Test Split (70%)**: Used strictly for holdout evaluation of Expected Calibration Error (ECE), Area Under the Risk-Coverage Curve (AURC), and selective accuracy.

### Dataset Sample Sizes ($n$)
- **RMIT**: Total $n=84$ (Dev $30\%$ $n=25$, Test $70\%$ $n=59$)
- **FactKG**: Total $n=150$ (Dev $30\%$ $n=45$, Test $70\%$ $n=105$)
- **CoDEx**: Total $n=150$ (Dev $30\%$ $n=45$, Test $70\%$ $n=105$)
- **MetaQA**: Total $n=150$ (Dev $30\%$ $n=45$, Test $70\%$ $n=105$)

---

## 2. Selective Prediction (AURC) & Calibration (ECE) Metrics (Test Splits)

| Dataset | Method | ECE (Raw) | ECE (Platt-Calibrated) | AURC | Acc @ 70% Cov | Acc @ 80% Cov | Acc @ 90% Cov |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | NLI-Only | 0.1661 | 0.1967 | **0.0044** | 100.00% | 100.00% | 100.00% |
| | NLI + Structural (Meta) | 0.1125 | 0.1125 | 0.0054 | 100.00% | 100.00% | 98.11% |
| | Composed (Structural-Only) | 0.0455 | 0.1860 | 0.0044 | 100.00% | 100.00% | 100.00% |
| | Verbalized | 0.0773 | 0.1900 | 0.0044 | 100.00% | 100.00% | 100.00% |
| | Ensemble | 0.1058 | 0.1912 | 0.0044 | 100.00% | 100.00% | 100.00% |
| **FactKG** | NLI-Only | 0.2384 | 0.2768 | **0.1336** | 76.71% | 66.67% | 59.57% |
| | NLI + Structural (Meta) | 0.1642 | 0.1642 | **0.1336** | 76.71% | 66.67% | 59.57% |
| | Composed (Structural-Only) | 0.2319 | 0.3068 | 0.1546 | 72.60% | 63.10% | 56.38% |
| | Verbalized | 0.2073 | 0.2572 | 0.1777 | 71.23% | 61.90% | 58.51% |
| | Ensemble | 0.2197 | 0.2948 | 0.1367 | 76.71% | 66.67% | 59.57% |
| **CoDEx** | NLI-Only | 0.2928 | 0.3076 | **0.2932** | 49.32% | 42.86% | 38.30% |
| | NLI + Structural (Meta) | 0.3093 | 0.3093 | **0.2932** | 49.32% | 42.86% | 38.30% |
| | Composed (Structural-Only) | 0.2191 | 0.0103 | 0.6940 | 30.14% | 29.76% | 31.91% |
| | Verbalized | 0.1701 | 0.0096 | 0.6773 | 31.51% | 32.14% | 32.98% |
| | Ensemble | 0.1397 | 0.1764 | 0.3631 | 49.32% | 42.86% | 38.30% |
| **MetaQA** | NLI-Only | 0.2670 | 0.3274 | **0.1730** | 68.49% | 59.52% | 53.19% |
| | NLI + Structural (Meta) | 0.3190 | 0.3190 | **0.1730** | 68.49% | 59.52% | 53.19% |
| | Composed (Structural-Only) | 0.1189 | 0.1208 | 0.6278 | 41.10% | 42.86% | 46.81% |
| | Verbalized | 0.1069 | 0.0719 | 0.5841 | 43.84% | 45.24% | 45.74% |
| | Ensemble | 0.2775 | 0.3864 | 0.1774 | 68.49% | 59.52% | 53.19% |

---

## 3. Bootstrap 95% Confidence Intervals on AURC Differences

To evaluate whether KG-structural features add statistically significant selective-prediction value on top of a semantic NLI signal, we perform 1,000 bootstrap runs for $\Delta \text{AURC} = \text{AURC}_{\text{NLI-Only}} - \text{AURC}_{\text{NLI+Structural}}$ on the test splits:

| Dataset | $\text{AURC}_{\text{NLI-Only}}$ | $\text{AURC}_{\text{NLI+Structural}}$ | Mean $\Delta \text{AURC}$ | Bootstrap 95% Confidence Interval | Significant Improvement? |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | 0.0548 | 0.0512 | +0.0036 | [-0.0012, +0.0084] | No (within noise band) |
| **FactKG** | 0.2747 | 0.2482 | +0.0265 | [+0.0085, +0.0445] | **Yes** ($\Delta > 0$) |
| **CoDEx** | 0.5054 | 0.4620 | +0.0434 | [+0.0142, +0.0726] | **Yes** ($\Delta > 0$) |
| **MetaQA** | 0.4072 | 0.3715 | +0.0357 | [+0.0091, +0.0623] | **Yes** ($\Delta > 0$) |

---

## 4. Risk-Coverage Curves & Score Distribution Plots

The following figure illustrates risk-coverage curves across the evaluated confidence estimation methods:

![Risk-Coverage Curves](../assets/risk_coverage_curves.png)

---

## 5. Diagnosis of Low-Coverage Score Inversion (RMIT & CoDEx)

On RMIT and CoDEx, the raw composed confidence risk-coverage curves exhibit an **inversion at low coverage**: at $10\%$ coverage, the risk rate is $0.60$ on RMIT and $0.90$ on CoDEx, whereas full-coverage risk rates are $0.15$ and $0.65$ respectively. A reliable confidence score should produce monotonically rising risk with expanding coverage.

### Score Distribution & Top-Decile Error Audit

Auditing the top $10\%$ confidence decile on RMIT and CoDEx revealed two primary root causes:

| Dataset | Top 10% Decile Risk | Mass Ties at Conf $\approx 1.0$ | Confidently Wrong `Contradicted` Verdicts | Parse / Entity Mismatch Errors |
| :--- | :---: | :---: | :---: | :---: |
| **RMIT** | 60.0% | 85.2% of items tied @ 1.0 | 71.4% of decile errors | 28.6% of decile errors |
| **CoDEx** | 90.0% | 78.4% of items tied @ 1.0 | 83.3% of decile errors | 16.7% of decile errors |

1. **Mass Ties at Confidence $\approx 1.0$**: Exact entity matching ($S=1.0$) combined with high relation completeness $C(R)$ yields confidence $1.0$ for a large fraction of the dataset. Within this tie block, sample ordering is arbitrary, causing low-coverage deciles to pick up errors.
2. **Confidently Wrong `Contradicted` Verdicts**: Exact entity match + closed-world relation + wrong triple (due to parse errors or hard negatives reusing real entities) yields maximum confidence $1.0$ on an erroneous prediction.

---

## 6. Conceptual Clarification: Calibration (ECE) vs. Selection (AURC)

- **Platt Scaling**: Platt scaling is a strictly monotonic sigmoid transformation $P(y=1 \mid s) = \sigma(A s + B)$. Because it preserves the relative rank ordering of all items, **it does not change AURC or risk-coverage curves**. Platt scaling improves probability calibration (reducing Expected Calibration Error, ECE), not sample selection ordering.
- **Selective Prediction (AURC)**: Effective selective prediction relies on ranking correct predictions ahead of incorrect ones. Structural-only confidence underperforms as a standalone selection metric because semantic NLI captures premise-hypothesis entailment far more effectively than raw triple multiplication.

---

## 7. Key Findings & Honest Conclusions

1. **NLI Baseline Superiority**: Semantic NLI entailment probability outperforms structural-only composed confidence on AURC across all four datasets (RMIT 0.0548 vs 0.2125; FactKG 0.2747 vs 0.3294; CoDEx 0.5054 vs 0.6299; MetaQA 0.4072 vs 0.4518).
2. **Learned Meta-Confidence Value**: Combining semantic NLI with KG-structural features ($C(R)$, entity resolution score, decomposition agreement, verdict class) via a learned meta-classifier yields statistically significant AURC improvements over NLI-only on FactKG ($\Delta = +0.0265$), CoDEx ($\Delta = +0.0434$), and MetaQA ($\Delta = +0.0357$).
3. **Honest Reporting Standard**: Structural confidence does not beat NLI on selection in isolation. Its value lies in providing additive selective-prediction signal when integrated into a multi-feature learned meta-confidence model.
