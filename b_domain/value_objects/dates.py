from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from a_core.exceptions import ValidationException


class DateKind(str, Enum):
    """
    Define a natureza semântica da data.
    """
    FIXED = "fixed"  # Um instante absoluto (ex: Reunião Global às 14:00 UTC)
    FLOATING = "floating"  # Um horário de relógio local (ex: Acordar às 07:00 da manhã)


@dataclass(frozen=True, order=True)
class AxiomDate:
    """
    Primitiva temporal universal da aplicação Axiom.
    Substitui o uso cru de datetime para garantir consistência de Timezone.
    """

    # Value é usado para ordenação (sort). Por isso, vem primeiro.
    # Se FIXED: deve ser aware (preferencialmente UTC).
    # Se FLOATING: deve ser naive.
    value: datetime | None

    kind: DateKind = field(compare=False)

    # O timezone de origem (para floating) ou de exibição preferencial (para fixed)
    timezone: Optional[str] = field(default=None, compare=False)
    """
    The IANA timezone identifier (e.g., "America/Sao_Paulo") 
    used as the anchor to interpret the due_date and handle 
    Daylight Saving Time (DST) changes accurately.
    """

    def __post_init__(self):
        """Garante a integridade dos dados na criação."""

        if self.value is None:
            return

        # Validação de Floating
        if self.kind == DateKind.FLOATING:
            if self.value.tzinfo is not None:
                raise ValidationException("Floating dates must store a Naive datetime.")
            if not self.timezone:
                raise ValidationException("Floating dates require a valid Timezone Name.")

        # Validação de Fixed
        if self.kind == DateKind.FIXED:
            if self.value.tzinfo is None:
                raise ValidationException("Fixed dates must store a Timezone-Aware datetime.")

        self._extra_validation()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_tz_name(dt: datetime, context_name: str = "Reference datetime object") -> str:
        """
        Validates if a datetime is aware and extracts its IANA timezone name or 'UTC'.
        Used by factories and comparison methods to normalize inputs.
        """

        if dt.tzinfo is None:
            raise ValidationException(f"{context_name} must be timezone-aware")

        # 1. Try to get the IANA key (for ZoneInfo objects)
        tz_name = getattr(dt.tzinfo, "key", None)

        if tz_name:
            return tz_name

        # 2. If no key, check if it is native UTC or string "UTC"
        # Using str() covers both datetime.timezone.utc and fixed offsets named "UTC"
        if dt.tzinfo == timezone.utc or str(dt.tzinfo) == "UTC":
            return "UTC"

        raise ValidationException(
            f"{context_name} must use an IANA timezone or UTC"
        )

    def _extra_validation(self):
        pass

    # ------------------------------------------------------------------
    # Factories (Construtores Estáticos)
    # ------------------------------------------------------------------

    @classmethod
    def empty(cls, kind: DateKind | None = DateKind.FLOATING) -> "AxiomDate":
        return cls(value=None, kind=kind, timezone=None)

    @classmethod
    def fixed(cls, dt: datetime) -> "AxiomDate":
        """Create a fixed due date.

        Args:
            dt (datetime): Timezone-aware datetime representing the fixed instant.

        Returns:
            DueDate: A fixed due date instance.

        Raises:
            ValidationException: If the datetime is naive or does not use an IANA timezone.
        """

        tz_name: str = cls._extract_tz_name(
            dt,
            "Fixed due date",
        )

        return cls(
            value=dt,
            kind=DateKind.FIXED,
            timezone=tz_name,
        )

    @classmethod
    def floating(cls, dt: datetime, source_tz: str) -> "AxiomDate":
        """Create a floating due date.

        Args:
            dt (datetime): Naive datetime representing the floating time.
            source_tz (str): IANA timezone identifier.

        Returns:
            DueDate: A floating due date instance.
        """

        return cls(
            value=dt,
            kind=DateKind.FLOATING,
            timezone=source_tz,
        )

    @classmethod
    def now(cls) -> "AxiomDate":
        """Factory conveniente para criar 'agora' como Fixed date."""
        return cls.fixed(datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Checagens úteis
    # ------------------------------------------------------------------

    @property
    def is_floating(self) -> bool:
        return self.kind == DateKind.FLOATING

    @property
    def is_fixed(self) -> bool:
        return self.kind == DateKind.FIXED

    # ------------------------------------------------------------------
    # Conversão e Exibição
    # ------------------------------------------------------------------

    def materialize(self, target_tz: Optional[str] = None) -> Optional[datetime]:
        """Return a timezone-aware datetime suitable for comparison or display.

        Args:
            target_tz (Optional[str]): Target timezone identifier.
                If None, defaults to the due date's timezone or UTC.

        Returns:
            Optional[datetime]: A timezone-aware datetime, or None if invalid.
        """

        if self.value is None:
            return None

        # Determina qual TZ usar
        tz: ZoneInfo | timezone
        effective_tz_name: str = target_tz or self.timezone or "UTC"
        try:
            tz = ZoneInfo(effective_tz_name)
        except ZoneInfoNotFoundError:
            tz = timezone.utc

        if self.kind == DateKind.FLOATING:
            return self.value.replace(tzinfo=tz)

        if self.kind == DateKind.FIXED:
            return self.value.astimezone(tz)

        return None

    def format(self, fmt: str = "%Y-%m-%d %H:%M") -> str | None:
        """Formata para string considerando a natureza da data."""

        if self.value is None:
            return None

        dt_aware: datetime = self.materialize(self.timezone)

        suffix: str = ""
        if self.kind == DateKind.FLOATING:
            suffix = " (Local)"

        return f"{dt_aware.strftime(fmt)}{suffix}"

    def __str__(self) -> str:
        return self.format()


@dataclass(frozen=True)
class DueDate(AxiomDate):
    """
    Especialização de SmartDate focada em prazos e vencimentos.
    """

    # ------------------------------------------------------------------
    # Lógica de Domínio (Business Logic)
    # ------------------------------------------------------------------

    def _extra_validation(self):
        if self.value.year < 2000:
            raise ValidationException("Due date seems invalid (too old).")

    def is_overdue(self, now_reference: datetime) -> bool:
        """
        Verifica se o prazo expirou.

        Args:
            now_reference: O 'agora' contra o qual comparar. DEVE ser aware.
        """

        if self.value is None:
            return False

        if now_reference.tzinfo is None:
            raise ValidationException("Reference 'now' must be timezone-aware")

        is_iana: bool = isinstance(now_reference.tzinfo, ZoneInfo)
        is_utc: bool = now_reference.tzinfo == timezone.utc
        if not (is_iana or is_utc):
            raise ValidationException("Reference 'now' must use an IANA timezone or UTC")

        # Estratégia: Converter o DueDate para o contexto do 'now_reference' ou UTC
        # Se for Fixed: self.value já é UTC aware. Basta comparar se now (em UTC) > self.value
        # Se for Floating: Precisamos materializar o floating no timezone dele e comparar com now.

        try:
            # Pegamos a versão aware desta data
            my_limit = self.materialize()
            # Garantimos comparação 'apples-to-apples' convertendo ambos para timestamp ou mesmo TZ
            return now_reference > my_limit
        except (ValueError, TypeError):
            # Fallback seguro
            return False

    def remaining_time(self, now_reference: datetime) -> Optional[timedelta]:
        """Retorna o tempo restante (negativo se atrasado)."""

        if self.value is None:
            return None

        target_date = self.materialize()
        return target_date - now_reference

    # ------------------------------------------------------------------
    # Factories Específicas (Opcional, mas útil para legibilidade)
    # ------------------------------------------------------------------

    @classmethod
    def as_deadline(cls, smart_date: AxiomDate) -> "DueDate":
        """Converte um SmartDate genérico em DueDate."""
        return cls(
            value=smart_date.value,
            kind=smart_date.kind,
            timezone=smart_date.timezone
        )
