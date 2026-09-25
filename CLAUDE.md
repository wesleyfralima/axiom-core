# CLAUDE.md — axiom-core

> Regras de negócio e casos de uso do Axiom Pro. **Repositório público**
> (github.com/wesleyfralima/axiom-core) e vitrine técnica do autor. O mapa do
> ecossistema (enterprise, CLI, web) está no `CLAUDE.md` da pasta-mãe
> (`../CLAUDE.md`), que mora num repositório privado de documentação. Se algo aqui divergir do código, o
> código ganha — e a linha daqui se corrige na mesma tratativa.

## Regras inegociáveis

1. **Zero dependências de runtime.** `[tool.poetry.dependencies]` só tem
   `python`. Tudo o que é framework, banco, rede ou biblioteca de terceiros
   mora no axiom-enterprise, atrás de uma **porta** em `b_domain/ports/`.
2. **Nada do plano de negócio entra aqui** (preço, plano pago, estratégia,
   segredos). O repo é público.
3. **Autocontido.** Não depender do `base-python-project`; copiar e adaptar,
   sim.
4. **O tempo é injetado.** Métodos de domínio recebem `now: datetime`; use
   cases usam `self.clock.now()` (`ClockProvider`). Nunca `datetime.now()` em
   regra de negócio (exceções legadas: defaults de `Entity`/`DomainEvent`).
5. **Efeito colateral vira evento.** O use case muda a entidade; a entidade
   registra o `DomainEvent`; o `UnitOfWork` grava no Outbox; um handler
   (`c_application/handlers/`) reage. Ex.: concluir tarefa → desbloquear
   dependentes e gerar a próxima ocorrência.
6. **Mudança de API usada pelo enterprise/CLI só fecha com eles adaptados.**

## Camadas

A letra no nome existe para a ordem de dependência ser visível no `ls`. Uma
camada só importa das anteriores.

| Pasta | Papel |
| --- | --- |
| `a_core/` | Base genérica, sem nada de Axiom: `ddd/` (`Entity`, `ValueObject`, `SimpleValueObject`, `TextValueObject`, `UniqueId`, `IdPrefix`, `DomainEvent`), `persistence/` (`BaseRepository`, `@tracks_entity`), `application/` (`DTO`, `InputDTO`, `OutputDTO`, `PaginatedResponse`), `exceptions.py`, `text.py` (ordinais, listas em inglês) |
| `b_domain/` | `entities/` (Task, User, Context, TimeEntry, OutboxEvent), `value_objects/` (datas, enums, recorrências, textos, ids, flow state, perfil/métricas de comportamento, reward), `events/`, `exceptions/`, `ports/`, `services/`, `engines/` |
| `c_application/` | `use_cases/` (auth, task, user, contexts), `handlers/` + `wiring.py`, `dtos/`, `mappers/` (entidade → OutputDTO), `utils/` |

Fora do pacote, **locais e gitignored**: `diretrizes.md` (visão do Axiom
Flow), `todo.md` (backlog "master" de março/2026) e `d_fake_infra/`
(repositórios em memória + simulador interativo do FlowEngine:
`python -m d_fake_infra`).

## Onde procurar cada coisa

- **Contrato de use case:** `b_domain/ports/use_case.py` — `UseCase[TReq, TResp]`
  recebe `uow_factory` e `clock`; cada `async with self.uow as uow:` abre uma
  transação nova; `execute` é `async`.
- **Transação + outbox:** `b_domain/ports/unit_of_work.py`. Repositórios
  concretos herdam `BaseRepository` e decoram com `@tracks_entity` todo método
  que devolve entidade — é assim que o UoW acha os eventos. `__init_subclass__`
  cobra isso na definição da classe.
- **Registro de handlers:** `c_application/handlers/wiring.py` —
  `register_essential_handlers` (desbloqueio de dependências, recorrência) e
  `register_optional_handlers` (métricas + aprendizado; recebe `None` e não
  registra nada quando o produto não os liga).
- **Datas:** `b_domain/value_objects/dates.py`. `AxiomDate.fixed` = instante
  (aware, UTC); `AxiomDate.floating` = hora de parede + fuso de origem (naive).
  Tarefa flutuante exige recorrência flutuante, e vice-versa.
- **Recorrências:** `b_domain/value_objects/recurrences/` — uma classe por
  regra, `_base.py` com o contrato, `_factory.py` monta a partir do
  `RecurrenceInputDTO`. Cada regra se descreve (`describe_pattern()`); regra
  nova tem de implementar esse método.
