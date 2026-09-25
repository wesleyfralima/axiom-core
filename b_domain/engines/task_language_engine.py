import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from b_domain.value_objects.enums import EnergyLevel, Priority, TaskComplexity

# ==========================================================
# DOMAIN DATA
# ==========================================================


@dataclass(frozen=True, kw_only=True)
class InferredTaskFields:
    """Represents task fields inferred from natural language input."""

    title: str
    description: str = ""
    priority: Priority = Priority.MEDIUM
    energy: EnergyLevel = EnergyLevel.BALANCED
    complexity: TaskComplexity = TaskComplexity.MEDIUM
    duration: int = 30
    context_id: str | None = None
    due_date: datetime | None = None
    recurrence: str | None = None
    is_floating: bool = True


@dataclass(frozen=True, kw_only=True)
class InferredTaskData:
    """Represents inferred task attributes with confidence level."""

    energy: EnergyLevel
    complexity: TaskComplexity
    duration_minutes: int
    confidence: float


@dataclass(frozen=True, kw_only=True)
class Archetype:
    """Represents a task archetype with baseline attributes."""

    energy: EnergyLevel
    complexity: TaskComplexity
    base_duration: int
    weight: int = 1


@dataclass(frozen=True, kw_only=True)
class IntensityModifier:
    """Represents modifiers applied to adjust task intensity."""

    energy_shift: int = 0
    complexity_shift: int = 0
    duration_mult: float = 1.0


# ==========================================================
# TOKENS
# ==========================================================


class TokenType(StrEnum):
    """Types of tokens extracted from natural language parsing."""

    WORD = "WORD"
    DURATION = "DURATION"
    DATE = "DATE"
    PRIORITY = "PRIORITY"
    CONTEXT = "CONTEXT"
    TAG = "TAG"


@dataclass(frozen=True, kw_only=True)
class Token:
    """Represents a parsed token with type and value."""

    type: TokenType
    value: str


# ==========================================================
# TOKENIZER
# ==========================================================


class TaskTokenizer:
    """Tokenizer for parsing natural language task descriptions.

    Splits text into tokens representing contexts, tags, priorities,
    durations, dates, or generic words. This enables downstream
    processing of user input into structured task data.
    """

    # Regex pattern to detect durations (e.g., "30m", "2 h", "45 min")
    DURATION_PATTERN: re.Pattern[str] = re.compile(r"^(\d+)(h|min|m)$", re.I)

    def __init__(self, priorities_list: list[str], date_words: dict[str, str]):
        """Initialize the tokenizer with domain-specific keywords.

        Args:
            priorities_list (list[str]): List of recognized priority keywords.
            date_words (dict[str, str]): Mapping of recognized
                date words (e.g., "tomorrow").
        """
        self.priorities = {p.lower() for p in priorities_list}
        self.date_words = date_words

    def tokenize(self, text: str) -> list[Token]:
        """Convert input text into a list of tokens.

        The tokenizer applies the following rules:
        - Words starting with `@` → Context tokens
        - Words starting with `#` → Tag tokens
        - Matches in priorities list → Priority tokens
        - Matches duration regex → Duration tokens
        - Matches date words → Date tokens
        - Otherwise → Generic word tokens

        Args:
            text (str): Raw input text to tokenize.

        Returns:
            List[Token]: List of parsed tokens with type and value.
        """

        tokens: list[Token] = []
        parts: list[str] = text.split()

        for part in parts:
            # Strip trailing common punctuation (. , ! ?) unless it's a priority symbol
            clean_part: str = part
            if not part.startswith("!"):
                clean_part = re.sub(r"[.,!?\s]+$", "", part)

            lower: str = clean_part.lower()

            if clean_part.startswith("@"):
                tokens.append(
                    Token(
                        type=TokenType.CONTEXT,
                        value=clean_part[1:],
                    )
                )
                continue

            if clean_part.startswith("#"):
                tokens.append(
                    Token(
                        type=TokenType.TAG,
                        value=clean_part[1:],
                    )
                )
                continue

            if lower in self.priorities:
                tokens.append(
                    Token(
                        type=TokenType.PRIORITY,
                        value=lower,
                    )
                )
                continue

            if self.DURATION_PATTERN.match(lower):
                tokens.append(
                    Token(
                        type=TokenType.DURATION,
                        value=lower,
                    )
                )
                continue

            # Date keyword (e.g., "tomorrow", "today")
            if lower in self.date_words:
                tokens.append(
                    Token(
                        type=TokenType.DATE,
                        value=lower,
                    )
                )
                continue

            tokens.append(
                Token(
                    type=TokenType.WORD,
                    value=clean_part,
                )
            )

        return tokens


