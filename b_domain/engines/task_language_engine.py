import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Dict, Any

from b_domain.value_objects.enums import EnergyLevel, TaskComplexity, Priority


# ==========================================================
# DOMAIN DATA
# ==========================================================

@dataclass(frozen=True)
class InferredTaskFields:
    title: str
    description: str = ""
    priority: Priority = Priority.MEDIUM
    energy: EnergyLevel = EnergyLevel.BALANCED
    complexity: TaskComplexity = TaskComplexity.MEDIUM
    duration: int = 30
    context_id: Optional[str] = None
    due_date: Optional[datetime] = None
    recurrence: Optional[str] = None
    is_floating: bool = True


@dataclass(frozen=True)
class InferredTaskData:
    energy: EnergyLevel
    complexity: TaskComplexity
    duration_minutes: int
    confidence: float


@dataclass(frozen=True)
class Archetype:
    energy: EnergyLevel
    complexity: TaskComplexity
    base_duration: int
    weight: int = 1


@dataclass(frozen=True)
class IntensityModifier:
    energy_shift: int = 0
    complexity_shift: int = 0
    duration_mult: float = 1.0


# ==========================================================
# TOKENS
# ==========================================================

class TokenType(Enum):
    WORD = "WORD"
    DURATION = "DURATION"
    DATE = "DATE"
    PRIORITY = "PRIORITY"
    CONTEXT = "CONTEXT"
    TAG = "TAG"


@dataclass
class Token:
    type: TokenType
    value: str


# ==========================================================
# TOKENIZER
# ==========================================================

class TaskTokenizer:
    DURATION_PATTERN = re.compile(r"(\d+)(h|m|min)", re.I)

    def __init__(self, priorities_list: list[str], date_words: dict[str, str]):
        self.priorities = priorities_list
        self.date_words = date_words

    def tokenize(self, text: str) -> List[Token]:

        tokens = []

        parts = text.split()

        for part in parts:

            lower = part.lower()

            if part.startswith("@"):
                tokens.append(Token(TokenType.CONTEXT, part[1:]))
                continue

            if part.startswith("#"):
                tokens.append(Token(TokenType.TAG, part[1:]))
                continue

            if part in self.priorities:
                tokens.append(Token(TokenType.PRIORITY, part))
                continue

            if self.DURATION_PATTERN.match(part):
                tokens.append(Token(TokenType.DURATION, part))
                continue

            if lower in self.date_words:
                tokens.append(Token(TokenType.DATE, lower))
                continue

            tokens.append(Token(TokenType.WORD, part))

        return tokens


# ==========================================================
# AST
# ==========================================================

@dataclass
class TaskNode:
    title_words: List[str]

    duration: Optional[int] = None
    due: Optional[str] = None

    context: Optional[str] = None
    priority: Optional[str] = None

    tags: Optional[List[str]] = None


# ==========================================================
# PARSER
# ==========================================================

class TaskParser:

    def parse(self, tokens: List[Token]) -> TaskNode:

        title_words = []
        duration = None
        due = None
        context = None
        priority = None
        tags = []

        for token in tokens:

            if token.type == TokenType.WORD:
                title_words.append(token.value)

            elif token.type == TokenType.DURATION:
                duration = self._parse_duration(token.value)

            elif token.type == TokenType.DATE:
                due = token.value

            elif token.type == TokenType.CONTEXT:
                context = token.value

            elif token.type == TokenType.PRIORITY:
                priority = token.value

            elif token.type == TokenType.TAG:
                tags.append(token.value)

        return TaskNode(
            title_words=title_words,
            duration=duration,
            due=due,
            context=context,
            priority=priority,
            tags=tags
        )

    @staticmethod
    def _parse_duration(value: str) -> Optional[int]:

        if value.endswith("h"):
            return int(value[:-1]) * 60

        if value.endswith("m"):
            return int(value[:-1])

        if value.endswith("min"):
            return int(value[:-3])

        return None


# ==========================================================
# SEMANTIC INFERENCE
# ==========================================================