- **Entrada de nível pelo usuário:** `Priority`, `EnergyLevel` e
  `TaskComplexity` herdam `LevelEnum`; converta texto/número com
  `.parse(...)` (falha com `InvalidValueError`), nunca com `Priority(texto)`.
- **Motores (ainda sem use case):** `b_domain/engines/flow_engine.py`
  (`FlowEngine.get_next_action` → `FlowDecision`) e
  `b_domain/engines/task_language_engine.py`
  (`build_language_engine(config, contexts_map)` →
  `TaskLanguageEngine.infer(texto, now, lang)`). A configuração padrão do
  segundo é `b_domain/engines/task_language_engine.toml`, empacotada; quem a
  lê é o chamador (`importlib.resources` + `tomllib`), nunca o core.
- **IDs curtos:** use cases de tarefa recebem **prefixo** de UUID
  (`IdPrefix`) e resolvem via `TaskRepository.task_ids_from_id_prefixes`;
  ambiguidade é erro.

O inventário completo (o que existe, o que falta, o que tem defeito) está em
`../docs/inventario.md`.

## Convenções de código

- Python 3.12, sintaxe moderna: `X | None`, generics PEP 695
  (`class UseCase[TReq, TResp]`), `StrEnum`/`IntEnum`, `datetime.UTC`.
- Entidades: `@dataclass(kw_only=True, eq=False)` + factory `create(...)`.
  Value objects: `@dataclass(frozen=True)`; métodos que "mudam" devolvem cópia.
- Código, nomes e docstrings em **inglês**, docstrings no estilo Google (Args /
  Returns / Raises). Documentação do repo (`README`, `docs/`) em português.
- Exceções de negócio herdam `DomainException` (`a_core/exceptions.py`) e ficam
  em `b_domain/exceptions/` por assunto.
- black + ruff (`E, F, I, UP`), linha de 88; mypy estrito
  (`disallow_untyped_defs`) em `a_core`, `b_domain`, `c_application` e `tests`
  — está zerado; commit não usa mais `SKIP=mypy`.

## Comandos

O pre-commit (`.pre-commit-config.yaml`) chama as ferramentas do `.venv` do
próprio repo, para nunca discordar do `make check`. Não use `poetry run` nos
hooks: com outro venv ativo no terminal (o VSCode ativa sozinho), o Poetry
usa o venv errado.

```bash
make check      # black --check, ruff, mypy, pytest com cobertura mínima de 95%
make test       # só pytest
make coverage   # relatório em htmlcov/
make lint-fix   # ruff --fix
make format     # black
```

Testes em `tests/a_unit` (marcador `unit`), `tests/b_integration` e
`tests/c_system` (vazios). Os fakes de repositório, UoW e relógio estão em
`tests/conftest.py` (`fake_uow_factory`, `fake_clock`, `use_case_context`).

## Fluxo de trabalho

1. Um branch por trabalho: `feat/backlogNN-parteN-nome-curto` (ou `fix/…`).
2. Commit no branch; `merge --no-ff` em `master`. Push só quando o dono pedir.
3. No mesmo commit do trabalho: suba `version` no `pyproject.toml` (feature →
   `0.x.0`; correção → `0.x.y`) e escreva a entrada no `CHANGELOG.md`.
4. `make check` verde antes do merge (hoje ainda não está — é a Parte 2 do
   Backlog 01).

### docs/backlog/todo/ e docs/backlog/done/

Pendências e histórico ficam em **um arquivo por objetivo**, e cada pasta tem
um `README.md` que é só o índice. Um arquivo só vai para `done/` quando está
100% concluído, inteiro, com "resolvido em …" em cada item; enquanto houver
item aberto ele fica em `todo/` (inclusive com os `[x]`). `done/` não se edita
retroativamente. Se um trabalho fechar item de outro arquivo, feche lá também.

## Estado atual (24/09/2026)

- Versão `0.3.8`: WIP consolidado (Backlog 01, Parte 1), licença (Parte 5,
  1º item), bugs do levantamento (Parte 3) e o que o CLI pediu para o uso
  diário (listar só abertas, editar prazo, validar preferências).
- 298 testes passando; **mypy zerado** (pacotes e testes); cobertura 68%,
  abaixo do piso de 95% do `make check` — o piso real é item da Parte 2.
- O CI (`.github/workflows/ci.yml`) veio do base-python-project e está errado:
  roda em `main`/`develop` (o branch é `master`) e mede cobertura de
  `src/arch_pat_with_python`. Parte 2.
