import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, TypeAlias

from b_domain.value_objects.enums import EnergyLevel, Priority, TaskComplexity


# ==========================================================
# DOMAIN DATA
# ==========================================================

@dataclass(frozen=True)
class InferredTaskFields:
    """Represents task fields inferred from natural language input."""
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
    """Represents inferred task attributes with confidence level."""
    energy: EnergyLevel
    complexity: TaskComplexity
    duration_minutes: int
    confidence: float


@dataclass(frozen=True)
class Archetype:
    """Represents a task archetype with baseline attributes."""
    energy: EnergyLevel
    complexity: TaskComplexity
    base_duration: int
    weight: int = 1


@dataclass(frozen=True)
class IntensityModifier:
    """Represents modifiers applied to adjust task intensity."""
    energy_shift: int = 0
    complexity_shift: int = 0
    duration_mult: float = 1.0


# ==========================================================
# TOKENS
# ==========================================================

class TokenType(Enum):
    """Types of tokens extracted from natural language parsing."""
    WORD = "WORD"
    DURATION = "DURATION"
    DATE = "DATE"
    PRIORITY = "PRIORITY"
    CONTEXT = "CONTEXT"
    TAG = "TAG"


@dataclass
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

    # Regex pattern to detect durations (e.g., "30m", "2h", "45min")
    DURATION_PATTERN: re.Pattern[str] = re.compile(r"(\d+)(h|m|min)", re.I)

    def __init__(self, priorities_list: list[str], date_words: dict[str, str]):
        """Initialize the tokenizer with domain-specific keywords.

        Args:
            priorities_list (list[str]): List of recognized priority keywords.
            date_words (dict[str, str]): Mapping of recognized date words (e.g., "tomorrow").
        """
        self.priorities = priorities_list
        self.date_words = date_words

    def tokenize(self, text: str) -> List[Token]:
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

            lower: str = part.lower()

            # Context marker
            if part.startswith("@"):
                tokens.append(Token(TokenType.CONTEXT, part[1:]))
                continue

            # Tag marker
            if part.startswith("#"):
                tokens.append(Token(TokenType.TAG, part[1:]))
                continue

            # Priority keyword
            if part in self.priorities:
                tokens.append(Token(TokenType.PRIORITY, part))
                continue

            # Duration pattern (e.g., "30m", "2h")
            if self.DURATION_PATTERN.match(part):
                tokens.append(Token(TokenType.DURATION, part))
                continue

            # Date keyword (e.g., "tomorrow", "today")
            if lower in self.date_words:
                tokens.append(Token(TokenType.DATE, lower))
                continue

            # Default: generic word
            tokens.append(Token(TokenType.WORD, part))

        return tokens


# ==========================================================
# AST
# ==========================================================

@dataclass
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
    """Parser that converts tokens into a structured TaskNode."""

    def parse(self, tokens: List[Token]) -> TaskNode:
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

        if value.endswith("m"):
            return int(value[:-1])

        if value.endswith("min"):
            return int(value[:-3])

        return None


# ==========================================================
# SEMANTIC INFERENCE
# ==========================================================

# Archetypes
ArchetypesRawDict: TypeAlias = Dict[str, Archetype]  # {keyword -> Archetype}

# Lexicons
LexiconType: TypeAlias = Dict[str, re.Pattern]  # {name -> compiled regex}
LexiconRawDict: TypeAlias = Dict[str, Dict[str, str]]  # language -> {name -> regex string}
LexiconCompiledDict: TypeAlias = Dict[str, LexiconType]  # language -> {name -> compiled regex}

# Modifiers
ModifierType: TypeAlias = Dict[re.Pattern, IntensityModifier]  # {compiled regex -> modifier}
ModifierRawDict: TypeAlias = Dict[str, Dict[str, IntensityModifier]]  # language -> {pattern string -> modifier}
ModifierCompiledDict: TypeAlias = Dict[str, ModifierType]  # lang -> {compiled regex -> modifier}

# Priorities
PriorityMapType: TypeAlias = Dict[str, Priority]  # keyword/symbol -> Priority enum

