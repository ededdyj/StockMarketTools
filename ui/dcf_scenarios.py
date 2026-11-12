"""Scenario controls anchored to the active single-stock DCF."""

import streamlit as st

from models.valuation import DcfAssumptions, default_scenarios


def _set_scenario_state(scenarios: dict[str, DcfAssumptions]) -> None:
    for name in ("Bear", "Bull"):
        assumptions = scenarios[name]
        for field, value in (
            ("growth", assumptions.growth_rate),
            ("discount", assumptions.discount_rate),
            ("terminal", assumptions.terminal_growth_rate),
        ):
            st.session_state[f"scenario_{name.lower()}_{field}"] = max(-50.0, min(50.0, value * 100))


def get_user_scenario_assumptions(
    base: DcfAssumptions, state_key: str,
) -> dict[str, DcfAssumptions]:
    scenarios = default_scenarios(base)
    signature = (
        state_key, base.discount_rate, base.growth_rate,
        base.terminal_growth_rate, base.projection_years,
    )
    if st.session_state.get("dcf_scenario_signature") != signature:
        _set_scenario_state(scenarios)
        st.session_state["dcf_scenario_signature"] = signature

    with st.expander("Bull / Base / Bear Scenario Assumptions", expanded=False):
        st.caption(
            "Base always matches the active DCF sidebar assumptions. Bear and Bull use the same "
            "starting FCF, net debt, shares, and projection years. Their rates reset to defaults "
            "when the ticker or active assumptions change."
        )
        st.write(
            f"Base (active DCF): growth {base.growth_rate:.2%}, discount {base.discount_rate:.2%}, "
            f"terminal growth {base.terminal_growth_rate:.2%}, {base.projection_years} years."
        )
        if st.button("Reset Bear/Bull to active defaults", key="dcf_scenario_reset"):
            _set_scenario_state(scenarios)
        for name in ("Bear", "Bull"):
            cols = st.columns(3)
            values = {}
            for col, (field, label) in zip(cols, (
                ("growth", "Growth"), ("discount", "Discount"), ("terminal", "Terminal"),
            )):
                with col:
                    values[field] = st.number_input(
                        f"{name} {label} (%)", min_value=-50.0, max_value=50.0,
                        format="%.2f", key=f"scenario_{name.lower()}_{field}",
                    ) / 100.0
            scenarios[name] = DcfAssumptions(
                discount_rate=values["discount"], growth_rate=values["growth"],
                terminal_growth_rate=values["terminal"], projection_years=base.projection_years,
            )
    return scenarios
