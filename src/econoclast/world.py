"""The world of Econoclast: one lexicon shared by the agent, the web stage and the reports.

Ravenna, an autumn afternoon. A traveller stands under the gold of San Vitale and the
mosaic moves. A hooded figure assembles itself out of loose tesserae: the Sicarius. It
will walk the old procession route from the port of Classis to the Palatium and test
the Emperor's decree (a paper's headline claim) for the place where it bleeds.

Everything the program does maps onto that walk:

- a *station* is a phase of the run (fetch the paper, read it, find the data, build the
  local quant workshop, attack, re-run the numbers, judge);
- a *blade* is one line of attack (specification search, cherry-picking, identification,
  ...); each blade either lands a *wound* (a grounded finding) or is *parried* (the paper
  defends itself on that front);
- the *verdict* is the fragility score, read as how badly the Emperor is hurt.

This module is the single source of truth for those names. The web UI fetches it from
``/api/world`` so the stage, the agent's mandate and the reports never drift apart.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Station:
    key: str
    latin: str
    en: str
    zh: str
    act_en: str
    act_zh: str


@dataclass(frozen=True)
class Blade:
    key: str
    latin: str
    en: str
    zh: str
    hunts_en: str
    hunts_zh: str
    category: str  # the questionable-research-practice family it belongs to


@dataclass(frozen=True)
class Band:
    ceiling: float  # score strictly below this falls in the band
    key: str
    latin: str
    en: str
    zh: str
    blurb_en: str
    blurb_zh: str
    pose: str  # how the Emperor is drawn on the stage


STATIONS: tuple[Station, ...] = (
    Station("classis", "Classis", "The Port", "克拉塞港",
            "Fetch the paper: the decree arrives by ship.",
            "取得论文：诏书随船入港。"),
    Station("scriptorium", "Scriptorium", "The Scriptorium", "缮写室",
            "Read the paper and examine the parchment: its claim, its numbers, its earlier versions, any forgery or rouge.",
            "通读并检验这张羊皮纸：它的结论、数字、早先的版本，以及伪造与粉饰的痕迹。"),
    Station("forum", "Forum", "The Forum", "广场",
            "Learn the field: the real actors, institutions and theory the decree claims to describe.",
            "了解这个领域：诏书声称描述的真实人群、制度与理论。"),
    Station("horreum", "Horreum", "The Warehouse", "仓廪",
            "Find the data: replication packages, public sources, or the traveller's help.",
            "搜寻数据：复现包、公开数据源，必要时向旅人求援。"),
    Station("fabrica", "Fabrica", "The Arms Forge", "兵器工坊",
            "Build the local quant workshop and reproduce the headline number.",
            "搭建本地量化工坊，先把论文的核心数字复现出来。"),
    Station("palatium", "Palatium", "The Palace Gate", "宫门",
            "The seven method blades: each line of attack against the paper's defences.",
            "方法七刃：逐一攻击论文的每道防线。"),
    Station("aula", "Aula", "The Throne Hall", "王座厅",
            "A thousand roads: re-run the result across every defensible specification.",
            "千条道路：在所有说得过去的设定下重跑结果。"),
    Station("curia", "Curia", "The Tribunal", "元老院",
            "The verdict: how badly the decree is wounded.",
            "裁决：这道诏书伤得有多重。"),
)

BLADES: tuple[Blade, ...] = (
    Blade("labyrinthus", "Labyrinthus", "The Labyrinth", "迷宫之刃",
          "Specification search: the garden of forking paths, a headline spec picked from many.",
          "设定搜索：分岔小径的花园，从一堆设定里挑出显著的那一个。",
          "specification_search"),
    Blade("canistrum", "Canistrum", "The Fruit Basket", "果篮之刃",
          "Cherry-picking: convenient samples, windows, subgroups, outcomes, dropped data.",
          "挑樱桃：恰到好处的样本、时间窗、子群体、结果变量，以及被丢掉的数据。",
          "cherry_picking"),
    Blade("persona", "Persona", "The Mask", "面具之刃",
          "Identification: is the causal face real, or a mask over correlation?",
          "识别策略：这张因果的脸是真的，还是罩在相关性上的面具？",
          "identification"),
    Blade("inversio", "Inversio", "The Inversion", "倒置之刃",
          "Reverse causality: the outcome driving the cause, simultaneity, timing that runs backwards.",
          "倒因为果：结果反过来驱动原因、互为因果、时间顺序对不上。",
          "reverse_causality"),
    Blade("theoria", "Theoria", "The Theory", "理论之刃",
          "Theory misused: a model whose assumptions fail here, or that predicts something else.",
          "理论误用：所引模型的关键假设在此不成立，或者它本来预测的是另一回事。",
          "theory"),
    Blade("novacula", "Novacula", "Occam's Razor", "剃刀之刃",
          "Needless theory: mechanisms, assumptions and parameters that explain nothing a simpler account "
          "does not, or that are bolted on to explain away contradicting facts.",
          "不必要的理论：比更简单的解释多不出任何解释力的机制、假设和参数，或者为了把相反的事实圆过去而硬加的东西。",
          "parsimony"),
    Blade("mundus", "Mundus", "The World", "现实之刃",
          "Reality: a mechanism real people would not follow, institutions that do not work that way, "
          "magnitudes the world cannot produce.",
          "与现实不符：真实的人不会这样行事，制度并非如此运作，数量级现实中不可能出现。",
          "reality"),
    Blade("scutum", "Scutum", "The Shield", "盾牌之刃",
          "Robustness: which standard checks are present and which are conveniently missing.",
          "稳健性：该做的检验做了哪些，又恰好漏了哪些。",
          "robustness"),
    Blade("augur", "Augur", "The Augur", "占卜之刃",
          "HARKing: hypotheses and mechanisms written after the results were known.",
          "事后假设：先看到结果，再写出的假说和机制。",
          "harking"),
    Blade("tuba", "Tuba", "The Herald's Horn", "号角之刃",
          "Over-claiming: the abstract promises more than the design can deliver.",
          "过度宣称：摘要许下的，超出了研究设计能兑现的。",
          "overclaiming"),
    Blade("bibliotheca", "Bibliotheca", "The Library", "书库之刃",
          "Literature: novelty claims, contradicted findings, citations that do not resolve or do not say "
          "what the paper claims they say.",
          "文献：首创性声明、与既有发现的冲突、查无此文或根本没这么说的引用。",
          "literature"),
    Blade("falsum", "Falsum", "The Forgery", "伪造之刃",
          "Fabrication: numbers and data that carry the fingerprints of being made up or doctored.",
          "伪造：带着编造或篡改指纹的数字与数据。",
          "fabrication"),
    Blade("palimpsestus", "Palimpsestus", "The Palimpsest", "改写之刃",
          "Rewriting: outcomes, samples or hypotheses quietly changed between versions or against the "
          "pre-registration.",
          "改写：在不同版本之间、或相对预注册，悄悄换掉的结果变量、样本与假设。",
          "version_manipulation"),
    Blade("fucus", "Fucus", "The Rouge", "粉饰之刃",
          "Spin: abstract numbers the tables never show, buried nulls, 'marginal' significance, misleading "
          "figures and framings.",
          "粉饰：表格里找不到的摘要数字、被埋掉的零结果、“边际显著”、误导性的图与表述。",
          "spin"),
    Blade("abacus", "Abacus", "The Abacus", "算盘之刃",
          "Arithmetic: reported coefficients, errors, stars and p-values that cannot all be true.",
          "算术：系数、标准误、星号和 p 值彼此对不上。",
          "reporting_inconsistency"),
    Blade("speculum", "Speculum", "The Mirror", "铜镜之刃",
          "Reproduction: re-running the paper's own specification on its own data, and reading the authors' "
          "code for undisclosed drops, filters and recodes.",
          "复现：用论文自己的数据和设定再跑一遍，并审读作者代码里没交代的删样本、筛选与重编码。",
          "data_integrity"),
    Blade("mille_viae", "Mille Viae", "A Thousand Roads", "千径之刃",
          "Multiverse: how often the result survives across every defensible specification.",
          "多重宇宙：在所有说得过去的设定里，结果能活下来多少次。",
          "specification_search"),
)

BANDS: tuple[Band, ...] = (
    Band(15, "stat", "Imperator stat", "The Emperor stands", "皇帝屹立",
         "No material wound. The headline result held against every blade.",
         "没有实质伤口。核心结论顶住了每一刃。", "defiant"),
    Band(35, "laesus", "Laesus", "Grazed", "擦伤",
         "Small cuts. The headline result is probably safe.",
         "几道小口子，核心结论大概率无恙。", "idle"),
    Band(60, "vulneratus", "Vulneratus", "Wounded", "负伤",
         "Real wounds. The result may not survive a hostile referee.",
         "伤口是真的，结论未必扛得住严苛的审稿人。", "wounded"),
    Band(80, "moribundus", "Moribundus", "Mortally wounded", "重伤垂危",
         "The central claim is fragile to plausible alternative choices.",
         "换一个同样合理的做法，核心结论就站不住了。", "kneeling"),
    Band(101, "cecidit", "Cecidit", "Fallen", "倒下",
         "Treat the central claim as unsupported until these wounds are answered.",
         "在这些伤口得到回应之前，核心结论应视为没有支撑。", "fallen"),
)

@dataclass(frozen=True)
class Seal:
    key: str
    latin: str
    en: str
    zh: str
    blurb_en: str
    blurb_zh: str


# The decree's seal: the integrity of the paper, judged apart from how fragile its result is.
SEALS: tuple[Seal, ...] = (
    Seal("integrum", "Sigillum integrum", "Seal intact", "封印完好",
         "No sign of fabricated numbers, rewritten versions, undisclosed data steps or spin.",
         "没有发现编造的数字、被改写的版本、未披露的数据操作或粉饰。"),
    Seal("dubium", "Sigillum dubium", "Seal questioned", "封印存疑",
         "Some integrity flags deserve a human look; each may have an innocent explanation.",
         "有些诚信疑点值得人工核查，每一处都可能有无辜的解释。"),
    Seal("fractum", "Sigillum fractum", "Seal broken", "封印破损",
         "Serious integrity flags: numbers that cannot be true, data or versions bent toward the conclusion. "
         "A hypothesis to verify with the authors, not an accusation.",
         "严重的诚信疑点：不可能成立的数字、朝结论方向弯折的数据或版本。这是需要向作者核实的假设，不是指控。"),
)
INTEGRITY_BLADES = ("abacus", "falsum", "speculum", "palimpsestus", "fucus")

SEVERITIES = ("info", "low", "medium", "high", "critical")
SEVERITY_WEIGHT = {"info": 0.0, "low": 1.0, "medium": 2.5, "high": 5.0, "critical": 8.0}
SEVERITY_LATIN = {"info": "Nota", "low": "Scalpsit", "medium": "Secuit", "high": "Transfixit",
                  "critical": "Iugulavit"}

STATION_KEYS = tuple(s.key for s in STATIONS)
BLADE_KEYS = tuple(b.key for b in BLADES)


def station(key: str) -> Station | None:
    return next((s for s in STATIONS if s.key == key), None)


def blade(key: str) -> Blade | None:
    return next((b for b in BLADES if b.key == key), None)


def band_for(score: float) -> Band:
    for b in BANDS:
        if score < b.ceiling:
            return b
    return BANDS[-1]


def seal(key: str) -> Seal:
    return next((x for x in SEALS if x.key == key), SEALS[0])


def as_dict() -> dict:
    """The lexicon as plain JSON for the web stage and the reports."""
    return {
        "stations": [asdict(s) for s in STATIONS],
        "blades": [asdict(b) for b in BLADES],
        "bands": [asdict(b) for b in BANDS],
        "seals": [asdict(x) for x in SEALS],
        "integrity_blades": list(INTEGRITY_BLADES),
        "severities": list(SEVERITIES),
        "severity_weight": SEVERITY_WEIGHT,
        "severity_latin": SEVERITY_LATIN,
    }
