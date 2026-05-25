# Data requirements for the 2020–2060 time horizon

> Populated incrementally during **Phase C** of
> [the plan](../.claude/plans/switch-china-cosmic-phoenix.md). This file lists
> every CSV field that needs fresh data when extending base inputs to 9 periods
> (2020/2025/2030/2035/2040/2045/2050/2055/2060).
>
> Source convention (per plan decision): user provides data sources; tools fill
> values, never fabricate. Costs in **2020 USD** (per decision D-7).

## Status

| File | Field | Periods needing data | Source (you'll fill in) | Filled? |
|---|---|---|---|---|
| _(populated by_ `tools/rebuild_periods.py`_)_ | | | | |

## Source convention

When you provide a data source for a field, append a row above with format:

```
| inputs/<file>.csv | <column> | 2020/2025/.../2060 | <source: doc/url/spreadsheet name> | filled YYYY-MM-DD |
```

Open items get a `—` in the "Filled?" column; mark `✓` once the values are
loaded and `tools/validate_scenario.py` passes.
