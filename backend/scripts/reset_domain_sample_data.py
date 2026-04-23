from datetime import datetime
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import APP_ENV, DB_PATH, IS_DEVELOPMENT
from app.db import db_cursor, init_db


LEGACY_BUSINESS_TAG_CODES = [
    "pest_control",
    "tomato",
    "cucumber",
    "rice",
    "corn",
    "farm_machinery",
]

AI4S_APPLICATION_NAME = "AI4S攻关任务"
COT_PER_SCENE = 100

RESEARCH_MODULES = [
    {
        "key": "target_definition",
        "name": "研究目标与性状边界",
        "focus": "把场景需求转成可执行的目标性状与成功判据",
        "measurements": "核心目标性状、稳定性指标和场景适配指标",
        "deliverable": "目标性状框架与阶段成功标准",
        "upstream": "场景需求、生产问题和科研目标",
        "downstream": "材料筛选与试验设计",
        "risk": "目标定义过宽，导致后续试验无法收敛",
    },
    {
        "key": "germplasm_population",
        "name": "种质资源与群体设计",
        "focus": "构建覆盖关键变异来源的材料体系和群体结构",
        "measurements": "遗传多样性、群体结构、亲缘关系和等位变异覆盖度",
        "deliverable": "核心材料集、训练群体和验证群体",
        "upstream": "研究目标与性状边界",
        "downstream": "表型采集与机制定位",
        "risk": "材料覆盖不足或群体结构偏斜，导致结论不可迁移",
    },
    {
        "key": "phenotyping_sampling",
        "name": "表型体系与采样策略",
        "focus": "建立可重复、可分期、可与机制数据对齐的表型体系",
        "measurements": "关键表型、时期性指标、器官级样本和质量控制指标",
        "deliverable": "标准化表型协议与分期采样方案",
        "upstream": "种质资源与群体设计",
        "downstream": "环境试验与组学采样",
        "risk": "只采终点表型，忽略过程性表型与器官来源差异",
    },
    {
        "key": "gradient_trials",
        "name": "梯度试验与多环境布局",
        "focus": "在密度、生态、病害或管理梯度上识别稳定响应规律",
        "measurements": "梯度响应曲线、G×E 或 G×D×E 交互和重复间一致性",
        "deliverable": "多环境梯度试验网络与响应参数",
        "upstream": "表型体系与采样策略",
        "downstream": "机制解析与预测建模",
        "risk": "把环境差异当噪声处理，导致响应参数失真",
    },
    {
        "key": "omics_mechanism",
        "name": "组学采样与机制解析",
        "focus": "定位与目标性状变化相关的分子层调控线索",
        "measurements": "QTL、eQTL、表达模块、代谢通路和关键候选基因",
        "deliverable": "机制候选列表与可验证的调控假设",
        "upstream": "梯度试验与多环境布局",
        "downstream": "遗传网络与因果链建模",
        "risk": "组学采样时点与表型关键时期错位，导致机制解释漂移",
    },
    {
        "key": "genetic_network",
        "name": "遗传网络与因果链",
        "focus": "从关联信号中提炼可解释的因果路径与调控网络",
        "measurements": "位点效应、单倍型组合、网络中心节点和跨层连边强度",
        "deliverable": "遗传网络图谱与候选因果链",
        "upstream": "组学采样与机制解析",
        "downstream": "预测模型与选择指数",
        "risk": "只保留相关性而不做因果约束，导致网络不可用于决策",
    },
    {
        "key": "predictive_modeling",
        "name": "预测模型与数字孪生",
        "focus": "将材料、表型、环境和机制数据统一到可预测框架中",
        "measurements": "预测准确率、跨环境迁移性、校准误差和可解释性",
        "deliverable": "多模态预测模型与场景数字孪生体",
        "upstream": "遗传网络与因果链",
        "downstream": "选择优化与应用决策",
        "risk": "模型仅在单一场景拟合良好，跨场景即失效",
    },
    {
        "key": "selection_optimization",
        "name": "选择指数与决策优化",
        "focus": "把研究结果转成材料筛选、组合设计或管理优化规则",
        "measurements": "综合选择指数、风险惩罚项、收益稳定性和排序一致性",
        "deliverable": "决策规则、候选清单和优先级排序",
        "upstream": "预测模型与数字孪生",
        "downstream": "独立验证与应用转化",
        "risk": "只看平均表现，不看梯度响应和极端场景风险",
    },
    {
        "key": "validation_deployment",
        "name": "独立验证与应用转化",
        "focus": "验证模型和规则是否能在独立材料与独立场景上成立",
        "measurements": "独立验证精度、转化成功率、成本收益和部署稳定性",
        "deliverable": "验证报告、转化方案和应用建议",
        "upstream": "选择指数与决策优化",
        "downstream": "知识图谱更新与下一轮迭代",
        "risk": "验证数据与训练数据同源，导致转化效果被高估",
    },
    {
        "key": "quality_iteration",
        "name": "质量控制与迭代闭环",
        "focus": "对研究链路进行误差审计、偏差校正和图谱迭代",
        "measurements": "数据缺失、批次偏差、模块一致性和复现实验结果",
        "deliverable": "质控规范、失败模式清单和迭代计划",
        "upstream": "独立验证与应用转化",
        "downstream": "下一轮目标定义与资源配置",
        "risk": "没有把失败模式结构化沉淀，导致同类问题反复出现",
    },
]