class SemanticInferencer:

    def __init__(
            self,
            archetypes: Dict[str, Archetype],
            lexicons: Dict[str, Dict[str, str]],
            modifiers: Dict[str, Dict[str, IntensityModifier]],
            default_lang: str = "pt"
    ):

        self.archetypes = archetypes
        self.default_lang = default_lang

        self.lexicons = self._compile_patterns(lexicons)
        self.modifiers = self._compile_modifiers(modifiers)

    @staticmethod
    def _compile_patterns(lexicons):

        compiled = {}

        for lang, entries in lexicons.items():

            compiled[lang] = {}

            for name, pattern in entries.items():
                compiled[lang][name] = re.compile(
                    fr"\b{pattern}\b",
                    re.IGNORECASE
                )

        return compiled

    @staticmethod
    def _compile_modifiers(modifiers):

        compiled = {}

        for lang, entries in modifiers.items():

            compiled[lang] = {}

            for pattern, modifier in entries.items():
                compiled[lang][
                    re.compile(fr"\b{pattern}\b", re.IGNORECASE)
                ] = modifier

        return compiled

    def infer(self, title: str, lang: str):

        title_lower = title.lower()

        lexicon = self.lexicons.get(lang, {})

        matches = []

        for name, pattern in lexicon.items():

            if pattern.search(title_lower):

                arch = self.archetypes.get(name)

                if arch:
                    matches.append(arch)

        if not matches:
            return InferredTaskData(
                EnergyLevel.BALANCED,
                TaskComplexity.MEDIUM,
                30,
                0.1
            )

        total_weight = sum(a.weight for a in matches)

        energy = sum(a.energy.value * a.weight for a in matches) / total_weight
        complexity = sum(a.complexity.value * a.weight for a in matches) / total_weight
        duration = sum(a.base_duration * a.weight for a in matches) / total_weight

        mods = self.modifiers.get(lang, {})

        for pattern, mod in mods.items():

            if pattern.search(title_lower):
                energy += mod.energy_shift
                complexity += mod.complexity_shift
                duration *= mod.duration_mult

        energy = EnergyLevel(max(1, min(3, round(energy))))
        complexity = TaskComplexity(max(1, min(5, round(complexity))))

        return InferredTaskData(
            energy,
            complexity,
            int(duration),
            min(1.0, total_weight / 5)
        )


# ==========================================================
# INTERPRETER
# ==========================================================

class TaskInterpreter:

    def __init__(
            self,
            semantic: SemanticInferencer,
            priority_map: dict[str, Any],
            contexts_map: Dict[str, str],
            dates_map: Dict[str, str],
    ):
        self.semantic = semantic
        self.priority_map = priority_map
        self.contexts_map = contexts_map
        self.dates_map = dates_map

    def interpret(self, node: TaskNode, now: datetime, lang: str) -> InferredTaskFields:

        title = " ".join(node.title_words)

        semantic_data = self.semantic.infer(title, lang)

        duration = node.duration or semantic_data.duration_minutes

        due_date = None

        if node.due:
            normalized = self.dates_map.get(node.due.lower())
            if normalized:
                due_date = self.resolve_relative_date(normalized, now)

        priority = self.priority_map.get(node.priority, Priority.MEDIUM)

        context = None

        if node.context:
            context = self.contexts_map.get(node.context, node.context)

        return InferredTaskFields(
            title=title,
            priority=priority,
            energy=semantic_data.energy,
            complexity=semantic_data.complexity,
            duration=duration,
            context_id=context,
            due_date=due_date,
        )

    @staticmethod
    def resolve_relative_date(token: str, now: datetime) -> datetime | None:

        match token:

            # hoje
            case "today":
                return now.replace(hour=23, minute=59, second=59, microsecond=0)

            # amanhã
            case "tomorrow":
                return (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)

            # depois de amanhã
            case "day_after_tomorrow":
                return (now + timedelta(days=2)).replace(hour=23, minute=59, second=59, microsecond=0)

            # ontem
            case "yesterday":
                return now - timedelta(days=1)

            case "day_before_yesterday":
                return now - timedelta(days=2)

            # curto prazo
            case "soon":
                return now + timedelta(hours=2)

            case "later":
                return now + timedelta(hours=6)

            # semana
            case "this_week":
                return now + timedelta(days=3)

            case "next_week":
                return now + timedelta(days=7)

            # mês
            case "this_month":
                return now + timedelta(days=15)

            case "next_month":
                return now + timedelta(days=30)

        return None