# ==========================================================
# AST
# ==========================================================


@dataclass(frozen=True, kw_only=True)
class TaskNode:
    """Represents the abstract syntax tree (AST) node for a parsed task.

    Attributes:
        title_words (List[str]): Words that form the task title.
        duration (Optional[int]): Task duration in minutes.
        due (Optional[str]): Due date keyword (e.g., "tomorrow").
        context (Optional[str]): Context identifier (e.g., "@work").
        priority (Optional[str]): Priority keyword (e.g., "high").
        tags (Optional[List[str]]): List of tag keywords (e.g., "#urgent").
    """

    title_words: list[str]

    duration: int | None = None
    due: str | None = None

    context: str | None = None
    priority: str | None = None

    tags: list[str] | None = None


# ==========================================================
# PARSER
# ==========================================================


class TaskParser:
    """Parser that converts tokens into a structured TaskNode."""

    def parse(self, tokens: list[Token]) -> TaskNode:
        """Parse a list of tokens into a TaskNode.

        Applies rules to extract title words, duration, due date,
        context, priority, and tags from the token stream.

        Args:
            tokens (List[Token]): List of tokens produced by the tokenizer.

        Returns:
            TaskNode: Structured representation of the parsed task.
        """

        title_words: list[str] = []
        duration: int | None = None
        due: str | None = None
        context: str | None = None
        priority: str | None = None
        tags: list[str] = []

        for token in tokens:
            match token.type:
                case TokenType.WORD:
                    title_words.append(token.value)
                case TokenType.DURATION:
                    duration = self._parse_duration(token.value)
                case TokenType.DATE:
                    due = token.value
                case TokenType.CONTEXT:
                    context = token.value
                case TokenType.PRIORITY:
                    priority = token.value
                case TokenType.TAG:
                    tags.append(token.value)

        return TaskNode(
            title_words=title_words,
            duration=duration,
            due=due,
            context=context,
            priority=priority,
            tags=tags,
        )

    @staticmethod
    def _parse_duration(value: str) -> int | None:
        """Convert duration tokens into minutes.

        Supported formats:
        - "2h" → 120 minutes
        - "30m" → 30 minutes
        - "45min" → 45 minutes

        Args:
            value (str): Raw duration token.

        Returns:
            Optional[int]: Duration in minutes, or None if invalid.
        """

        if value.endswith("h"):
            return int(value[:-1]) * 60

        if value.endswith("min"):
            return int(value[:-3])

        if value.endswith("m"):
            return int(value[:-1])

        return None


# ==========================================================
# SEMANTIC INFERENCE
# ==========================================================

# Archetypes
type ArchetypesRawDict = dict[str, Archetype]  # {keyword -> Archetype}

# Lexicons
type LexiconType = dict[str, re.Pattern]  # {name -> compiled regex}
type LexiconRawDict = dict[str, dict[str, str]]  # language -> {name -> regex string}
type LexiconCompiledDict = dict[str, LexiconType]  # language -> {name -> compiled regx}

# Modifiers
type ModifierType = dict[re.Pattern, IntensityModifier]  # {compiled regex -> modifier}
type ModifierRawDict = dict[
    str, dict[str, IntensityModifier]
]  # language -> {pattern string -> modifier}
type ModifierCompiledDict = dict[
    str, ModifierType
]  # lang -> {compiled regex -> modifier}

# Priorities
type PriorityMapType = dict[str, Priority]  # keyword/symbol -> Priority enum

# Contexts
type ContextMapType = dict[str, str]  # context keyword -> normalized context id

# Dates
type DateWordsMapType = dict[str, str]  # date keyword -> normalized token