REASONING_ACTIONS = [
    {"key": "define_scope", "name": "操作性定义"},
    {"key": "core_hypothesis", "name": "核心假设"},
    {"key": "key_variables", "name": "关键变量"},
    {"key": "experimental_design", "name": "试验设计"},
    {"key": "data_integration", "name": "数据整合"},
    {"key": "decision_threshold", "name": "决策阈值"},
    {"key": "validation_route", "name": "独立验证"},
    {"key": "failure_mode", "name": "失败模式"},
    {"key": "translation_path", "name": "转化路径"},
    {"key": "knowledge_graph", "name": "图谱连接"},
]

if len(RESEARCH_MODULES) * len(REASONING_ACTIONS) != COT_PER_SCENE:
    raise ValueError("research module count and reasoning action count must produce 100 CoT items")

DOMAIN_SCENES = [
    {
        "code": "wild_rice_resource_utilization",
        "slug": "wild_rice",
        "name": "野生稻种质快速评价与利用",
        "owners": ["sunjian"],
        "goal": "利用野生稻资源和数字孪生建模识别主栽品种短板，并形成可导入的改良路径",
        "materials": "野生稻核心种质、主栽水稻品种、导入系和回交群体",
        "primary_traits": "高温结实率、抗逆性、花粉活力、灌浆稳定性和产量稳定性",
        "stress_axis": "高温、干旱、盐胁迫及区域生态梯度",
        "phenotype_data": "多季田间表型、结实率、花粉活力、冠层温度和灌浆动态数据",
        "omics_data": "重测序、转录组、代谢组及候选位点注释数据",
        "modeling_stack": "种质数字孪生、供体匹配模型和导入优先级评分模型",
        "deployment": "野生稻供体筛选、回交导入和区域主栽品种改良决策",
        "success_metric": "在多生态压力下提升主栽品种短板性状且不牺牲区域适应性",
        "key_risk": "把野生稻资源只当静态供体，不建立环境响应函数和导入成本约束",
        "decision_output": "供体优先级、导入位点组合和回交验证顺序",
        "validation_route": "跨生态区导入系验证、关键性状回交群体验证和热胁迫复现实验",
        "knowledge_core": "野生稻资源-关键短板-环境响应-导入改良路径",
        "direct_question": "野生稻资源数字孪生模型在主栽品种短板识别中主要起什么作用？",
        "direct_context": "目标是识别主栽品种在抗逆性和产量稳定性上的短板，并匹配可利用的野生稻资源。",
        "direct_answer": "数字孪生模型应把野生稻资源、主栽品种表型表现和环境响应放在同一评价框架里，先定位主栽品种的关键短板，再按短板强度、导入价值和利用成本筛选最有潜力的野生稻供体。只有把材料、性状和环境联动起来，导入方案才不会停留在经验判断。",
    },
    {
        "code": "soybean_synergy_optimization",
        "slug": "soybean",
        "name": "耐密植、高油、高蛋白协同优化",
        "owners": ["shenyanting", "expert01"],
        "goal": "解析耐密植、高油和高蛋白之间的拮抗与协同，形成动态选育和栽培优化体系",
        "materials": "多生态区大豆核心种质、重组群体、育成品系和密度分层训练群体",
        "primary_traits": "群体适应性、单位面积产量、油分、蛋白含量、油蛋白比和稳定性",
        "stress_axis": "种植密度梯度、区域生态差异和管理措施变化",
        "phenotype_data": "多密度田间试验、株型、结荚性状、产量构成和籽粒品质测定数据",
        "omics_data": "GWAS、QTL、eQTL、转录组、代谢组和基因型标记数据",
        "modeling_stack": "G×D×E 建模、密度分层基因组预测和动态选择指数",
        "deployment": "高油高蛋白兼顾的密植适应型品种选育与区域栽培推荐",
        "success_metric": "跨密度条件下油蛋白平衡稳定，且单位面积生产效益持续提升",
        "key_risk": "把密度效应当噪声处理，导致品系在不同密度下的排序翻转而无法稳定应用",
        "decision_output": "密度分层选材名单、组合优先级和区域密植管理方案",
        "validation_route": "独立密度梯度群体验证、跨区域复现实验和后代群体追踪验证",
        "knowledge_core": "等位变异-密度响应-品质平衡-动态选择指数",
        "direct_question": "耐密植、高油、高蛋白三类目标在大豆选育中为什么容易产生拮抗？",
        "direct_context": "希望在同一套育种与栽培方案中兼顾产量、品质和群体适应性。",
        "direct_answer": "这些目标受不同资源分配路径和生理机制共同控制，高蛋白和高油本身就可能存在负相关，而耐密植又会通过群体光环境和源库关系改变品质表达。因此不能用单一均值去做材料排序，而要按密度梯度和场景收益去重新定义选择目标。",
    },
    {
        "code": "maize_high_protein_feed",
        "slug": "maize_feed",
        "name": "高蛋白饲用玉米综合利用",
        "owners": ["shaoyang"],
        "goal": "构建高蛋白饲用玉米综合性状评价体系，兼顾营养价值、产量和利用稳定性",
        "materials": "高蛋白玉米种质、青贮材料、育成品种和饲用评价群体",
        "primary_traits": "蛋白含量、消化率、赖氨酸水平、青贮品质、产量、抗倒性和收获含水率",
        "stress_axis": "区域气候差异、栽培密度、收获时期和贮藏加工条件",
        "phenotype_data": "产量性状、倒伏、含水率、青贮品质和饲喂表现测定数据",
        "omics_data": "品质相关位点、代谢组、转录组和关键营养通路信息",
        "modeling_stack": "综合性状评价模型、饲用价值预测模型和风险惩罚模型",
        "deployment": "高蛋白饲用玉米材料筛选、饲用利用方案和栽培收获建议",
        "success_metric": "在不显著牺牲产量与稳定性的前提下持续提升综合饲用价值",
        "key_risk": "只追求极端蛋白水平，忽略产量、倒伏和青贮品质带来的系统性风险",
        "decision_output": "综合评分排序、候选饲用品种和利用场景匹配建议",
        "validation_route": "多地点栽培验证、青贮发酵验证和饲喂效应独立验证",
        "knowledge_core": "营养品质-产量稳定-饲用价值-风险控制",
        "direct_question": "高蛋白饲用玉米综合利用场景下，为什么不能只盯着蛋白含量这一项指标？",
        "direct_context": "目标是提升饲用价值，同时避免极端性状带来的生产和营养风险。",
        "direct_answer": "饲用价值是多维度结果，蛋白含量只是其中一个维度，还必须同时考察消化率、赖氨酸、青贮品质、产量和抗倒性。若只追求极高蛋白，往往会把高风险材料推到前面，最终在生产端和利用端都不稳定。",
    },
    {
        "code": "photosynthesis_nitrogen_biomass",
        "slug": "biomass",
        "name": "生物量最大化与养分调控",
        "owners": ["wanghaifeng", "xuyongxin"],
        "goal": "从光合效能、碳氮协同和分时期养分调控出发，提升群体生物量积累与资源利用效率",
        "materials": "高生物量材料、固氮相关材料、不同养分效率品系和分期管理试验群体",
        "primary_traits": "群体生物量、光合效率、根瘤活性、氮素积累、叶片功能持续性和养分利用效率",
        "stress_axis": "生育时期差异、氮素供应梯度、水分条件和群体竞争强度",
        "phenotype_data": "分时期叶面积、叶绿素、根瘤活性、干物质积累和养分吸收动态数据",
        "omics_data": "光合相关转录组、氮代谢通路、代谢组和关键调控基因信息",
        "modeling_stack": "碳氮协同模型、分时期养分调控模型和生物量数字孪生",
        "deployment": "分时期施肥策略、材料筛选和高生物量生产方案优化",
        "success_metric": "在不同生育阶段维持来源与库之间协调，显著提升后期生物量积累",
        "key_risk": "只看前期长势，不分析中后期碳氮失配，导致高生物量目标被早期表象误导",
        "decision_output": "分时期调控方案、高生物量材料排序和管理窗口建议",
        "validation_route": "分时期养分处理复现实验、独立年份验证和器官级动态跟踪验证",
        "knowledge_core": "光合来源-固氮协同-时序养分-生物量积累",
        "direct_question": "光合效能、碳氮协同与分时期养分调控在生物量最大化中是什么关系？",
        "direct_context": "目标是在不同生育时期提高群体生物量积累和养分利用效率。",
        "direct_answer": "光合效能决定碳源形成，固氮和氮同化决定氮源供给，分时期养分调控的作用是把资源投入与各阶段需求对齐。只有三者协同，才能避免前期过旺或后期脱肥，并把生物量提升建立在持续而非短期的生长优势上。",
    },
    {
        "code": "crop_disease_mechanism_control",
        "slug": "disease",
        "name": "病害胁迫下稳产机制",
        "owners": ["mashengwei", "yangzhiquan"],
        "goal": "解析病害与产量形成的互作机制，建立带病条件下的稳产资源评价体系",
        "materials": "抗病资源、稳产资源、多病原处理材料和多点试验群体",
        "primary_traits": "病情进程、减产率、穗粒构成、补偿能力、稳产性和环境适应性",
        "stress_axis": "不同病害压力、病原类型、发病时期和区域环境条件",
        "phenotype_data": "病情指数、产量构成因素、病斑扩展、农艺性状和环境监测数据",
        "omics_data": "抗病相关位点、转录组、代谢组和防御调控网络信息",
        "modeling_stack": "病害-产量互作模型、稳产综合评价模型和病程预测模型",
        "deployment": "带病稳产资源筛选、病害防控决策和稳产品种改良",
        "success_metric": "在真实病害压力下稳定识别既抗病又稳产的材料与策略",
        "key_risk": "只用病斑轻重评价材料，不把产量损失路径和补偿能力纳入同一框架",
        "decision_output": "稳产资源名单、病害管理窗口和抗病改良优先级",
        "validation_route": "多病原复合验证、病害年份复现实验和带病产量独立验证",
        "knowledge_core": "病情进程-产量损失-补偿机制-稳产资源",
        "direct_question": "病害胁迫下稳产机制研究的核心评价目标是什么？",
        "direct_context": "希望在带病条件下筛选稳产资源，并构建可推广的评价体系。",
        "direct_answer": "核心不是单看抗病性，而是在真实病害场景下同时评估病情控制能力、减产幅度和补偿能力。只有把病害过程与产量形成路径连起来，才能找到真正可用于稳产改良和防控决策的资源。",
    },
    {
        "code": "pig_breeding_production",
        "slug": "pig",
        "name": "提高生猪的饲料转化效率",
        "owners": ["lixin"],
        "goal": "整合基因型、表型和环境数据，协同优化生猪选育和精准饲喂以提升饲料转化效率",
        "materials": "不同遗传背景猪群、家系材料、生产群体和精准饲喂试验群",
        "primary_traits": "料肉比、日增重、采食行为、胴体性状、健康表现和环境适应性",
        "stress_axis": "日龄阶段、营养水平、圈舍环境和管理差异",
        "phenotype_data": "个体采食、日增重、健康记录、胴体测定和环境监测数据",
        "omics_data": "基因型、系谱、候选位点和代谢表型信息",
        "modeling_stack": "遗传评估模型、精准饲喂模型和生产效益预测模型",
        "deployment": "高效率家系选择、分阶段饲喂和生产端管理优化",
        "success_metric": "在保证生长和健康的前提下持续降低单位增重饲料消耗",
        "key_risk": "把饲料转化率当作单纯遗传性状，忽略环境和管理条件导致的表达偏移",
        "decision_output": "高效率家系名单、分阶段饲喂配方和圈舍管理建议",
        "validation_route": "独立猪群验证、不同圈舍环境复现和生产端持续跟踪验证",
        "knowledge_core": "遗传潜力-采食行为-环境效应-精准饲喂",
        "direct_question": "提高生猪饲料转化效率时，为什么要同时整合基因型、表型和环境数据？",
        "direct_context": "目标是在选育和生产环节同时提升饲料利用效率。",
        "direct_answer": "饲料转化效率既受遗传背景影响，也深受采食行为、健康状态和圈舍环境调节。只有把基因型、表型和环境放到同一模型中，才能区分稳定遗传潜力和可通过管理优化修正的部分，从而让选育与生产形成闭环。",
    },
    {
        "code": "rice_ai_breeder",
        "slug": "rice_ai",
        "name": "育种家经验AI化与主栽品种改良",
        "owners": ["fanlongjiang"],
        "goal": "将育种家长期积累的经验结构化为模型能力，服务区域主栽品种精准改良",
        "materials": "核心主栽品种、历史组合材料、区域试验品系和专家经验案例库",
        "primary_traits": "区域适应性、食味、抗倒性、产量稳定性、组合潜力和改良风险",
        "stress_axis": "区域生态差异、年份波动、目标市场需求和育种决策偏好",
        "phenotype_data": "区域试验表现、品种画像、组合表现和专家评价记录",
        "omics_data": "核心品种基因型、关键位点和经验案例中的遗传标签数据",
        "modeling_stack": "经验知识图谱、案例检索模型和可解释改良建议模型",
        "deployment": "区域主栽品种改良建议、亲本选择和组合设计辅助决策",
        "success_metric": "模型建议与高水平育种家判断一致，且在区域改良实践中可复用",
        "key_risk": "把专家经验直接文本化而不做结构化约束，导致建议无法追溯和验证",
        "decision_output": "亲本推荐、改良方向排序和区域组合设计建议",
        "validation_route": "历史案例回放验证、区域试验复现和育种家盲评比对",
        "knowledge_core": "专家经验-品种画像-区域适应-改良建议",
        "direct_question": "“育种家经验 AI 化”在区域主栽品种改良中最关键的价值是什么？",
        "direct_context": "目标是把长期积累的品种选择经验转化为可复用的模型能力。",
        "direct_answer": "关键价值在于把育种家关于材料选择、组合判断和区域适应性的隐性知识结构化，让模型可以在相似情境下给出可解释的改良建议。这样经验不再依赖个体记忆，而能变成可验证、可复盘、可扩展的决策资产。",
    },
    {
        "code": "embodied_intelligence_agri",
        "slug": "embodied",
        "name": "快速表型采集与生产匹配",
        "owners": ["yangwanneng"],
        "goal": "利用具身智能完成多模态表型采集、性状识别和生产匹配闭环",
        "materials": "农业机器人平台、作物生产群体、多模态传感器和场景化作业任务",
        "primary_traits": "株高、冠层结构、病斑程度、长势等级、成熟度和作业可达性",
        "stress_axis": "田间环境变化、作物生育期差异、设备姿态变化和作业负载变化",
        "phenotype_data": "多模态图像、点云、环境传感器、作业轨迹和人工标注数据",
        "omics_data": "场景不以组学为核心，但可对接关键基因型或品种标签用于任务匹配",
        "modeling_stack": "多模态感知模型、性状提取模型和生产匹配决策引擎",
        "deployment": "田间表型采集、生产管理建议、采收分级和育种筛选辅助",
        "success_metric": "感知结果稳定可复用，并能直接驱动补肥、灌溉、采收或筛选决策",
        "key_risk": "把机器人采集当成单纯图像识别任务，未把性状解释和生产决策闭环打通",
        "decision_output": "性状指标、作业建议、管理动作和生产匹配方案",
        "validation_route": "多季田间复现、不同设备平台验证和人工专家对照验证",
        "knowledge_core": "多模态感知-性状提取-任务匹配-生产闭环",
        "direct_question": "具身智能在农业快速表型采集与生产匹配中的主要作用是什么？",
        "direct_context": "希望把农业性状评价与现场生产决策连接起来。",
        "direct_answer": "具身智能的价值不只是自动采图，而是把感知、解释和执行放到同一链路中。它应在田间或设施环境中稳定提取关键性状指标，再把这些指标直接映射为补肥、灌溉、采收或筛选等可执行动作。",
    },
]


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def fetch_id_map(cursor, table: str, key_column: str) -> dict[str, int]:
    rows = cursor.execute(f"SELECT id, {key_column} AS key_value FROM {table}").fetchall()
    return {str(row["key_value"]): int(row["id"]) for row in rows}