# ==========================================================
# ENGINE
# ==========================================================

class TaskLanguageEngine:

    def __init__(
            self,
            semantic: SemanticInferencer,
            priority_map: dict[str, Any],
            date_words: Dict[str, str],
            contexts_map: Dict[str, str],
    ):
        self.tokenizer = TaskTokenizer(list(priority_map.keys()), date_words)
        self.parser = TaskParser()
        self.interpreter = TaskInterpreter(
            semantic,
            priority_map,
            contexts_map,
            date_words,
        )

    def infer(self, text: str, now: datetime, lang: str = "pt") -> InferredTaskFields:
        tokens = self.tokenizer.tokenize(text)
        ast = self.parser.parse(tokens)
        return self.interpreter.interpret(ast, now, lang)


# 1. Definimos os Arquétipos (A "Alma" da tarefa)
ARCHETYPES = {
    "DEEP_WORK": Archetype(EnergyLevel.HIGH, TaskComplexity.VERY_HIGH, 60, weight=3),
    "LEARNING": Archetype(EnergyLevel.HIGH, TaskComplexity.MEDIUM, 45, weight=2),
    "ADMIN": Archetype(EnergyLevel.LOW, TaskComplexity.VERY_LOW, 15),
    "MEETING": Archetype(EnergyLevel.BALANCED, TaskComplexity.MEDIUM, 30),
    "MAINTENANCE": Archetype(EnergyLevel.BALANCED, TaskComplexity.LOW, 20),
}

# 2. Léxico por Idioma
LEXICONS = {
    "pt": {
        "DEEP_WORK": r"(codar|programar|desenvolver|refatorar|build|criar)",
        "LEARNING": r"(estudar|aprender|ler|revisar|pesquisar|documentação)",
        "ADMIN": r"(pagar|comprar|boleto|nota|fiscal|enviar|responder|email|e-mail)",
        "MEETING": r"(reunião|call|sync|feedback|alinhamento|daily)",
        "MAINTENANCE": r"(limpar|organizar|arrumar|lavar|louça|casa)",
    },
    "en": {
        "DEEP_WORK": r"(code|develop|refactor|build|create|programming)",
        "LEARNING": r"(study|learn|read|review|research|docs)",
        "ADMIN": r"(pay|buy|invoice|bill|send|reply|email|e-mail)",
        "MEETING": r"(meeting|call|sync|feedback|alignment|daily)",
        "MAINTENANCE": r"(clean|organize|fix|wash|dishes|house)",
    }
}

MODIFIERS = {
    "pt": {
        r"(rápido|vapt-vupt|fast)": IntensityModifier(duration_mult=0.5),
        r"(longo|detalhado|devagar)": IntensityModifier(duration_mult=1.6),
        r"(difícil|complexo|pesado|hard)": IntensityModifier(complexity_shift=1, energy_shift=1),
        r"(fácil|simples|bobagem|easy)": IntensityModifier(complexity_shift=-1, energy_shift=-1),
        r"(urgente|crítico)": IntensityModifier(energy_shift=1, duration_mult=0.8)
    },
    "en": {
        r"(quick|fast)": IntensityModifier(duration_mult=0.5),
        r"(hard|complex|heavy)": IntensityModifier(complexity_shift=1, energy_shift=1),
        r"(easy|simple)": IntensityModifier(complexity_shift=-1, energy_shift=-1),
    }
}

