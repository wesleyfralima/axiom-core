# Axiom Core 🧠

**Axiom Core** is the heart of the Axiom ecosystem: it holds every domain rule, entity and use case of the
application. It follows the principles of **Clean Architecture**, so the business logic is independent of
frameworks, databases and external interfaces.

## 🏗️ Project structure

The code is organized in concentric layers:

* **`a_core/`**: base abstractions and the system's universal types.
* **`b_domain/`**: entities, value objects and business exceptions.
    * E.g. `Task`, `User`, `AxiomDate`, `RecurrenceRule`.
* **`c_application/`**: use cases, DTOs and mappers.
    * This layer orchestrates the data flow to and from the domain entities.

## 🚀 Main technologies

* **Python 3.12+**: static typing and modern syntax (PEP 695, `X | None`).
* **Poetry**: dependency management and packaging.
* **Timezone-aware**: strict time handling with `ZoneInfo` (fixed vs floating dates).

## 🧩 Key components

### AxiomDate & DueDate

A custom time primitive that solves the "wall-clock time" vs "absolute instant" (UTC) problem, essential for
productivity systems used across time zones.

### Recurrence strategies

A polymorphic recurrence system that supports everything from simple rules (daily) to complex ones (the nth
business day of the month).

### Clean use cases

Every flow (create a task, list, authenticate) is wrapped in a single-command class, which makes testing and
auditing easier.

## 🛠️ Installation

Make sure [Poetry](https://python-poetry.org/) is installed.

```bash
# Clone the repository
git clone https://github.com/wesleyfralima/axiom-core.git

# Enter the folder
cd axiom-core

# Install the dependencies
poetry install
```

## 📄 License

[Axiom Core License 1.0](LICENSE). In short (the binding text is the one in
the `LICENSE` file):

* You **may** use, study, copy, modify and redistribute it, and use the code
  to build other applications — commercial ones included.
* You **must** give credit: the origin (https://github.com/wesleyfralima/axiom-core)
  and the authors (Wesley Francisco de Lima, with Claude, by Anthropic), and
  say when your copy was modified.
* You **may not** sell Axiom Core itself as-is, or with minor changes
  (renaming, rebranding, repackaging…). Selling an application that uses it as
  one of its parts and adds substantial functionality of its own is allowed.
