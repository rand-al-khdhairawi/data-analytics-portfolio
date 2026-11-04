# Ad Campaign A/B Test Decision Memo

**Recommendation: roll out the ad campaign, and check revenue per conversion before scaling spend.** Users shown the ad converted at 2.55% against 1.79% for the PSA control, a lift of 0.77 percentage points (95% CI 0.60 to 0.94) or 43% relative (CI 30% to 58%), with p < 0.001.

## Result

| Metric | Ad (treatment) | PSA (control) | Difference |
| --- | --- | --- | --- |
| Users | 564,577 | 23,524 |  |
| Conversions | 14,423 | 420 |  |
| Conversion rate | 2.55% | 1.79% | +0.77 pp (CI +0.60 to +0.94) |
| Relative lift |  |  | +43% (CI +30% to +58%) |
| z-test and chi-square p-value |  |  | 1.7e-13 |

## Why the result is credible

The file has 588,101 users with no duplicates or missing values, and the split is exactly 96% to 4%, matching an intended allocation (sample ratio test p = 1.00). Power is above 99.9% for the observed effect, and the smallest lift detectable at 80% power is 0.25 pp, well under the 0.77 pp seen. The control group is small, with only 420 conversions, which is why the confidence interval is wide.

The lift holds up under checks. Dropping the heaviest-exposure 0.1% or 1% of users, who may be bots, gives +0.76 pp and +0.79 pp. A logistic regression that adjusts for ads seen gives an odds ratio of 1.49, and a Mantel-Haenszel test across exposure bands gives 1.48 (both p < 0.001).

## Risks and open points

- **The effect sits with heavy-exposure users.** Users who saw 25 ads or fewer show no measurable lift. The lift is +0.88 pp at 26 to 50 ads, +5.9 pp at 51 to 100 and +5.3 pp at 100 or more, all significant after Holm correction. The group-by-exposure interaction is significant (p = 0.0001).
- **Exposure is not randomized within each group**, so these numbers do not show that more ads cause more conversions.
- **Small imbalances remain.** Day and hour of heaviest exposure differ slightly between groups (Cramér's V 0.02 and 0.013), and median ads seen is 13 versus 12. These are measured after assignment, so they are not a strict randomization check.
- **There is no revenue or cost data.** The result is about conversions only, so return on ad spend is unverified.

## Next steps

1. Compare incremental revenue per converter with ad cost before increasing budget.
2. Run a follow-up test that randomizes ad frequency, to learn whether capping or targeting heavy users pays off.
3. Keep a PSA holdout of about 4% in the rollout to monitor the lift.
