# Axiom Core 🧠

O **Axiom Core** é o coração do ecossistema Axiom, contendo todas as regras de domínio, entidades e casos de uso da
aplicação. Ele é construído seguindo os princípios da **Clean Architecture**, garantindo que a lógica de negócio seja
independente de frameworks, bancos de dados ou interfaces externas.

## 🏗️ Estrutura do Projeto

O código está organizado em camadas concêntricas:

* **`a_core/`**: Abstrações-base e tipos universais do sistema.
* **`b_domain/`**: Entidades, Value Objects e exceções de negócio.
    * Ex: `Task`, `User`, `AxiomDate`, `RecurrenceRule`.
* **`c_application/`**: Casos de uso (Use Cases), DTOs e Mappers.
    * Esta camada orquestra o fluxo de dados de e para as entidades de domínio.

## 🚀 Tecnologias Principais

* **Python 3.12+**: tipagem estática e sintaxe moderna (PEP 695, `X | None`).
* **Poetry**: Para gerenciamento de dependências e empacotamento.
* **Timezone-aware**: Gestão rigorosa de tempo com `ZoneInfo` (Fixed vs Floating dates).

## 🧩 Componentes Chave

### AxiomDate & DueDate

Uma primitiva temporal customizada que resolve o problema de "horário de parede" (Wall-clock time) vs "instantes
absolutos" (UTC), essencial para sistemas de produtividade globais.

### Recurrence Strategies

Sistema polimórfico de recorrência que suporta desde regras simples (diárias) até complexas (enésimo dia útil do mês).

### Clean Use Cases

Todos os fluxos (Criar tarefa, Listar, Autenticar) são encapsulados em classes de comando único, facilitando testes e
auditoria.

## 🛠️ Instalação

Certifique-se de ter o [Poetry](https://python-poetry.org/) instalado.

```bash
# Clone o repositório
git clone [https://github.com/wesleyfralima/axiom-core.git](https://github.com/wesleyfralima/axiom-core.git)

# Entre na pasta
cd axiom-core

# Instale as dependências
poetry install
```

## 📄 Licença

[Axiom Core License 1.0](LICENSE). Em resumo (o texto que vale é o do
arquivo `LICENSE`):

* **Pode** usar, estudar, copiar, modificar e redistribuir, e usar o código
  para construir outras aplicações — inclusive comerciais.
* **Precisa** dar o crédito: a origem (https://github.com/wesleyfralima/axiom-core)
  e os autores (Wesley Francisco de Lima, com Claude, da Anthropic), e dizer
  quando a cópia foi modificada.
* **Não pode** vender o próprio Axiom Core como está, ou com alterações
  pequenas (renomear, trocar a marca, reempacotar…). Vender uma aplicação que
  o usa como parte e acrescenta funcionalidade própria substancial é permitido.
