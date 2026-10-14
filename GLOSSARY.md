# 热工与储能选型测算系统 (Thermal Calculation & Sizing System)

面向熔盐储能、工业供汽及多能源耦合场景的确定性热工计算、设备规格整定与经济性初测系统。

## Language

**原子公式 (Atomic Formula)**:
最小粒度的无副作用运算单元，严格绑定物理量纲与变量解释，支持单向查表或符号双向推导。
_Avoid_: 脚本, 函数片段, 计算过程

**计算管道 (Calculation Pipeline)**:
特定工程场景下的声明式有向无环图（DAG），通过变量引脚拓扑连接多个原子公式，由底层引擎执行。
_Avoid_: 批处理, 工作流脚本, 算式链

**SGS (Steam Generation System / 蒸汽发生系统)**:
熔盐与水/蒸汽介质之间的高温高压换热设备组合，用于将储热介质的热量释放产生额定参数蒸汽。
_Avoid_: 锅炉, 发生器, 换热器

**储热介质 (Thermal Storage Medium)**:
存储热能的化学介质（如 HITEC 三元盐、太阳盐二元盐），在特定高低温工作温区内运行。
_Avoid_: 导热油, 蓄热液

**离散选型 (Discrete Equipment Sizing)**:
将理论计算得到的连续物理功率或容量，按照设备制造标准和国标档位向上圆整匹配为商业型号的规则。
_Avoid_: 估算规格, 连续取值

**状态机守卫 (State Machine Guard)**:
在 MCP 调用链路中强制拦截越权操作的阶段控制器，保证场景与参数必须经过人工显式授权。
_Avoid_: 校验器, 权限拦截器

**默认工程基准 (Default Engineering Baseline)**:
集中存放于 `constants/` 的标准化缺省物理与造价参数，在用户未提供时作为初始值供人工核对。
_Avoid_: 硬编码配置, 缺省值

**经营毛利差额 (Operating Gross Spread)**:
特定运行周期内售汽总收入与购电/燃料总成本之间的直接差额，不含折旧、贷款与税费。
_Avoid_: 净利润, 财务净现值, IRR