def build_question(scene: dict[str, object], module: dict[str, str], action: dict[str, str]) -> str:
    scene_name = str(scene["name"])
    module_name = module["name"]
    action_key = action["key"]
    if action_key == "define_scope":
        return f"在{scene_name}场景下，围绕“{module_name}”这一节点，应该如何给研究对象下操作性定义，避免只停留在概念层面？"
    if action_key == "core_hypothesis":
        return f"如果把“{module_name}”视为{scene_name}研究链路中的关键节点，最值得优先验证的核心假设是什么？"
    if action_key == "key_variables":
        return f"在{scene_name}的“{module_name}”环节，哪些变量必须进入最小可用分析框架，哪些变量可以作为扩展层？"
    if action_key == "experimental_design":
        return f"为了检验{scene_name}中“{module_name}”相关假设，试验设计应如何安排材料、梯度、时期和重复？"
    if action_key == "data_integration":
        return f"在{scene_name}的“{module_name}”节点上，如何把表型、环境和机制数据整合成同一条可追溯的分析链路？"
    if action_key == "decision_threshold":
        return f"推进{scene_name}的“{module_name}”研究时，哪些阈值或判定规则应被设置成继续、调整或暂停的决策点？"
    if action_key == "validation_route":
        return f"完成{scene_name}的“{module_name}”分析后，怎样设计独立验证路线，避免结论只在当前数据里成立？"
    if action_key == "failure_mode":
        return f"如果{scene_name}在“{module_name}”阶段没有得到稳定结论，最常见的失败模式或误判来源是什么？"
    if action_key == "translation_path":
        return f"如何把{scene_name}中“{module_name}”得到的研究结果，转化成实际可执行的选材、育种或生产决策？"
    return f"若要把{scene_name}的“{module_name}”接入整个领域知识图谱，上游和下游最关键的连接节点分别是什么？"