class SemanticInferencer:
    """Infers task attributes (energy, complexity, duration) from text.

    Uses archetypes, lexicons, and intensity modifiers to semantically
    interpret task titles. This allows the system to estimate cognitive
    load and effort based on natural language input.
    """

    def __init__(
        self,
        archetypes: ArchetypesRawDict,
        lexicons: LexiconRawDict,
        modifiers: ModifierRawDict,
        default_lang: str = "pt",
    ):
        """Initialize the semantic inferencer.

        Args:
            archetypes (Dict[str, Archetype]): Mapping of
                archetype names to baseline attributes.
            lexicons (Dict[str, Dict[str, str]]): Language-specific keyword patterns.
            modifiers (Dict[str, Dict[str, IntensityModifier]]): Language-specific
                modifiers.
            default_lang (str): Default language for inference (default: "pt").
        """

        self.archetypes = archetypes
        self.default_lang = default_lang

        self.lexicons = self._compile_patterns(lexicons)
        self.modifiers = self._compile_modifiers(modifiers)

    @staticmethod
    def _compile_patterns(lexicons: LexiconRawDict) -> LexiconCompiledDict:
        """Compile lexicon patterns into regex objects."""

        compiled: LexiconCompiledDict = {}

        for lang, entries in lexicons.items():
            compiled[lang] = {}

            for name, pattern in entries.items():
                compiled[lang][name] = re.compile(rf"\b{pattern}\b", re.IGNORECASE)

        return compiled

    @staticmethod
    def _compile_modifiers(modifiers: ModifierRawDict) -> ModifierCompiledDict:
        """Compile modifier patterns into regex objects."""

        compiled: ModifierCompiledDict = {}

        for lang, entries in modifiers.items():
            compiled[lang] = {}

            for pattern, modifier in entries.items():
                compiled[lang][re.compile(rf"\b{pattern}\b", re.IGNORECASE)] = modifier

        return compiled

    def infer(self, title: str, lang: str) -> InferredTaskData:
        """Infer task attributes from a title.

        Matches lexicon patterns against the task title to identify
        archetypes. Applies modifiers if intensity keywords are found.
        Produces an `InferredTaskData` object with confidence scoring.

        Args:
            title (str): Task title text.
            lang (str): Language code (e.g., "pt", "en").

        Returns:
            InferredTaskData: Estimated attributes
                (energy, complexity, duration, confidence).
        """

        title_lower: str = title.lower()
        lexicon: LexiconType = self.lexicons.get(lang, {})
        matches: list[Archetype] = []

        # Match archetypes
        for name, pattern in lexicon.items():
            if pattern.search(title_lower):
                arch = self.archetypes.get(name)
                if arch:
                    matches.append(arch)

        # Default fallback if no matches
        if not matches:
            return InferredTaskData(
                energy=EnergyLevel.BALANCED,
                complexity=TaskComplexity.MEDIUM,
                duration_minutes=30,
                confidence=0.1,
            )

        # Weighted averages
        total_weight: int = sum(a.weight for a in matches)
        energy: float = sum(a.energy.value * a.weight for a in matches) / total_weight
        complexity: float = (
            sum(a.complexity.value * a.weight for a in matches) / total_weight
        )
        duration: float = (
            sum(a.base_duration * a.weight for a in matches) / total_weight
        )

        # Apply modifiers
        mods: ModifierType = self.modifiers.get(lang, {})
        for pattern, mod in mods.items():
            if pattern.search(title_lower):
                energy += mod.energy_shift
                complexity += mod.complexity_shift
                duration *= mod.duration_mult

        # Clamp values to valid ranges
        energy_enum = EnergyLevel(max(1, min(3, round(energy))))
        complexity_enum = TaskComplexity(max(1, min(5, round(complexity))))

        return InferredTaskData(
            energy=energy_enum,
            complexity=complexity_enum,
            duration_minutes=int(duration),
            confidence=min(1.0, total_weight / 5),
        )


# ==========================================================
# INTERPRETER
# ==========================================================


