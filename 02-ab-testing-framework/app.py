"""Streamlit app: explore the A/B test and plan sample sizes. Run: streamlit run app.py
Reads results.json (from run_analysis.py) and uses ab_lib for the calculator."""
import json
import pandas as pd
import streamlit as st
import ab_lib as L

st.set_page_config(page_title="Marketing A/B test", layout="wide")
R = json.load(open("results.json"))
p = R["primary"]

st.title("Ad campaign A/B test")
st.caption("Ad (treatment) vs PSA (control). 588,101 users, conversion as the outcome.")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ad conversion", f"{p['p_treat']:.2%}")
c2.metric("PSA conversion", f"{p['p_ctrl']:.2%}")
c3.metric("Absolute lift", f"{p['diff'] * 100:+.2f} pp", help=f"95% CI {p['diff_ci'][0] * 100:+.2f} to {p['diff_ci'][1] * 100:+.2f}")
c4.metric("Relative lift", f"{p['rel_lift']:+.0%}", help=f"95% CI {p['rel_lift_ci'][0]:+.0%} to {p['rel_lift_ci'][1]:+.0%}")

tab1, tab2, tab3, tab4 = st.tabs(["Checks", "By exposure", "By day and hour", "Sample size calculator"])

with tab1:
    st.subheader("Assignment and data quality")
    st.write(f"Ad share {R['srm']['share_ad']:.4%}. Sample ratio test against the 96/4 design: p = {R['srm']['vs_96_4']['p']:.3f}.")
    st.write(f"Duplicate users: {R['quality']['duplicate_users']}. Missing values: {R['quality']['missing_values']}.")
    b = R["balance"]
    st.write(f"Day balance: Cramér's V {b['day']['cramers_v']:.3f}. Hour balance: Cramér's V {b['hour_block']['cramers_v']:.3f}. "
             f"Ads seen: medians {b['total_ads_mannwhitney']['median_ad']:.0f} vs {b['total_ads_mannwhitney']['median_psa']:.0f}, Mann-Whitney p = {b['total_ads_mannwhitney']['p']:.1e}.")
    st.subheader("Power")
    st.write(f"Observed power {R['power']['observed_power']:.4f}. Minimum detectable lift at 80% power: {R['power']['mde_abs_80'] * 100:.2f} pp.")
    st.subheader("Sensitivity to extreme exposure")
    st.dataframe(pd.DataFrame(R["sensitivity"]).T[["p_treat", "p_ctrl", "diff", "rel_lift", "p_z"]])

with tab2:
    df = pd.DataFrame(R["by_exposure"]).drop(columns=["diff_ci"])
    st.bar_chart(df.set_index("bucket")[["conv_psa", "conv_ad"]])
    st.dataframe(df)
    st.write(f"Mantel-Haenszel odds ratio {R['cmh']['or_mh']:.2f} (p = {R['cmh']['p']:.1e}). Interaction test p = {R['interaction_lr']['p']:.1e}.")

with tab3:
    df = pd.DataFrame(R["segments"]).drop(columns=["diff_ci"])
    st.dataframe(df)

with tab4:
    st.subheader("How many users do you need?")
    base = st.number_input("Baseline conversion rate (%)", 0.1, 50.0, p["p_ctrl"] * 100, 0.1) / 100
    rel = st.slider("Relative lift to detect (%)", 1, 100, 10)
    power = st.slider("Power (%)", 70, 95, 80) / 100
    alpha = st.selectbox("Significance level", [0.05, 0.01, 0.10], index=0)
    n = L.n_per_group(base, base * rel / 100, alpha=alpha, power=power)
    st.metric("Users per group", f"{n:,}")