def build_context(scene: dict[str, object], module: dict[str, str], action: dict[str, str]) -> str:
    return (
        f"研究目标：{scene['goal']}。"
        f" 当前知识主线：{scene['knowledge_core']}。"
        f" 当前节点：{module['name']}，重点关注{module['measurements']}。"
        f" 可用基础：{scene['phenotype_data']}；{scene['omics_data']}。"
        f" 当前推理动作：{action['name']}。"
    )


def build_answer(scene: dict[str, object], module: dict[str, str], action: dict[str, str]) -> str:
    action_key = action["key"]
    if action_key == "define_scope":
        return (
            f"应先把{scene['goal']}拆成材料、性状、环境和决策四类功能单元。"
            f" 在“{module['name']}”节点中，核心不是泛泛描述，而是明确{scene['materials']}作为材料边界，"
            f" 以{module['measurements']}作为观测边界，再用{scene['stress_axis']}构成场景压力轴。"
            f" 最终要把该节点的输出固定为“{module['deliverable']}”，这样后续模块才能围绕统一对象推进。"
        )
    if action_key == "core_hypothesis":
        return (
            f"优先假设应围绕“{module['focus']}”展开，即{module['name']}中的关键变化会通过{scene['primary_traits']}影响{scene['success_metric']}。"
            f" 这个假设必须同时解释材料差异、环境响应和决策结果三层关系，而不是只解释单一表型。"
            f" 只有当假设能被{scene['modeling_stack']}和独立验证共同支持，它才适合作为后续研究主线。"
        )
    if action_key == "key_variables":
        return (
            f"最小变量集至少应包含{scene['materials']}的身份信息、{scene['primary_traits']}、{scene['stress_axis']}以及{module['measurements']}。"
            f" 扩展层再加入{scene['omics_data']}和成本、时间窗等应用变量。"
            f" 这样做的目的是先保证链路可运行，再逐步把解释性和预测性提升到可部署水平。"
        )
    if action_key == "experimental_design":
        return (
            f"试验设计应先在{scene['materials']}中做分层选材，再围绕{scene['stress_axis']}设置梯度处理，并保证关键时期重复采样。"
            f" “{module['name']}”节点的设计重点是让{module['measurements']}可以在材料、时期和环境三个维度被同时比较。"
            f" 若条件允许，应预留独立年份或独立地点作为盲验证批次，而不是把全部数据都用于同一轮建模。"
        )
    if action_key == "data_integration":
        return (
            f"整合时要以材料编号、时期和环境处理作为共同主键，把{scene['phenotype_data']}与{scene['omics_data']}按同一时间轴对齐。"
            f" 在“{module['name']}”节点中，先形成可重复的基础数据层，再叠加{scene['modeling_stack']}形成解释层和预测层。"
            f" 只有先控制数据对齐误差，后续因果链和选择规则才不会建立在错位样本上。"
        )
    if action_key == "decision_threshold":
        return (
            f"建议将“{module['name']}”的继续条件设为：关键指标达到预设稳定性、跨处理趋势方向一致，且对{scene['success_metric']}有明确提升。"
            f" 若{module['measurements']}在重复间波动过大，或仅在单一场景显著，就应先回到试验或数据层面修正。"
            f" 阈值设置的目标不是追求统计显著本身，而是保证结果能支撑{scene['decision_output']}。"
        )
    if action_key == "validation_route":
        return (
            f"独立验证应沿着{scene['validation_route']}展开，并尽量在与训练数据不同的材料或场景上复核。"
            f" 对“{module['name']}”而言，至少要验证{module['deliverable']}是否能稳定复现，以及其对{scene['deployment']}是否仍然有效。"
            f" 如果验证阶段表现显著回落，就说明节点仍停留在局部规律，不能直接进入部署。"
        )
    if action_key == "failure_mode":
        return (
            f"这一阶段最常见的问题是{scene['key_risk']}，同时还包括“{module['risk']}”。"
            f" 一旦出现这种偏差，研究者会把局部相关性误判成稳定规律，导致后续模型或选择指数建立在错误前提上。"
            f" 修正方式是回到原始试验设计、样本对齐和独立验证三处做交叉审计，而不是只在模型参数上打补丁。"
        )
    if action_key == "translation_path":
        return (
            f"转化时要把“{module['deliverable']}”映射为{scene['decision_output']}，并明确对应的使用场景是{scene['deployment']}。"
            f" 在执行层面，可先用{scene['modeling_stack']}给出候选排序，再结合成本、周期和风险做二次筛选。"
            f" 只有当研究节点能够直接改变选材、组合、管理或验证顺序，它才真正完成了从科研到应用的转化。"
        )
    return (
        f"知识图谱连接时，应把“{module['name']}”视为从“{module['upstream']}”流向“{module['downstream']}”的中间桥梁。"
        f" 上游提供研究背景和输入变量，下游承接{module['deliverable']}并进入{scene['deployment']}。"
        f" 对{scene['name']}而言，这样的连接方式能把{scene['knowledge_core']}串成连续可追踪的研究链，而不是孤立的题目集合。"
    )