PRIORITY_MAP = {
    # ==========================================================
    # SÍMBOLOS
    # ==========================================================
    "!": Priority.LOW,
    "!!": Priority.MEDIUM,
    "!!!": Priority.HIGH,
    "!!!!": Priority.CRITICAL,

    # ==========================================================
    # PADRÃO TICKET / INCIDENT
    # ==========================================================
    "p0": Priority.CRITICAL,
    "p1": Priority.HIGH,
    "p2": Priority.MEDIUM,
    "p3": Priority.LOW,
    "p4": Priority.LOW,

    # ==========================================================
    # KEYWORDS — PORTUGUÊS
    # ==========================================================
    "urgente": Priority.CRITICAL,
    "crítico": Priority.CRITICAL,
    "critico": Priority.CRITICAL,

    "alta": Priority.HIGH,
    "prioridade alta": Priority.HIGH,

    "normal": Priority.MEDIUM,
    "médio": Priority.MEDIUM,
    "media": Priority.MEDIUM,
    "prioridade média": Priority.MEDIUM,

    "baixa": Priority.LOW,
    "baixo": Priority.LOW,
    "prioridade baixa": Priority.LOW,

    # ==========================================================
    # KEYWORDS — INGLÊS
    # ==========================================================
    "urgent": Priority.CRITICAL,
    "critical": Priority.CRITICAL,

    "high": Priority.HIGH,

    "medium": Priority.MEDIUM,

    "low": Priority.LOW,
    "minor": Priority.LOW,
}

DATE_WORDS = {

    # ==========================================================
    # HOJE
    # ==========================================================
    "hoje": "today",
    "ainda hoje": "today",
    "hoje mesmo": "today",

    # ==========================================================
    # AMANHÃ
    # ==========================================================
    "amanhã": "tomorrow",
    "amanha": "tomorrow",

    # ==========================================================
    # FUTURO CURTO
    # ==========================================================
    "depois": "later",
    "mais tarde": "later",
    "daqui a pouco": "soon",
    "em breve": "soon",

    # ==========================================================
    # DIAS RELATIVOS
    # ==========================================================
    "depois de amanhã": "day_after_tomorrow",
    "depois de amanha": "day_after_tomorrow",

    "ontem": "yesterday",
    "anteontem": "day_before_yesterday",

    # ==========================================================
    # SEMANA
    # ==========================================================
    "esta semana": "this_week",
    "semana que vem": "next_week",
    "na próxima semana": "next_week",

    # ==========================================================
    # MÊS
    # ==========================================================
    "este mês": "this_month",
    "esse mês": "this_month",
    "mês que vem": "next_month",

    # ==========================================================
    # PERÍODOS DO DIA
    # ==========================================================
    "hoje cedo": "today_morning",
    "hoje à tarde": "today_afternoon",
    "hoje a tarde": "today_afternoon",
    "hoje à noite": "today_night",
    "hoje a noite": "today_night",

    "amanhã cedo": "tomorrow_morning",
    "amanhã à tarde": "tomorrow_afternoon",
    "amanhã a tarde": "tomorrow_afternoon",
    "amanhã à noite": "tomorrow_night",
    "amanhã a noite": "tomorrow_night",
}

