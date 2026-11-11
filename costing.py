# costing.py — one place for the product-costing precision policy (Phase 5B-2)
#
# PRECISION POLICY (used by inventory, sales, treatments and reports)
#   * Money that people see and pay (prices, line totals, payments, report
#     totals) is rounded to 2 decimals (kobo) — ONLY at the final stage.
#   * UNIT COSTS are kept to 6 decimals (NUMERIC(18,6)) so a weighted average
#     such as 120.588235... is not rounded to 120.59 before being multiplied
#     by a quantity. Line COGS = quantity x unit_cost is NOT rounded per line;
#     totals are summed at full precision and rounded once at the end.
#   * QUANTITIES are kept to 3 decimals (NUMERIC(12,3)). A quantity with more
#     decimals is REJECTED rather than silently rounded, so the stock the
#     database stores always equals the quantity used in the cost maths.
#   * No float anywhere: Decimal only.
#
# KNOWN vs UNKNOWN COST
#   * A cost of NULL is unknown. A cost of 0 is a real cost ONLY when the
#     record says so explicitly (cost_known = TRUE). Records written before
#     this phase have cost_known = NULL ("legacy"): a legacy positive cost is
#     trusted (the owner entered it), but a legacy cost of exactly 0 is treated
#     as UNVERIFIED, because the old system could not tell "free" from "never
#     entered". Nothing historical is rewritten to make this so.

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

COST_SCALE = Decimal("0.000001")
MONEY_SCALE = Decimal("0.01")
QTY_SCALE = Decimal("0.001")
_ZERO = Decimal("0")


class CostingError(ValueError):
    pass


def to_decimal(value, field_name="Value"):
    if value is None or value == "":
        raise CostingError(f"{field_name} is required.")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise CostingError(f"{field_name} must be a valid number.")
    if not d.is_finite():
        raise CostingError(f"{field_name} must be a valid number.")
    return d


def quantity(value, field_name="Quantity"):
    """Parse a quantity; reject more than 3 decimal places (never round it)."""
    d = to_decimal(value, field_name)
    if d != d.quantize(QTY_SCALE):
        raise CostingError(f"{field_name} can have at most 3 decimal places.")
    return d.quantize(QTY_SCALE)


def unit_cost(value, field_name="Unit cost"):
    """Parse a unit cost to the stored 6-decimal precision."""
    d = to_decimal(value, field_name)
    return d.quantize(COST_SCALE, rounding=ROUND_HALF_UP)


def money(value):
    """Final-stage currency rounding (kobo)."""
    return Decimal(value).quantize(MONEY_SCALE, rounding=ROUND_HALF_UP)


def weighted_average(stock_before, avg_cost, qty_added, new_unit_cost):
    """Perpetual weighted-average cost after a GENUINE purchase.

        (stock_before x avg_cost + qty_added x new_unit_cost)
        / (stock_before + qty_added)

    Uses the real quantities and costs (never a simple average of two prices).
    If there was no stock to weight against (zero or negative), the new
    cost simply becomes the average. qty_added must be > 0 so the divisor is
    never zero. Returns the cost at 6-decimal precision."""
    if qty_added <= 0:
        raise CostingError("Quantity added must be greater than zero.")
    if stock_before <= 0:
        return new_unit_cost.quantize(COST_SCALE, rounding=ROUND_HALF_UP)
    total_value = stock_before * avg_cost + qty_added * new_unit_cost
    return (total_value / (stock_before + qty_added)).quantize(COST_SCALE, rounding=ROUND_HALF_UP)


# ── SQL fragments: ONE definition of "known cost" for every report ──────────

def known_cost_sql(alias):
    """True when the row's unit_cost is a reliable recorded cost."""
    a = alias
    return f"({a}.unit_cost IS NOT NULL AND ({a}.unit_cost > 0 OR {a}.cost_known IS TRUE))"


def unknown_cost_sql(alias):
    return f"(NOT {known_cost_sql(alias)})"


def snapshot_cost(product_row):
    """The unit cost to lock onto a sale / dispensing line right now:
    the product's current cost basis if it is KNOWN, otherwise None
    (unknown) — never a silent 0."""
    if product_row.get("cost_known") is True:
        return product_row["purchase_price"]
    if product_row.get("cost_known") is None and (product_row.get("purchase_price") or _ZERO) > 0:
        return product_row["purchase_price"]       # legacy positive cost: trusted
    return None