class TaskInterpreter:
    """Interprets parsed task nodes into structured task fields.

    Combines semantic inference with contextual maps (priority, context,
    date words) to produce a fully enriched `InferredTaskFields` object.
    """

    def __init__(
        self,
        semantic: SemanticInferencer,
        priority_map: PriorityMapType,
        contexts_map: ContextMapType,
        dates_map: DateWordsMapType,
    ):
        """Initialize the task interpreter.

        Args:
            semantic (SemanticInferencer): Semantic inference engine.
            priority_map (dict[str, Any]): Mapping of priority
                keywords/symbols to Priority enum.
            contexts_map (Dict[str, str]): Mapping of context
                keywords to normalized context IDs.
            dates_map (Dict[str, str]): Mapping of date keywords to normalized tokens.
        """
        self.semantic = semantic
        self.priority_map = priority_map
        self.contexts_map = contexts_map
        self.dates_map = dates_map

    def interpret(self, node: TaskNode, now: datetime, lang: str) -> InferredTaskFields:
        """Interpret a parsed TaskNode into structured task fields.

        Steps:
        1. Join title words into a full task title.
        2. Use semantic inference to estimate energy, complexity, and duration.
        3. Resolve explicit duration if provided, otherwise use inferred duration.
        4. Normalize and resolve due dates using date map.
        5. Map priority keywords to Priority enum.
        6. Map context keywords to normalized context IDs.

        Args:
            node (TaskNode): Parsed AST node representing the task.
            now (datetime): Current timestamp for relative date resolution.
            lang (str): Language code (e.g., "pt", "en").

        Returns:
            InferredTaskFields: Fully enriched task fields with
                semantic and contextual data.
        """

        # Build title from words
        title: str = " ".join(node.title_words)

        # Infer semantic attributes
        semantic_data: InferredTaskData = self.semantic.infer(title, lang)

        # Use explicit duration if available, otherwise semantic estimate
        duration: int = node.duration or semantic_data.duration_minutes

        # Resolve due date if present
        due_date: datetime | None = None
        if node.due:
            normalized: str | None = self.dates_map.get(node.due.lower())
            if normalized:
                due_date = self.resolve_relative_date(normalized, now)

        # Map priority keyword to Priority enum (default: MEDIUM)
        k: str = str(node.priority)
        priority: Priority = self.priority_map.get(k, Priority.MEDIUM)

        # Map context keyword to normalized context ID
        context: str | None = None
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
        """Resolve relative date tokens into absolute datetime values.

        Supported tokens:
        - "today" → End of current day
        - "tomorrow" → End of next day
        - "day_after_tomorrow" → End of day two days ahead
        - "yesterday" → End of previous day
        - "day_before_yesterday" → End of day two days before
        - "soon" → Two hours ahead
        - "later" → Six hours ahead
        - "this_week" → Three days ahead
        - "next_week" → Seven days ahead
        - "this_month" → Fifteen days ahead
        - "next_month" → Thirty days ahead
        - "today_morning" → Today at 12:00
        - "today_afternoon" → Today at 18:00
        - "today_night" → Today at 23:59
        - "tomorrow_morning" → Tomorrow at 12:00
        - "tomorrow_afternoon" → Tomorrow at 18:00
        - "tomorrow_night" → Tomorrow at 23:59
        - "next_quarter" → End of day 90 days ahead
        - "next_year" → End of day 365 days ahead

        Args:
            token (str): Normalized relative date keyword.
            now (datetime): Current timestamp.

        Returns:
            Optional[datetime]: Resolved datetime value, or None if unsupported.
        """

        def end_of_day(dt: datetime) -> datetime:
            return dt.replace(hour=23, minute=59, second=59, microsecond=0)

        match token:
            # Absolute days
            case "today":
                return end_of_day(now)
            case "tomorrow":
                return end_of_day(now + timedelta(days=1))
            case "day_after_tomorrow":
                return end_of_day(now + timedelta(days=2))
            case "yesterday":
                return end_of_day(now - timedelta(days=1))
            case "day_before_yesterday":
                return end_of_day(now - timedelta(days=2))

            # Short-term future
            case "soon":
                return now + timedelta(hours=2)
            case "later":
                return now + timedelta(hours=6)

            # Week / month
            case "this_week":
                return now + timedelta(days=3)
            case "next_week":
                return now + timedelta(days=7)
            case "this_month":
                return now + timedelta(days=15)
            case "next_month":
                return now + timedelta(days=30)

            # Day periods
            case "today_morning":
                return now.replace(hour=12, minute=0, second=0, microsecond=0)
            case "today_afternoon":
                return now.replace(hour=18, minute=0, second=0, microsecond=0)
            case "today_night":
                return end_of_day(now)
            case "tomorrow_morning":
                return (now + timedelta(days=1)).replace(
                    hour=12, minute=0, second=0, microsecond=0
                )
            case "tomorrow_afternoon":
                return (now + timedelta(days=1)).replace(
                    hour=18, minute=0, second=0, microsecond=0
                )
            case "tomorrow_night":
                return end_of_day(now + timedelta(days=1))

            # Long-term
            case "next_quarter":
                return end_of_day(now + timedelta(days=90))
            case "next_year":
                return end_of_day(now + timedelta(days=365))

        return None


# ==========================================================
# ENGINE
# ==========================================================


