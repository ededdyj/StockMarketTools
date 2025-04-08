import numpy as np


def calculate_fair_value(cashflow_df, shares_outstanding, discount_rate=0.10, growth_rate=0.03,
                         terminal_growth_rate=0.02, projection_years=5):
    """
    Calculates a simplistic fair value using a Discounted Cash Flow (DCF) model.
    Assumes:
      - 'Free Cash Flow' is available in cashflow_df.
      - cashflow_df columns are sorted with the most recent period first.

    Parameters:
      cashflow_df (DataFrame): Cash flow data from yfinance.
      shares_outstanding (int): Number of shares outstanding.
      discount_rate (float): The discount rate (default 10%).
      growth_rate (float): Annual growth rate for free cash flow (default 3%).
      terminal_growth_rate (float): Growth rate after projection period (default 2%).
      projection_years (int): Number of years to project cash flows (default 5).

    Returns:
      fair_value_per_share (float) or None if calculation fails.
    """
    try:
        # Assume the first column holds the most recent data
        recent_period = cashflow_df.columns[0]
        # Extract the free cash flow value; adjust the row key as needed based on yfinance output
        fcf = cashflow_df.loc['Free Cash Flow', recent_period]
    except Exception as e:
        print("Error accessing Free Cash Flow data:", e)
        return None

    # Project future free cash flows
    projected_fcf = [fcf * ((1 + growth_rate) ** i) for i in range(1, projection_years + 1)]

    # Calculate terminal value
    terminal_value = projected_fcf[-1] * (1 + terminal_growth_rate) / (discount_rate - terminal_growth_rate)

    # Discount cash flows to present value
    pv_fcf = sum([cf / ((1 + discount_rate) ** i) for i, cf in enumerate(projected_fcf, start=1)])
    pv_terminal = terminal_value / ((1 + discount_rate) ** projection_years)

    enterprise_value = pv_fcf + pv_terminal
    # For simplicity, assume net debt is zero. Fair value per share is enterprise value divided by shares outstanding.
    fair_value_per_share = enterprise_value / shares_outstanding
    return fair_value_per_share


def calculate_fair_value_range(cashflow_df, shares_outstanding, discount_rate_base=0.10, growth_rate_base=0.03,
                               terminal_growth_rate=0.02, projection_years=5, discount_rate_variation=0.02,
                               growth_rate_variation=0.01):
    """
    Calculate a confidence interval for the fair value per share by varying the discount and growth rates.

    Parameters:
      cashflow_df (DataFrame): Cash flow data.
      shares_outstanding (int): Number of shares outstanding.
      discount_rate_base (float): Base discount rate (default 10%).
      growth_rate_base (float): Base growth rate for free cash flow (default 3%).
      terminal_growth_rate (float): Terminal growth rate (default 2%).
      projection_years (int): Projection period (default 5 years).
      discount_rate_variation (float): Variation for discount rate (default ±2%).
      growth_rate_variation (float): Variation for growth rate (default ±1%).

    Returns:
      (min_fair_value, max_fair_value) tuple if calculations succeed, else None.
    """
    # Define the grid of assumption values
    discount_values = [discount_rate_base - discount_rate_variation, discount_rate_base,
                       discount_rate_base + discount_rate_variation]
    growth_values = [growth_rate_base - growth_rate_variation, growth_rate_base,
                     growth_rate_base + growth_rate_variation]

    fair_values = []
    for d in discount_values:
        for g in growth_values:
            try:
                fv = calculate_fair_value(cashflow_df, shares_outstanding, discount_rate=d, growth_rate=g,
                                          terminal_growth_rate=terminal_growth_rate, projection_years=projection_years)
                if fv is not None:
                    fair_values.append(fv)
            except Exception as e:
                continue

    if not fair_values:
        return None
    return min(fair_values), max(fair_values)