def build_direct_seed(scene: dict[str, object]) -> dict[str, object]:
    return {
        "external_id": f"domain_demo_{scene['slug']}_direct_001",
        "technical_type": "direct_qa",
        "business_tag": scene["code"],
        "owners": scene["owners"],
        "question_text": scene["direct_question"],
        "context_text": scene["direct_context"],
        "answer_text": scene["direct_answer"],
        "metadata": {
            "seed_group": "domain-direct",
            "scene_code": scene["code"],
            "scene_name": scene["name"],
        },
    }


def build_cot_seed(
    scene: dict[str, object],
    module: dict[str, str],
    action: dict[str, str],
    sequence_no: int,
) -> dict[str, object]:
    return {
        "external_id": f"domain_demo_{scene['slug']}_cot_{sequence_no:03d}",
        "technical_type": "cot_qa",
        "business_tag": scene["code"],
        "owners": scene["owners"],
        "question_text": build_question(scene, module, action),
        "context_text": build_context(scene, module, action),
        "answer_text": build_answer(scene, module, action),
        "metadata": {
            "seed_group": "domain-cot",
            "scene_code": scene["code"],
            "scene_name": scene["name"],
            "module_key": module["key"],
            "module_name": module["name"],
            "action_key": action["key"],
            "action_name": action["name"],
            "cot_sequence_no": sequence_no,
        },
    }