TASKS: list[str] = [

    # ==========================================================
    # DEEP WORK (Energia Alta / Complexidade Alta)
    # ==========================================================
    "Refatorar banco de dados do Axiom",
    "Implementar UseCase de Autenticação",
    "Codar engine de inferência semântica",
    "Desenvolver scheduler do Axiom 1h",
    "Refatorar módulo de persistência difícil",
    "Criar arquitetura do novo microservice",
    "Buildar pipeline de deploy CI/CD",
    "Programar parser de linguagem natural",
    "Criar protótipo do dashboard analítico",
    "Refatorar core do sistema urgente",

    # ==========================================================
    # LEARNING / RESEARCH (Energia Alta / Complexidade Média)
    # ==========================================================
    "Ler documentação do SQLAlchemy",
    "Pesquisar sobre Arquitetura Hexagonal",
    "Aprender Rust 1h",
    "Estudar event sourcing",
    "Revisar documentação do FastAPI",
    "Ler artigo sobre distributed systems",
    "Estudar padrões de arquitetura",
    "Pesquisar otimização de queries PostgreSQL",
    "Revisar conceitos de DDD",
    "Aprender sobre observabilidade",

    # ==========================================================
    # ADMIN / SHALLOW (Energia Baixa / Complexidade Baixa)
    # ==========================================================
    "Pagar mensalidade da VPS",
    "Responder e-mails da Elyon Gestão",
    "Comprar teclado novo",
    "Enviar feedback para o cliente",
    "Responder email rápido",
    "Enviar relatório financeiro",
    "Baixar notas fiscais",
    "Pagar boleto do domínio",
    "Organizar lista de tarefas",
    "Atualizar planilha de custos",
    "Responder mensagens do WhatsApp",

    # ==========================================================
    # REUNIÕES / SOCIAL (Energia Equilibrada / Complexidade Média)
    # ==========================================================
    "Sync com a Bel",
    "Call de alinhamento Davi Içamentos 30m",
    "Reunião de planejamento semanal",
    "Daily do projeto Axiom",
    "Reunião de feedback com cliente",
    "Call rápida com equipe",
    "Alinhamento técnico com backend",
    "Reunião de estratégia produto",
    "Sync de arquitetura com time",
    "Call de revisão sprint",

    # ==========================================================
    # MANUTENÇÃO / ROTINA (Energia Equilibrada / Complexidade Baixa)
    # ==========================================================
    "Organizar mesa de trabalho 10min",
    "Limpar o quarto",
    "Arrumar a cama",
    "Organizar arquivos do computador",
    "Limpar inbox do email",
    "Arrumar mesa rápido",
    "Organizar documentos pessoais",
    "Limpar área de trabalho do PC",
    "Revisar tarefas do dia",
    "Planejar agenda da semana",

    # ==========================================================
    # TESTES DE MODIFIERS
    # ==========================================================
    "Codar feature rápida",
    "Refatorar módulo complexo",
    "Implementar autenticação difícil",
    "Resolver bug crítico urgente",
    "Responder email rápido",
    "Ler documentação detalhada",
    "Estudar algoritmo difícil",
    "Organizar arquivos rápido",
    "Enviar relatório urgente",
    "Revisar código devagar",

    # ==========================================================
    # TESTES DE DURAÇÃO
    # ==========================================================
    "Codar API 2h",
    "Estudar Rust 45min",
    "Ler documentação 20m",
    "Call com cliente 1h",
    "Revisar PR 30m",
    "Organizar mesa 5min",

    # ==========================================================
    # TESTES DE CONTEXTO
    # ==========================================================
    "Codar endpoint de pagamentos @axiom",
    "Refatorar módulo financeiro @elyon",
    "Responder email cliente @elyon",
    "Estudar Rust @aprendizado",
    "Revisar arquitetura do Axiom @axiom",

    # ==========================================================
    # TESTES DE PRIORIDADE
    # ==========================================================
    "Corrigir bug crítico !!!",
    "Responder cliente importante !!",
    "Comprar cabo HDMI !",
    "Deploy urgente p1",
    "Revisar contrato p2",

    # ==========================================================
    # TESTES DE DATAS
    # ==========================================================
    "Pagar boleto hoje",
    "Enviar relatório amanhã",
    "Revisar arquitetura depois de amanhã",
    "Call cliente amanhã 30m",
    "Deploy produção hoje urgente",

    # ==========================================================
    # TAREFAS MISTAS (Para testar média semântica)
    # ==========================================================
    "Estudar e Codar protótipo",
    "Limpar e Organizar os boletos",
    "Pesquisar e implementar solução",
    "Ler documentação e refatorar código",
    "Estudar arquitetura e programar exemplo",
    "Organizar arquivos e enviar relatórios",
]

if __name__ == '__main__':

    semantics = SemanticInferencer(
        archetypes=ARCHETYPES,
        lexicons=LEXICONS,
        modifiers=MODIFIERS
    )

    engine = TaskLanguageEngine(
        semantic=semantics,
        contexts_map={"work": "ctx_1"},
        priority_map=PRIORITY_MAP,
        date_words=DATE_WORDS,
    )

    for t in TASKS:
        task = engine.infer(
            t,
            now=datetime.now()
        )

        print(task, end="\n\n")

        # break