# Contexts
ContextMapType: TypeAlias = Dict[str, str]  # context keyword -> normalized context id

# Dates
DateWordsMapType: TypeAlias = Dict[str, str]  # date keyword -> normalized token


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
            default_lang: str = "pt"
    ):
        """Initialize the semantic inferencer.

        Args:
            archetypes (Dict[str, Archetype]): Mapping of archetype names to baseline attributes.
            lexicons (Dict[str, Dict[str, str]]): Language-specific keyword patterns.
            modifiers (Dict[str, Dict[str, IntensityModifier]]): Language-specific modifiers.
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
                compiled[lang][name] = re.compile(
                    fr"\b{pattern}\b",
                    re.IGNORECASE
                )

        return compiled

    @staticmethod
    def _compile_modifiers(modifiers: ModifierRawDict) -> ModifierCompiledDict:
        """Compile modifier patterns into regex objects."""

        compiled: ModifierCompiledDict = {}

        for lang, entries in modifiers.items():

            compiled[lang] = {}

            for pattern, modifier in entries.items():
                compiled[lang][
                    re.compile(fr"\b{pattern}\b", re.IGNORECASE)
                ] = modifier

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
            InferredTaskData: Estimated attributes (energy, complexity, duration, confidence).
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
                EnergyLevel.BALANCED,
                TaskComplexity.MEDIUM,
                30,
                0.1
            )

        # Weighted averages
        total_weight: int = sum(a.weight for a in matches)
        energy: float | EnergyLevel = sum(a.energy.value * a.weight for a in matches) / total_weight
        complexity: float | TaskComplexity = sum(a.complexity.value * a.weight for a in matches) / total_weight
        duration: float = sum(a.base_duration * a.weight for a in matches) / total_weight

        # Apply modifiers
        mods: ModifierType = self.modifiers.get(lang, {})
        for pattern, mod in mods.items():
            if pattern.search(title_lower):
                energy += mod.energy_shift
                complexity += mod.complexity_shift
                duration *= mod.duration_mult

        # Clamp values to valid ranges
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
            priority_map (dict[str, Any]): Mapping of priority keywords/symbols to Priority enum.
            contexts_map (Dict[str, str]): Mapping of context keywords to normalized context IDs.
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
            InferredTaskFields: Fully enriched task fields with semantic and contextual data.
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
        priority: Priority = self.priority_map.get(node.priority, Priority.MEDIUM)

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
    def resolve_relative_date(token: str, now: datetime) -> Optional[datetime]:
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
                return (now + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
            case "tomorrow_afternoon":
                return (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
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
            date_words: Dict[str, str],
            contexts_map: Dict[str, str],
    ):
        """Initialize the task language engine.

        Args:
            semantic (SemanticInferencer): Semantic inference engine for estimating energy, complexity, and duration.
            priority_map (dict[str, Any]): Mapping of priority keywords/symbols to Priority enum.
            date_words (Dict[str, str]): Mapping of date keywords to normalized tokens.
            contexts_map (Dict[str, str]): Mapping of context keywords to normalized context IDs.
        """

        # Tokenizer: splits raw text into tokens (priority, date, context, etc.)
        self.tokenizer: TaskTokenizer = TaskTokenizer(list(priority_map.keys()), date_words)

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


# ==========================================================
# USEFUL VARIABLES (TODO: MIGRATE FROM HERE TO A BETTER FILE)
# ==========================================================

# 1. Definimos os Arquétipos (A "Alma" da tarefa)
ARCHETYPES: ArchetypesRawDict = {
    "DEEP_WORK": Archetype(EnergyLevel.HIGH, TaskComplexity.VERY_HIGH, 60, weight=3),
    "LEARNING": Archetype(EnergyLevel.HIGH, TaskComplexity.MEDIUM, 45, weight=2),
    "ADMIN": Archetype(EnergyLevel.LOW, TaskComplexity.VERY_LOW, 15),
    "MEETING": Archetype(EnergyLevel.BALANCED, TaskComplexity.MEDIUM, 30),
    "MAINTENANCE": Archetype(EnergyLevel.BALANCED, TaskComplexity.LOW, 20),
    "CREATIVE": Archetype(EnergyLevel.HIGH, TaskComplexity.HIGH, 50, weight=2),
    "COMMUNICATION": Archetype(EnergyLevel.BALANCED, TaskComplexity.MEDIUM, 25),
    "PLANNING": Archetype(EnergyLevel.BALANCED, TaskComplexity.HIGH, 40),
    "SUPPORT": Archetype(EnergyLevel.LOW, TaskComplexity.MEDIUM, 20),
}

# 2. Léxico por Idioma
LEXICONS: LexiconRawDict = {
    "pt": {
        "DEEP_WORK": r"(codar|programar|desenvolver|refatorar|build|criar)",
        "LEARNING": r"(estudar|aprender|ler|revisar|pesquisar|documentação)",
        "ADMIN": r"(pagar|comprar|boleto|nota|fiscal|enviar|responder|email|e-mail)",
        "MEETING": r"(reunião|call|sync|feedback|alinhamento|daily)",
        "MAINTENANCE": r"(limpar|organizar|arrumar|lavar|louça|casa)",
        "CREATIVE": r"(escrever|redigir|criar|design|desenhar|pintar|ilustrar)",
        "COMMUNICATION": r"(ligar|telefonar|mensagem|comunicar|avisar|informar)",
        "PLANNING": r"(planejar|estratégia|agenda|cronograma|organizar|mapear)",
        "SUPPORT": r"(ajudar|suporte|assistir|auxiliar|colaborar)",
    },
    "en": {
        "DEEP_WORK": r"(code|develop|refactor|build|create|programming)",
        "LEARNING": r"(study|learn|read|review|research|docs)",
        "ADMIN": r"(pay|buy|invoice|bill|send|reply|email|e-mail)",
        "MEETING": r"(meeting|call|sync|feedback|alignment|daily)",
        "MAINTENANCE": r"(clean|organize|fix|wash|dishes|house)",
        "CREATIVE": r"(write|draft|create|design|draw|paint|illustrate)",
        "COMMUNICATION": r"(call|phone|message|communicate|notify|inform)",
        "PLANNING": r"(plan|strategy|schedule|organize|map|arrange)",
        "SUPPORT": r"(help|support|assist|aid|collaborate)",
    }
}

MODIFIERS: ModifierRawDict = {
    "pt": {
        r"(rápido|vapt-vupt|fast)": IntensityModifier(duration_mult=0.5),
        r"(longo|detalhado|devagar)": IntensityModifier(duration_mult=1.6),
        r"(difícil|complexo|pesado|hard)": IntensityModifier(complexity_shift=1, energy_shift=1),
        r"(fácil|simples|bobagem|easy)": IntensityModifier(complexity_shift=-1, energy_shift=-1),
        r"(urgente|crítico)": IntensityModifier(energy_shift=1, duration_mult=0.8),
        "(rápida reunião|call curto)": IntensityModifier(duration_mult=0.7),
        r"(brainstorm|ideação)": IntensityModifier(energy_shift=1, complexity_shift=1),
    },
    "en": {
        r"(quick|fast)": IntensityModifier(duration_mult=0.5),
        r"(hard|complex|heavy)": IntensityModifier(complexity_shift=1, energy_shift=1),
        r"(easy|simple)": IntensityModifier(complexity_shift=-1, energy_shift=-1),
        r"(quick meeting|short call)": IntensityModifier(duration_mult=0.7),
        r"(brainstorm|ideation)": IntensityModifier(energy_shift=1, complexity_shift=1),
    }
}

PRIORITY_MAP: PriorityMapType = {
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
    "critico": Priority.CRITICAL,
    "crítico": Priority.CRITICAL,
    "urgente": Priority.CRITICAL,

    "alta": Priority.HIGH,
    "prioridade alta": Priority.HIGH,

    "media": Priority.MEDIUM,
    "médio": Priority.MEDIUM,
    "normal": Priority.MEDIUM,
    "prioridade média": Priority.MEDIUM,

    "baixa": Priority.LOW,
    "baixo": Priority.LOW,
    "prioridade baixa": Priority.LOW,

    # ==========================================================
    # KEYWORDS — INGLÊS
    # ==========================================================
    "blocker": Priority.CRITICAL,
    "critical": Priority.CRITICAL,
    "urgent": Priority.CRITICAL,

    "high": Priority.HIGH,
    "important": Priority.HIGH,

    "medium": Priority.MEDIUM,
    "standard": Priority.MEDIUM,

    "low": Priority.LOW,
    "minor": Priority.LOW,
    "optional": Priority.LOW,
}

PT_DATE_WORDS: DateWordsMapType = {
    # ==========================================================
    # HOJE
    # ==========================================================
    "hoje": "today",
    "ainda hoje": "today",
    "hoje mesmo": "today",
    "hoje cedo": "today_morning",
    "hoje à tarde": "today_afternoon",
    "hoje a tarde": "today_afternoon",
    "hoje à noite": "today_night",
    "hoje a noite": "today_night",
    "esta manhã": "today_morning",
    "esta tarde": "today_afternoon",
    "esta noite": "today_night",

    # ==========================================================
    # AMANHÃ
    # ==========================================================
    "amanhã": "tomorrow",
    "amanha": "tomorrow",
    "amanhã cedo": "tomorrow_morning",
    "amanhã à tarde": "tomorrow_afternoon",
    "amanhã a tarde": "tomorrow_afternoon",
    "amanhã à noite": "tomorrow_night",
    "amanhã a noite": "tomorrow_night",
    "próxima manhã": "tomorrow_morning",
    "próxima tarde": "tomorrow_afternoon",
    "próxima noite": "tomorrow_night",

    # ==========================================================
    # DIAS RELATIVOS
    # ==========================================================
    "depois de amanhã": "day_after_tomorrow",
    "depois de amanha": "day_after_tomorrow",
    "ontem": "yesterday",
    "anteontem": "day_before_yesterday",

    # ==========================================================
    # FUTURO CURTO
    # ==========================================================
    "depois": "later",
    "mais tarde": "later",
    "daqui a pouco": "soon",
    "em breve": "soon",

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
    # LONGO PRAZO
    # ==========================================================
    "próximo trimestre": "next_quarter",
    "próximo ano": "next_year",
    "next quarter": "next_quarter",
    "next year": "next_year",
}

EN_DATE_WORDS: DateWordsMapType = {
    # ==========================================================
    # TODAY
    # ==========================================================
    "today": "today",
    "still today": "today",
    "today itself": "today",
    "this morning": "today_morning",
    "this afternoon": "today_afternoon",
    "this evening": "today_night",
    "today morning": "today_morning",
    "today afternoon": "today_afternoon",
    "today night": "today_night",

    # ==========================================================
    # TOMORROW
    # ==========================================================
    "tomorrow": "tomorrow",
    "tomorrow morning": "tomorrow_morning",
    "tomorrow afternoon": "tomorrow_afternoon",
    "tomorrow evening": "tomorrow_night",
    "next morning": "tomorrow_morning",
    "next afternoon": "tomorrow_afternoon",
    "next night": "tomorrow_night",

    # ==========================================================
    # RELATIVE DAYS
    # ==========================================================
    "day after tomorrow": "day_after_tomorrow",
    "yesterday": "yesterday",
    "day before yesterday": "day_before_yesterday",

    # ==========================================================
    # SHORT FUTURE
    # ==========================================================
    "later": "later",
    "soon": "soon",
    "in a while": "soon",
    "shortly": "soon",

    # ==========================================================
    # WEEK
    # ==========================================================
    "this week": "this_week",
    "next week": "next_week",

    # ==========================================================
    # MONTH
    # ==========================================================
    "this month": "this_month",
    "next month": "next_month",

    # ==========================================================
    # LONG TERM
    # ==========================================================
    "next quarter": "next_quarter",
    "next year": "next_year",
}

DATE_WORDS: DateWordsMapType = PT_DATE_WORDS | EN_DATE_WORDS

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
