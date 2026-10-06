# LightGBM tuning (validation, seed 42)

| setting | best iter | macro-F1 | macro-F1 (reliable) | FPR |
|---|---|---|---|---|
| lr 0.1, min_child_samples 5 (original) | 12 (diverged) | 0.8148 | - | 0.00187 |
| A: lr 0.05, mcs 20, min_child_weight 0.01, L2 1 | 167 | 0.9784 | 0.9905 | 0.00027 |
| B: lr 0.05, mcs 20, min_child_weight 1, L2 1 | 232 | 0.9836 | 0.9907 | 0.00026 |
| C: lr 0.1, mcs 20, min_child_weight 0.01, L2 1, max_delta_step 2 | 96 | **0.9881** | 0.9907 | 0.00026 |

Chosen: C. Differences between A/B/C come mostly from Heartbleed/Infiltration (tiny classes).
