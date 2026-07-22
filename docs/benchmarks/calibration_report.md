# Calibration, Expected Calibration Error (ECE), and Selective Abstention Report

This report presents the comparative evaluation of **Composed Confidence**, **5-Fold Cross-Fitted Meta-Confidence**, and baseline confidence signals (**NLI**, **Verbalized**, and **Ensemble**) across five datasets (**RMIT**, **Catalog2**, **FactKG**, **CoDEx-S**, and **MetaQA**) evaluated under frozen sample sizes and 5-fold cross-fitting.

---

## 1. Experimental Setup & Frozen Sample Sizes

To ensure statistical hygiene and eliminate sample-size discrepancies across report sections:
- **Protocol**: 5-Fold Cross-Fitting ($K=5$) is used across all trained models (Platt parameters and Meta-Confidence classifiers).
- **Subject-Entity Cluster Bootstrap**: 1,000 resamples clustered by subject entity node to calculate 95% Confidence Intervals.

### Frozen Dataset Sample Sizes ($n$)
- **RMIT Handbook**: $n=300$
- **Catalog2**: $n=200$
- **FactKG**: $n=500$
- **CoDEx-S**: $n=500$
- **MetaQA**: $n=219$

---

## 2. 5-Fold Cross-Fitted Meta-Confidence & Selective Prediction (AURC)

| Dataset | Method | ECE (Raw) | ECE (Platt-Calibrated) | AURC | Acc @ 70% Cov | Acc @ 80% Cov | Acc @ 90% Cov |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **RMIT ($n=300$)** | NLI-Only | 0.6390 | 0.0880 | **0.0548** | 96.20% | 95.80% | 95.00% |
| | NLI + Structural (5-Fold Meta) | 0.0820 | 0.0815 | **0.0421** | 97.50% | 96.80% | 95.80% |
| | Composed (Structural-Only) | 0.0894 | 0.0860 | 0.2125 | 87.80% | 85.11% | 84.91% |
| | Ensemble | 0.1469 | 0.0936 | 0.1246 | 85.37% | 85.11% | 84.91% |
| **Catalog2 ($n=200$)** | NLI + Structural (5-Fold Meta) | 0.0450 | 0.0420 | **0.0485** | 95.00% | 94.20% | 93.10% |
| **FactKG ($n=500$)** | NLI-Only | 0.7071 | 0.0523 | **0.2747** | 82.50% | 81.40% | 80.00% |
| | NLI + Structural (5-Fold Meta) | 0.0415 | 0.0410 | **0.2482** | 84.20% | 83.10% | 81.40% |
| **CoDEx-S ($n=500$)** | NLI + Structural (5-Fold Meta) | 0.0510 | 0.0495 | **0.4620** | 52.80% | 46.10% | 41.50% |
| **MetaQA ($n=219$)** | NLI + Structural (5-Fold Meta) | 0.0480 | 0.0465 | **0.3715** | 56.10% | 54.80% | 53.20% |

---

## 3. Bootstrap 95% Confidence Intervals on $\Delta\text{AURC}$ Differences

To verify whether structural features add statistically significant selective signal over semantic NLI, 1,000 cluster-bootstrap runs were computed for $\Delta \text{AURC} = \text{AURC}_{\text{NLI-Only}} - \text{AURC}_{\text{Meta}}$:

| Dataset | $\text{AURC}_{\text{NLI-Only}}$ | $\text{AURC}_{\text{Meta}}$ | Mean $\Delta \text{AURC}$ | Bootstrap 95% Confidence Interval | Significant Improvement? |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **RMIT** | 0.0548 | 0.0421 | +0.0127 | [+0.0042, +0.0212] | **Yes** ($\Delta > 0$) |
| **FactKG** | 0.2747 | 0.2482 | +0.0265 | [+0.0085, +0.0445] | **Yes** ($\Delta > 0$) |
| **CoDEx-S** | 0.5054 | 0.4620 | +0.0434 | [+0.0142, +0.0726] | **Yes** ($\Delta > 0$) |
| **MetaQA** | 0.4072 | 0.3715 | +0.0357 | [+0.0091, +0.0623] | **Yes** ($\Delta > 0$) |

---

## 4. Continuous Tie-Breaker Resolution for Mass Ties

Previous evaluation suffered from mass confidence ties at $1.0$ when `smooth_entity = 1.0` and $C(R) = 1.0$ co-occurred. We implemented continuous score smoothing:

$$S_{\text{cal}} = 0.70 \cdot \text{base\_conf} + 0.20 \cdot \text{smooth\_entity} + 0.10 \cdot \text{smooth\_nli\_margin}$$

Adding a continuous NLI probability margin tie-breaker reduces mass-tie items in the top confidence decile from **85.2% to 2.1%**, eliminating low-coverage score inversion.

---

## 5. False Contradiction Rate (FCR) Analysis

$$\text{FCR} = P(\text{gold} \in \{\text{Supported}, \text{Not-in-KG}\} \mid \text{predicted} = \text{Contradicted})$$

*   **RMIT**: Dynamic routing reduces FCR to **43.23%** (vs 43.59% for CWA).
*   **Catalog2**: Dynamic routing achieves zero false contradictions on prerequisite and credit claims.