def build_domain_qa_seeds() -> list[dict[str, object]]:
    seeds: list[dict[str, object]] = []
    for scene in DOMAIN_SCENES:
        seeds.append(build_direct_seed(scene))
        sequence_no = 1
        for module in RESEARCH_MODULES:
            for action in REASONING_ACTIONS:
                seeds.append(build_cot_seed(scene, module, action, sequence_no))
                sequence_no += 1
        if sequence_no - 1 != COT_PER_SCENE:
            raise ValueError(f"scene {scene['code']} generated {sequence_no - 1} CoT seeds, expected 100")
    return seeds


DOMAIN_QA_SEEDS = build_domain_qa_seeds()


def delete_sample_qa_items(cursor) -> int:
    qa_item_rows = cursor.execute(
        """
        SELECT id
        FROM qa_items
        WHERE source IN ('demo-seed', 'domain-seed')
           OR external_id LIKE 'qa_demo_%'
           OR external_id LIKE 'remote_sync_smoke_%'
           OR external_id LIKE 'domain_demo_%'
        """
    ).fetchall()
    qa_item_ids = [int(row["id"]) for row in qa_item_rows]
    if not qa_item_ids:
        return 0

    qa_item_placeholders = ",".join("?" for _ in qa_item_ids)
    answer_rows = cursor.execute(
        f"SELECT id FROM qa_answers WHERE qa_item_id IN ({qa_item_placeholders})",
        tuple(qa_item_ids),
    ).fetchall()
    answer_ids = [int(row["id"]) for row in answer_rows]
    answer_placeholders = ",".join("?" for _ in answer_ids) if answer_ids else ""

    task_rows = cursor.execute(
        f"SELECT id FROM evaluation_tasks WHERE qa_item_id IN ({qa_item_placeholders})",
        tuple(qa_item_ids),
    ).fetchall()
    task_ids = [int(row["id"]) for row in task_rows]
    task_placeholders = ",".join("?" for _ in task_ids) if task_ids else ""

    if task_ids:
        cursor.execute(
            f"DELETE FROM evaluation_records WHERE task_id IN ({task_placeholders})",
            tuple(task_ids),
        )
        cursor.execute(
            f"DELETE FROM evaluation_drafts WHERE task_id IN ({task_placeholders})",
            tuple(task_ids),
        )

    llm_session_rows = cursor.execute(
        f"""
        SELECT id
        FROM llm_sessions
        WHERE qa_item_id IN ({qa_item_placeholders})
        """,
        tuple(qa_item_ids),
    ).fetchall()
    llm_session_ids = [int(row["id"]) for row in llm_session_rows]
    if llm_session_ids:
        session_placeholders = ",".join("?" for _ in llm_session_ids)
        cursor.execute(
            f"DELETE FROM llm_messages WHERE session_id IN ({session_placeholders})",
            tuple(llm_session_ids),
        )
        cursor.execute(
            f"DELETE FROM llm_sessions WHERE id IN ({session_placeholders})",
            tuple(llm_session_ids),
        )

    model_trial_query = f"""
        SELECT id
        FROM model_trial_sessions
        WHERE source_qa_item_id IN ({qa_item_placeholders})
    """
    model_trial_params: tuple[int, ...] = tuple(qa_item_ids)
    if answer_ids:
        model_trial_query += f" OR source_answer_id IN ({answer_placeholders})"
        model_trial_params += tuple(answer_ids)
    model_trial_rows = cursor.execute(model_trial_query, model_trial_params).fetchall()
    model_trial_ids = [int(row["id"]) for row in model_trial_rows]
    if model_trial_ids:
        mt_placeholders = ",".join("?" for _ in model_trial_ids)
        cursor.execute(
            f"DELETE FROM model_trial_messages WHERE session_id IN ({mt_placeholders})",
            tuple(model_trial_ids),
        )
        cursor.execute(
            f"DELETE FROM model_trial_sessions WHERE id IN ({mt_placeholders})",
            tuple(model_trial_ids),
        )

    if answer_ids:
        cursor.execute(
            f"DELETE FROM llm_messages WHERE target_answer_id IN ({answer_placeholders}) OR generated_answer_id IN ({answer_placeholders})",
            tuple(answer_ids) + tuple(answer_ids),
        )
        cursor.execute(
            f"DELETE FROM qa_aggregates WHERE current_answer_id IN ({answer_placeholders}) OR final_standard_answer_id IN ({answer_placeholders})",
            tuple(answer_ids) + tuple(answer_ids),
        )

    cursor.execute(
        f"DELETE FROM expert_task_abandons WHERE qa_item_id IN ({qa_item_placeholders})",
        tuple(qa_item_ids),
    )
    cursor.execute(
        f"DELETE FROM evaluation_tasks WHERE qa_item_id IN ({qa_item_placeholders})",
        tuple(qa_item_ids),
    )
    cursor.execute(
        f"DELETE FROM qa_aggregates WHERE qa_item_id IN ({qa_item_placeholders})",
        tuple(qa_item_ids),
    )
    if answer_ids:
        cursor.execute(
            f"DELETE FROM qa_answers WHERE id IN ({answer_placeholders})",
            tuple(answer_ids),
        )
    cursor.execute(
        f"DELETE FROM qa_items WHERE id IN ({qa_item_placeholders})",
        tuple(qa_item_ids),
    )
    return len(qa_item_ids)


