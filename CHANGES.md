# CHANGES — switch-cn-provincial

This repository is a **fork** of upstream
[switch-model/switch-china-open-model](https://github.com/switch-model/switch-china-open-model),
adapted into a province-focused, scenario-driven medium/long-term power
planning model (Shanghai first, then migratable to other provinces). The fork
preserves upstream history (`vanilla-31province` branch at the upstream tip;
remote `upstream-switch-china` retained for future pulls).

## Why a fork

Upstream SWITCH-China is the canonical 31-province national model. Our research
needs province-focused scenarios (Shanghai → Jiangsu → … with associated
adjacent and UHV-partner zones), a rebuilt time horizon (2020–2060 in 5-year
periods), and a per-scenario directory layout. These changes warrant a
divergent branch we can iterate on without coupling to upstream's release
cadence.

## Divergence from upstream

See [the implementation plan](.claude/plans/switch-china-cosmic-phoenix.md) for
the full architecture decision record and execution roadmap. Summary:

| Area | Upstream | This fork |
|---|---|---|
| Module directory | `china_modules/` | `cn_modules/` (province-agnostic naming) |
| Paper subdirs | `he_et_al_*/`, `peng_et_al_*/`, `zhang_et_al_*/` at root | moved into `papers_archive/` |
| Time horizon | 2023–2052, 6 periods | **planned**: 2020–2060, 9 periods |
| Scenarios | single `inputs/` | `scenarios/<province>/inputs/` per scenario |
| `cn_modules/water_limits.py` | unresolved git merge conflict on filename | fixed: uses `gen_info.csv` (Switch 2.0.8+) |
| External-power (外调电) modeling | endogenous via transmission only | endogenous (default) + optional exogenous/hybrid via `cn_modules/extensions/imported_power.py` (planned) |

## Versioning

Major milestones get annotated git tags:

- `v0.1-shanghai-baseline` — Shanghai scenario first runnable + 2025 calibration passed
- `v0.2-jiangsu-migration` — province-agnostic verified by Jiangsu scenario
- `v0.3-timeline-2020-2060` — base inputs rebuilt to 2020–2060 9-period horizon

## Upstream sync

To pull future upstream improvements:
```bash
git fetch upstream-switch-china
git merge upstream-switch-china/main   # or cherry-pick specific commits
```