class TaskLanguageEngine:
    """High-level engine for natural language task inference.

    Orchestrates the full pipeline:
    1. Tokenization of raw text into structured tokens.
    2. Parsing tokens into an AST (`TaskNode`).
    3. Interpreting the AST into enriched task fields
       using semantic inference, priority maps, contexts, and date words.
    """

    def __init__(
        self,
        semantic: SemanticInferencer,
        priority_map: dict[str, Any],
        date_words: dict[str, str],
        contexts_map: dict[str, str],
    ):
        """Initialize the task language engine.

        Args:
            semantic (SemanticInferencer): Semantic inference engine
                for estimating energy, complexity, and duration.
            priority_map (dict[str, Any]): Mapping of priority
                keywords/symbols to Priority enum.
            date_words (Dict[str, str]): Mapping of date keywords to normalized tokens.
            contexts_map (Dict[str, str]): Mapping of context
                keywords to normalized context IDs.
        """

        # Tokenizer: splits raw text into tokens (priority, date, context, etc.)
        self.tokenizer: TaskTokenizer = TaskTokenizer(
            list(priority_map.keys()), date_words
        )

        # Parser: converts tokens into a TaskNode (AST)
        self.parser: TaskParser = TaskParser()

        # Interpreter: enriches TaskNode into InferredTaskFields
        self.interpreter: TaskInterpreter = TaskInterpreter(
            semantic,
            priority_map,
            contexts_map,
            date_words,
        )

    def infer(self, text: str, now: datetime, lang: str = "pt") -> InferredTaskFields:
        """Infer structured task fields from raw text.

        Steps:
        1. Tokenize the input text.
        2. Parse tokens into a TaskNode.
        3. Interpret the TaskNode into InferredTaskFields.

        Args:
            text (str): Raw natural language task description.
            now (datetime): Current timestamp for relative date resolution.
            lang (str, optional): Language code (default: "pt").

        Returns:
            InferredTaskFields: Fully enriched task fields including
            title, priority, energy, complexity, duration, context, and due date.
        """

        # Tokenize raw text into structured tokens
        tokens: list[Token] = self.tokenizer.tokenize(text)

        # Parse tokens into AST node
        ast: TaskNode = self.parser.parse(tokens)

        # Interpret AST into enriched task fields
        return self.interpreter.interpret(ast, now, lang)


def load_language_engine(config_path: Path) -> TaskLanguageEngine:
    """Load configuration from TOML and bootstrap the TaskLanguageEngine instance."""

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    # 1. Parse Archetypes mapping strings to native Domain Enums
    archetypes: dict[str, Archetype] = {}
    for name, arc in data["archetypes"].items():
        archetypes[name] = Archetype(
            energy=EnergyLevel[arc["energy"]],
            complexity=TaskComplexity[arc["complexity"]],
            base_duration=arc["base_duration"],
            weight=arc.get("weight", 1),
        )

    # 2. Parse Intensity Modifiers
    modifiers: dict[str, dict[str, IntensityModifier]] = {}
    for lang, entries in data["modifiers"].items():
        modifiers[lang] = {
            pattern: IntensityModifier(
                energy_shift=mod.get("energy_shift", 0),
                complexity_shift=mod.get("complexity_shift", 0),
                duration_mult=float(mod.get("duration_mult", 1.0)),
            )
            for pattern, mod in entries.items()
        }

    # 3. Parse Priority Map to Enums
    priority_map = {key: Priority[val] for key, val in data["priority_map"].items()}

    # 4. Flatten and merge multi-language date mappings
    date_words: dict[str, str] = {}
    for lang_dict in data["date_words"].values():
        date_words.update(lang_dict)

    # 5. Build pipeline infrastructure instances
    semantic_inferencer = SemanticInferencer(
        archetypes=archetypes,
        lexicons=data["lexicons"],
        modifiers=modifiers,
    )

    return TaskLanguageEngine(
        semantic=semantic_inferencer,
        priority_map=priority_map,
        date_words=date_words,
        contexts_map={"work": "ctx_1"},  # Dynamic map injected by user context
    )


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


if __name__ == "__main__":

    project_root: Path = Path(__file__).parent.parent.parent.parent
    toml_path: Path = project_root / "task_lang_engine_conf.toml"
    engine = load_language_engine(toml_path)

    for t in TASKS:
        task = engine.infer(t, now=datetime.now())

        print(task, end="\n")