def insert_domain_qa_seeds(cursor) -> int:
    application_ids = fetch_id_map(cursor, "applications", "name")
    technical_type_ids = fetch_id_map(cursor, "technical_types", "code")
    business_tag_ids = fetch_id_map(cursor, "business_tags", "code")
    user_ids = fetch_id_map(cursor, "users", "username")

    ai4s_application_id = application_ids[AI4S_APPLICATION_NAME]

    created_count = 0
    for seed in DOMAIN_QA_SEEDS:
        created_at = now_iso()
        business_tags_json = json.dumps([seed["business_tag"]], ensure_ascii=False)
        metadata_json = json.dumps(seed["metadata"], ensure_ascii=False)
        cursor.execute(
            """
            INSERT INTO qa_items (
              external_id, technical_type_id, business_tags_json, application_id,
              question_text, context_text, tags_json, source, status, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'domain-seed', 'active', ?, ?)
            """,
            (
                seed["external_id"],
                technical_type_ids[str(seed["technical_type"])],
                business_tags_json,
                ai4s_application_id,
                seed["question_text"],
                seed["context_text"],
                business_tags_json,
                created_at,
                metadata_json,
            ),
        )
        qa_item_id = int(cursor.lastrowid)
        cursor.execute(
            """
            INSERT INTO qa_answers (
              qa_item_id, answer_text, answer_type, source_model,
              version_no, is_current, created_at
            ) VALUES (?, ?, 'imported_candidate', 'domain-seed', 1, 1, ?)
            """,
            (qa_item_id, seed["answer_text"], created_at),
        )
        answer_id = int(cursor.lastrowid)

        for expert_order, username in enumerate(seed["owners"], start=1):
            if username not in user_ids:
                continue
            expert_user_id = user_ids[username]
            cursor.execute(
                """
                INSERT OR IGNORE INTO expert_applications (
                  expert_user_id, application_id, priority, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    expert_user_id,
                    ai4s_application_id,
                    expert_order,
                    created_at,
                ),
            )
            cursor.execute(
                """
                INSERT OR IGNORE INTO expert_business_tags (
                  expert_user_id, business_tag_id, priority, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    expert_user_id,
                    business_tag_ids[str(seed["business_tag"])],
                    expert_order,
                    created_at,
                ),
            )
            cursor.execute(
                """
                INSERT OR IGNORE INTO evaluation_tasks (
                  qa_item_id, answer_id, expert_user_id, round_no,
                  task_type, status, assigned_at
                ) VALUES (?, ?, ?, 1, 'initial_review', 'pending', ?)
                """,
                (qa_item_id, answer_id, expert_user_id, created_at),
            )
        created_count += 1

    return created_count


