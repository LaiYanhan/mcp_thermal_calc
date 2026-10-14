# 工业熔盐储热与热工选型测算系统 (MCP Thermal Calculation & Sizing Engine)

为企业构建的确定性工程热工计算、离散设备规格选型与经济性测算 MCP 工具服务与 Agent 技能体系。

## 🌟 系统核心特性与架构原则
1. **AI 严禁私自计算（100% 确定性程序执行）**：所有热工物性（IAPWS-IF97）、能量守恒、设备选型与电费测算完全由 Python 核心计算，彻底杜绝大模型计算幻觉；
2. **分阶段状态机与人工确认强守卫**：在 MCP 工具层内置状态机，必须经历“场景确认 $\rightarrow$ 参数缺项补全 $\rightarrow$ 参数审核确认 $\rightarrow$ 授权计算”，未经授权调用计算将被直接物理拦截；
3. **公式解耦与符号双向推导（SymPy）**：代数公式基于 SymPy 符号方程构建，天然支持正向与逆向多变量推导（如 $a,b \Rightarrow c$ 或由目标 $c$ 逆推所需入参 $a$）；水蒸气状态方程单向查表封装；
4. **统一原子公式化与管道装配（无过度抽象）**：设备选型与阶梯造价规则均抽象为纯净原子公式，在 `pipelines/` 声明式 DAG 管道中与热工物理公式串联一体；
5. **高度可扩展性**：支持通过标准模板为新场景动态注册新公式（存入 `formulas/`）与新计算管道（存入 `pipelines/`）。

---

## 📁 目录结构

```
.
├── GLOSSARY.md               # 领域统一词汇表 (Domain Glossary)
├── docs/adr/                 # 架构决策记录 (ADR 0001 ~ 0005)
├── constants/                # 独立工程常量与默认参数库
│   ├── default_parameters.py # 默认工况参数基准表（含中文释义与单位）
│   ├── molten_salt.py        # HITEC/太阳盐热物性状态方程 (密度/导热/粘度/比热)
│   └── equipment_catalog.py  # SGS/电加热器/国标变压器规格序列与阶梯造价函数
├── core/                     # 核心计算与调度引擎
│   ├── types.py              # Pin/引脚、FormulaMetadata、PipelineStep 等类型定义
│   ├── formula.py            # AlgebraicFormula (SymPy双向)、EmpiricalFormula 与注册表
│   ├── pipeline.py           # Pipeline DAG 拓扑执行引擎与校验
│   └── state_machine.py      # 分阶段状态机与人工确认守卫控制器
├── formulas/                 # 原子公式库 (按业务解耦)
│   ├── thermal/              # 水蒸气物性查表、焓差、SGS功率、储热量、电加热器功率、熔盐量
│   ├── operation/            # 用电量、供汽量、购电成本、售汽收入、日度/年化毛收益差额
│   └── sizing/               # SGS规格整定、电加热器整定、主变压器查表选型、熔盐采购量整定
├── pipelines/                # 场景计算管道库 (声明式 DAG)
│   └── valley_molten_salt_steam.py # 基准场景：谷电熔盐储热供蒸汽完整流水线
├── server/                   # MCP 服务端接口层
│   └── mcp_server.py         # 基于 MCP 2.x SDK 暴露的 10 个工程与工作流工具
├── skills/                   # 智能体交互技能说明书
│   └── thermal-calculation-agent/SKILL.md # 指导大模型执行状态机流程的详细规范
└── tests/                    # 单元与回归测试套件
```

---

## 🚀 启动与使用指南

### 1. 激活虚拟环境
本项目已通过 `uv` 初始化 `.venv` 环境：
```bash
# Windows
.venv\Scripts\activate
```

### 2. 运行自动化测试与数据回归核对
```bash
.venv\Scripts\pytest -v tests/
```

### 3. 启动 MCP 服务
```bash
.venv\Scripts\python server/mcp_server.py
```
可直接配置到 Claude Desktop、Cursor 或企业级 Agent 编排系统中。
