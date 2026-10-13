"""模型用途目录：配置引导、快速分配与连接诊断共用。"""

from dataclasses import asdict, dataclass
from typing import Literal


@dataclass(frozen=True)
class Copy:
    zh: str
    en: str


@dataclass(frozen=True)
class ModelPurpose:
    role: str
    label: Copy
    description: Copy
    guidance: Copy
    allocation: Literal["main", "text", "vision"] | None = None


@dataclass(frozen=True)
class PurposeGroup:
    id: str
    label: Copy
    purposes: tuple[ModelPurpose, ...]


MODEL_PURPOSE_GROUPS = (
    PurposeGroup(
        "research",
        Copy("研究执行", "Research"),
        (
            ModelPurpose(
                "orchestrator",
                Copy("研究规划与统筹", "Planning and coordination"),
                Copy(
                    "拆解任务、调度执行并完成常规回答",
                    "Plans tasks, coordinates execution, and writes the usual final answer",
                ),
                Copy(
                    "网络 / 混合研究 · 需要工具调用",
                    "Web / Hybrid research · Tool calling required",
                ),
                "main",
            ),
            ModelPurpose(
                "sub_agent",
                Copy("检索与阅读", "Search and reading"),
                Copy(
                    "探索来源、检索网页及本地文档问答",
                    "Explores sources, searches the web, and answers local document questions",
                ),
                Copy(
                    "网络 / 本地 / 混合 · 需要工具调用",
                    "Web / Local / Hybrid · Tool calling required",
                ),
                "main",
            ),
            ModelPurpose(
                "extraction",
                Copy("证据提取", "Evidence extraction"),
                Copy(
                    "从来源内容提取可核验的结构化事实",
                    "Extracts verifiable structured facts from source content",
                ),
                Copy(
                    "处理来源内容时 · 关注结构化输出与成本",
                    "When processing sources · Consider structured output and cost",
                ),
                "text",
            ),
            ModelPurpose(
                "judge",
                Copy("判断与核验", "Review and verification"),
                Copy(
                    "核验来源支持关系，并执行相关判断流程",
                    "Reviews source support and performs related checks",
                ),
                Copy(
                    "调用核验功能时 · 关注判断质量",
                    "When verification is requested · Prioritize judgment quality",
                ),
                "main",
            ),
        ),
    ),
    PurposeGroup(
        "content",
        Copy("内容处理", "Content processing"),
        (
            ModelPurpose(
                "synthesis",
                Copy("写作与回答兜底", "Writing and answer fallback"),
                Copy(
                    "供写作 Agent 及最终回答回退使用",
                    "Used by the writer agent and final-answer fallback",
                ),
                Copy(
                    "启用写作或常规收尾失败时",
                    "When writing is enabled or normal finalization fails",
                ),
                "text",
            ),
            ModelPurpose(
                "local_recap",
                Copy("文档与主题摘要", "Document and topic summaries"),
                Copy(
                    "生成章节、文档概览及知识库主题摘要",
                    "Creates section, document, and library topic summaries",
                ),
                Copy("处理本地知识库内容时", "When processing local knowledge-library content"),
                "text",
            ),
            ModelPurpose(
                "local_vision",
                Copy("图片与扫描件读取", "Images and scanned documents"),
                Copy(
                    "读取扫描文档，并为网页图片提供视觉回退",
                    "Reads scanned documents and provides a vision fallback for web images",
                ),
                Copy(
                    "需要图片输入能力 · 文本连接测试不验证视觉能力",
                    "Image input required · A text connection test does not verify vision",
                ),
                "vision",
            ),
        ),
    ),
    PurposeGroup(
        "skills",
        Copy("技能与复盘", "Skills and failure review"),
        (
            ModelPurpose(
                "skill_router",
                Copy("技能推荐与修复规划", "Skill selection and repair planning"),
                Copy(
                    "筛选相关技能，也用于定向修复任务规划",
                    "Selects relevant skills and plans targeted repair tasks",
                ),
                Copy("技能路由 / 定向修复时", "During skill routing or targeted repair"),
                "main",
            ),
            ModelPurpose(
                "skill_evolver",
                Copy("技能生成与修复", "Skill creation and repair"),
                Copy(
                    "识别技能需求，生成、调试和修复技能包",
                    "Identifies skill needs and generates, debugs, and repairs skill packages",
                ),
                Copy("创建技能时 · 需要工具调用", "When creating skills · Tool calling required"),
                "main",
            ),
            ModelPurpose(
                "post_mortem",
                Copy("失败复盘", "Failure review"),
                Copy(
                    "从失败轨迹中提炼后续检索策略",
                    "Distills follow-up search strategies from failed traces",
                ),
                Copy(
                    "启用失败记忆且遇到失败时",
                    "When failure memory is enabled and a failure occurs",
                ),
                "main",
            ),
        ),
    ),
    PurposeGroup(
        "evaluation",
        Copy("评测", "Evaluation"),
        (
            ModelPurpose(
                "reformat",
                Copy("评测结果重排", "Evaluation result formatting"),
                Copy(
                    "将答案转换为评测要求的格式",
                    "Converts answers to the format required by an evaluation",
                ),
                Copy(
                    "仅评测流程使用 · 单独设置输出长度",
                    "Evaluation only · Configure output length separately",
                ),
            ),
        ),
    ),
)

ROLE_NAMES = tuple(p.role for group in MODEL_PURPOSE_GROUPS for p in group.purposes)
RETIRED_MODEL_ROLES = frozenset({"skill_runtime"})


def purpose_groups_view() -> list[dict]:
    return [asdict(group) for group in MODEL_PURPOSE_GROUPS]