def delete_legacy_business_tags(cursor) -> int:
    legacy_rows = cursor.execute(
        f"""
        SELECT id, code
        FROM business_tags
        WHERE code IN ({",".join("?" for _ in LEGACY_BUSINESS_TAG_CODES)})
        """,
        tuple(LEGACY_BUSINESS_TAG_CODES),
    ).fetchall()
    if not legacy_rows:
        return 0

    legacy_ids = [int(row["id"]) for row in legacy_rows]
    legacy_codes = {str(row["code"]) for row in legacy_rows}

    cursor.execute(
        f"""
        DELETE FROM expert_business_tags
        WHERE business_tag_id IN ({",".join("?" for _ in legacy_ids)})
        """,
        tuple(legacy_ids),
    )

    batches = cursor.execute(
        """
        SELECT id, business_tags_json
        FROM dataset_batches
        WHERE business_tags_json IS NOT NULL
          AND business_tags_json != ''
          AND business_tags_json != '[]'
        """
    ).fetchall()
    for row in batches:
        try:
            parsed = json.loads(row["business_tags_json"])
        except Exception:
            continue
        if not isinstance(parsed, list):
            continue
        filtered = [item for item in parsed if str(item) not in legacy_codes]
        if filtered == parsed:
            continue
        cursor.execute(
            "UPDATE dataset_batches SET business_tags_json = ? WHERE id = ?",
            (json.dumps(filtered, ensure_ascii=False), row["id"]),
        )

    cursor.execute(
        f"""
        DELETE FROM business_tags
        WHERE id IN ({",".join("?" for _ in legacy_ids)})
        """,
        tuple(legacy_ids),
    )
    return len(legacy_ids)


if __name__ == "__main__":
    if not IS_DEVELOPMENT and os.getenv("QAEVALUATE_ALLOW_DEMO_SEED") != "1":
        raise SystemExit(
            f"refusing to reset sample data in env={APP_ENV}. "
            "Set QAEVALUATE_ENV=development or QAEVALUATE_ALLOW_DEMO_SEED=1 to override."
        )

    init_db()
    with db_cursor() as cursor:
        deleted_count = delete_sample_qa_items(cursor)
        deleted_tag_count = delete_legacy_business_tags(cursor)
        created_count = insert_domain_qa_seeds(cursor)

    print(
        f"reset sample domain data for env={APP_ENV} db={DB_PATH}: "
        f"deleted {deleted_count} old sample qa items, "
        f"deleted {deleted_tag_count} legacy business tags, "
        f"inserted {created_count} new domain qa items"
    )
