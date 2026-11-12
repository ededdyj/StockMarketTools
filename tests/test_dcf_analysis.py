from dataclasses import replace

import pandas as pd
import pytest

from models.valuation import DcfAssumptions, calculate_dcf_analysis, default_scenarios


PLTR_ASSUMPTIONS = DcfAssumptions(0.12926656898675665, 0.12, 0.03, 5)
PLTR_INPUTS = dict(
    starting_fcf=4_053_956_000, net_debt=-10_336_264_000,
    shares_outstanding=2_573_926_000, current_price=171.64,
    assumptions=PLTR_ASSUMPTIONS,
)


def test_pltr_headline_base_and_sensitivity_reconcile_despite_old_base_override():
    stale = default_scenarios(DcfAssumptions(0.1026, 0.0539, 0.03, 7))
    analysis = calculate_dcf_analysis(**PLTR_INPUTS, scenario_assumptions=stale)
    base = next(case for case in analysis.scenarios if case.name == "Base")
    center = analysis.sensitivity.loc[
        analysis.sensitivity["Terminal Growth"] == PLTR_ASSUMPTIONS.terminal_growth_rate,
        PLTR_ASSUMPTIONS.discount_rate,
    ].iloc[0]

    assert analysis.valuation.fair_value_per_share == pytest.approx(27.38189447923665)
    assert base.assumptions == PLTR_ASSUMPTIONS
    assert base.valuation == analysis.valuation
    assert center == pytest.approx(analysis.valuation.fair_value_per_share)
    assert analysis.fair_value_range[0] <= center <= analysis.fair_value_range[1]
    for case in analysis.scenarios:
        assert case.valuation.starting_fcf == PLTR_INPUTS["starting_fcf"]
        assert case.valuation.net_debt == PLTR_INPUTS["net_debt"]
        assert case.valuation.shares_used == PLTR_INPUTS["shares_outstanding"]
        assert case.assumptions.projection_years == PLTR_ASSUMPTIONS.projection_years


def test_reverse_dcf_round_trips_active_growth_and_horizon():
    assumptions = replace(PLTR_ASSUMPTIONS, discount_rate=0.11, growth_rate=0.08, projection_years=8)
    analysis = calculate_dcf_analysis(**{**PLTR_INPUTS, "assumptions": assumptions})
    round_trip = calculate_dcf_analysis(**{
        **PLTR_INPUTS, "assumptions": assumptions,
        "current_price": analysis.valuation.fair_value_per_share,
    })
    assert round_trip.reverse_dcf.valid
    assert round_trip.reverse_dcf.implied_growth_rate == pytest.approx(assumptions.growth_rate)
    assert "8 years" in round_trip.reverse_dcf.message


def test_analysis_copies_active_assumptions_instead_of_retaining_mutable_input():
    assumptions = replace(PLTR_ASSUMPTIONS)
    analysis = calculate_dcf_analysis(**{**PLTR_INPUTS, "assumptions": assumptions})
    assumptions.growth_rate = 0.01
    assert analysis.assumptions.growth_rate == 0.12
    assert analysis.scenarios[1].assumptions.growth_rate == 0.12


@pytest.mark.parametrize("changes", [
    {"starting_fcf": None},
    {"assumptions": DcfAssumptions(0.02, 0.03, 0.03, 5)},
])
def test_analysis_handles_missing_or_invalid_inputs(changes):
    analysis = calculate_dcf_analysis(**{**PLTR_INPUTS, **changes})
    assert analysis.valuation is None
    assert analysis.fair_value_range is None
    assert not analysis.scenarios
    assert analysis.sensitivity.empty
    assert not analysis.reverse_dcf.valid


def test_analysis_keeps_enterprise_output_when_shares_are_unavailable():
    analysis = calculate_dcf_analysis(**{**PLTR_INPUTS, "shares_outstanding": None})
    assert analysis.valuation.enterprise_value is not None
    assert analysis.valuation.fair_value_per_share is None
    assert pd.isna(analysis.sensitivity.iloc[2, 3])
    assert not analysis.reverse_dcf.valid


def test_valid_active_cell_is_shown_even_when_terminal_spread_is_small():
    assumptions = DcfAssumptions(0.031, 0.03, 0.03, 5)
    analysis = calculate_dcf_analysis(**{**PLTR_INPUTS, "assumptions": assumptions})
    center = analysis.sensitivity.loc[
        analysis.sensitivity["Terminal Growth"] == 0.03, 0.031,
    ].iloc[0]
    assert center == pytest.approx(analysis.valuation.fair_value_per_share)
