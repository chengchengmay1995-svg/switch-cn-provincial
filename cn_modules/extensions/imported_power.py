# cn_modules.extensions.imported_power
#
# Phase D Option 2 — Exogenous imported power as input time series with
# per-period contract prices.  Use this to represent long-distance UHV
# inflows whose sending province is NOT modeled as a SWITCH load_zone
# (e.g. Xinjiang → Anhui via Jiquan ±1100kV, Ningxia → Zhejiang via
# Lingshao ±800kV — both physically real but their senders fall outside
# the 6-zone Shanghai scenario).
#
# Concept:
# - Each `IMPORT_PARTNER` is a label (e.g. "Jiquan", "Lingshao").
# - It delivers `imported_power_mw[partner, tp]` MW into a receiving
#   `LOAD_ZONE` (modeled), at a contract price `imported_power_price_per_mwh
#   [partner, period]` US$/MWh.
# - The MW value is treated as a PARAMETER (fixed); a future v2 may
#   promote it to a `Var` bounded by `imported_power_mw_max` so the model
#   can refuse cheap-but-unwanted imports (plan decision D-6 said use Var,
#   deferred to v2 for simplicity).
#
# Inputs (all optional — module is a no-op if file is absent / empty):
#   imported_power_zones.csv       partner_zone, destination_load_zone
#   imported_power.csv             partner_zone, timepoint, imported_power_mw
#   imported_power_prices.csv      partner_zone, period, imported_power_price_per_mwh
#
# Effects on the model:
# - Adds positive injection to `Zone_Power_Injections` in receiving zone.
# - Adds a per-timepoint cost to `Cost_Components_Per_TP`.

import os

from pyomo.environ import (
    NonNegativeReals,
    Param,
    Set,
    Expression,
)

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
)


def define_components(mod):
    mod.IMPORT_PARTNERS = Set(dimen=1)

    mod.import_partner_zone = Param(
        mod.IMPORT_PARTNERS,
        within=mod.LOAD_ZONES,
        doc="Destination LOAD_ZONE receiving this exogenous import.",
    )

    mod.IMPORT_PARTNER_TPS = Set(
        dimen=2,
        initialize=lambda m: m.IMPORT_PARTNERS * m.TIMEPOINTS,
    )
    mod.imported_power_mw = Param(
        mod.IMPORT_PARTNER_TPS,
        within=NonNegativeReals,
        default=0.0,
        doc="MW delivered by partner at timepoint (fixed; see module docstring).",
    )

    mod.IMPORT_PARTNER_PERIODS = Set(
        dimen=2,
        initialize=lambda m: m.IMPORT_PARTNERS * m.PERIODS,
    )
    mod.imported_power_price_per_mwh = Param(
        mod.IMPORT_PARTNER_PERIODS,
        within=NonNegativeReals,
        default=0.0,
        doc="US$/MWh contract price for partner's import in this period.",
    )

    # Power-balance injection (one expression per zone × timepoint)
    def _imp_inject_rule(m, z, tp):
        return sum(
            m.imported_power_mw[p, tp]
            for p in m.IMPORT_PARTNERS
            if m.import_partner_zone[p] == z
        )

    mod.ImportedPowerInjection = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS, rule=_imp_inject_rule,
    )
    mod.Zone_Power_Injections.append("ImportedPowerInjection")

    # Per-timepoint cost (added to objective via Cost_Components_Per_TP)
    def _imp_cost_tp_rule(m, tp):
        p = m.tp_period[tp]
        return sum(
            m.imported_power_mw[ip, tp]
            * m.imported_power_price_per_mwh[ip, p]
            for ip in m.IMPORT_PARTNERS
        )

    mod.ImportedPowerCostPerTP = Expression(
        mod.TIMEPOINTS, rule=_imp_cost_tp_rule,
    )
    mod.Cost_Components_Per_TP.append("ImportedPowerCostPerTP")


def load_inputs(mod, switch_data, inputs_dir):
    """
    imported_power_zones.csv      partner_zone destination_load_zone
    imported_power.csv            partner_zone timepoint imported_power_mw
    imported_power_prices.csv     partner_zone period imported_power_price_per_mwh

    All optional.  If no files / empty, the module is a no-op
    (IMPORT_PARTNERS is empty, all expressions evaluate to 0).
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "imported_power_zones.csv"),
        optional=True,
        index=mod.IMPORT_PARTNERS,
        param=(mod.import_partner_zone,),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "imported_power.csv"),
        optional=True,
        param=(mod.imported_power_mw,),
    )
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "imported_power_prices.csv"),
        optional=True,
        param=(mod.imported_power_price_per_mwh,),
    )
