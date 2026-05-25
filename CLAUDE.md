# CLAUDE.md — switch-cn-provincial(SWITCH-China fork)

> 本文件由 Claude Code 在每次会话自动读取。本仓库是
> [switch-model/switch-china-open-model](https://github.com/switch-model/switch-china-open-model)
> 的 fork,改造成省级电力规划/预测模型(基年 2020,规划到 2060,上海首发,可迁移)。

---

## 项目性质(最重要,先读这一段)

这是一个**基于 SWITCH-China 框架开发的省级电力规划/预测模型**(fork + 改造,
不是从零开发,也不是直接跑上游 baseline)。

- 角色:**使用者 + 场景设计者 + 局部扩展者**(写新 china 扩展模块、写场景切片工具、
  装填新数据;**不轻易动 switch_model 核心**)
- 上游 SWITCH 主框架 `switch_model` 通过 pip 安装,在 `/Users/meichengcheng/miniforge3/envs/switch/lib/python3.10/site-packages/switch_model/` —— **不要改它**
- 本仓库的 `cn_modules/` 是中国扩展模块(由上游 `china_modules/` 改名,见 CHANGES.md)
- 改动模型公式、约束、数据结构前,**先用 Plan Mode 给出计划等批准**

## 实施计划(主线)

**请参考 [.claude/plans/switch-china-cosmic-phoenix.md](.claude/plans/switch-china-cosmic-phoenix.md)
中的完整 6-Phase 实施计划。** 关键决定已固化(D-1 ~ D-8 见 plan)。当前进度见 `CHANGES.md`。

执行节奏:Phase A(仓库重构 + Github)→ Phase C(时间轴 2020-2060) → Phase B(切片工具)
→ Phase E(上海首跑 + 2025 校对) → (暂停) → Phase F(江苏迁移验证)。

## 仓库结构

```
.
├── inputs/               # 通用 base data layer(可更新,所有更新走 git commit)
├── scenarios/<province>/ # 每个省一个 scenario;由 tools/build_scenario.py 切片生成
│   ├── scenario.yaml     # 单一配置文件
│   ├── inputs/           # 生成,不手工编辑
│   ├── outputs/          # .gitignore
│   ├── logs/             # .gitignore
│   └── results_archive/  # 选择性 commit 关键结果
├── cn_modules/           # 中国扩展模块(原 china_modules/ 改名)
│   ├── tech_plans.py
│   ├── water_limits.py
│   ├── mixed_strategy.py
│   ├── re_connected_strategy.py
│   └── extensions/       # 新增本 fork 的扩展(imported_power.py 等)
├── tools/                # 工作流脚本(build_scenario, rebuild_periods, ...)
├── docs/                 # data_requirements.md + results_calibration.md
├── papers_archive/       # 原 he_et_al_* / peng_et_al_* / zhang_et_al_* 归档
├── database/             # 上游原数据(发电厂/输电线/负荷预测的原始源)
├── CHANGES.md            # fork 分叉记录 + 版本里程碑
└── CLAUDE.md             # 本文件
```

## 技术栈

- **Python 3.10**(conda env `switch`,Miniforge 安装)
- **switch_model 2.0.9.post0**(pip 装,不在 conda-forge 上)+ **Pyomo 6.9.1**
- **求解器**:**HiGHS via `appsi_highs` 接口(highspy 1.14.0)**;首选模式 **IPM + `run_crossover=off`**(对省级大 LP 比 dual simplex 快一个量级)
- **依赖**:`setuptools<81`(switch_model 用 `pkg_resources`,新版 setuptools 已移除)
- **未来**:正式大场景可申请 Gurobi 学术 license,只需改 `--solver gurobi`

## 工作环境

- 编辑器:VS Code + Claude Code 扩展(macOS)
- **以 VS Code 集成终端为主**:`conda activate switch` 后跑 `switch solve` 等命令
- **改动走图形 diff 审阅**:每次修改我会做最小颗粒,小步 commit,便于 review 后 accept
- **Git workflow**:
  - `main` 是主线;`vanilla-31province` 是上游 baseline 备份分支
  - `upstream-switch-china` remote 保留,可拉上游更新
  - 远端 `origin` 是用户自己的 GitHub `switch-cn-provincial`(待配)
  - 重要里程碑打 annotated tag(`v0.1-shanghai-baseline` 等)

## 研究目标(指导所有改动)

省级电力系统规划/预测,核心关注:
1. **省级分辨率**:首发上海 5-6 zone(上海 + 华东四省一市:江苏/浙江/安徽/福建 + 四川 UHV)
2. **省间互济 + 外调电**:既包括华东电网内四省一市相互交换,也包括西电东送类长距离送受电
3. **灵活性内生**:储能、调峰、需求响应、省间互济相互竞争(SWITCH 默认提供基础;后续精细化)
4. **中长期演化**:基年 2020 → 2060 共 9 期 5 年一期(Phase C 重做时间轴)
5. **省份可迁移**:同一套代码后续要能跑江苏/山东/新疆/内蒙古等省,**仅换 scenario.yaml**

## 数据来源策略(重要)

- **base 数据由用户提供数据源**,我不伪造数值
- 流程:我列字段清单(`docs/data_requirements.md`)→ 用户提供数据或告诉我从哪里获取 →
  我转 SWITCH schema 写入 → commit + validate
- 成本数据基准:**2020 USD**(决定 D-7)
- 校对数据:用户提供 **2025 年上海实测数据** 作为模型 2025 期输出校对锚点

## 工作规范

- **先理解,再动手**:面对陌生代码先解释再提议改动
- **复杂任务用 Plan Mode**:改场景/动公式/调数据结构前先出计划
- **每次只改一处,可追溯**:小颗粒 commit,便于 review 和回滚
- **环境/依赖问题主动诊断**:Pyomo + 求解器版本、license、求解器找不到等,系统排查再改
- **解释优化模型报错**:infeasible / unbounded / 超时,先定位是数据/约束/规模问题
- **保护数据和代码**:删除/覆盖原始数据前先告知;**重要改动前提醒 commit**
- **中文交流**:回答用中文,代码注释中英皆可

## 安全提醒

- Git 管理 + 经常 commit + push GitHub;批量/不可逆命令前确认
- 不无脑通过所有权限请求,逐项审阅
- `inputs/` 是 base data,改动会影响所有 scenarios → 改前先确认 + commit + 重 build 验证
- `database/` 是上游原数据,**不修改**,只引用
