# AGENTS.md

## Mission

Build the requested full-stack application **quickly, correctly, and with minimal unnecessary complexity**.

The priority order is:

1. Make the requested functionality work.
2. Make the primary user flow usable.
3. Keep the implementation simple and maintainable.
4. Verify the application works end-to-end.
5. Only then make small improvements that directly support the request.

This is a **rapid-delivery project**.

Do not turn it into an enterprise architecture exercise.

---

# Core Rule

## Build only what was requested

Do **not** invent features, requirements, screens, workflows, abstractions, integrations, or infrastructure that were not requested.

If something is not necessary to satisfy the stated requirements, do not build it.

Examples of things you should NOT add unless explicitly requested:

* authentication
* user accounts
* permissions or RBAC
* admin dashboards
* analytics
* telemetry
* feature flags
* payment systems
* caching infrastructure
* background job systems
* message queues
* WebSockets
* microservices
* Docker
* Kubernetes
* CI/CD pipelines
* cloud infrastructure
* extensive logging systems
* elaborate configuration systems
* internationalization
* accessibility frameworks beyond sensible HTML practices
* complex state-management libraries
* design systems
* component libraries created from scratch
* generic internal frameworks
* speculative API endpoints
* speculative database fields
* speculative future features

Do not add functionality simply because it might be useful later.

Implement the application that was requested **now**.

---

# Technology

Unless the existing repository or task specifies otherwise:

## Frontend

Use:

* React
* TypeScript
* Vite

Prefer:

* functional components
* React hooks
* native `fetch`
* straightforward CSS
* existing dependencies already present in the repository

Avoid adding dependencies unless they provide clear value.

Do not introduce:

* Redux
* MobX
* complex state machines
* unnecessary context providers
* large UI frameworks

unless the application's requirements actually need them.

Local component state should be the default.

---

## Backend

Use:

* Python
* FastAPI
* Pydantic

Prefer:

* simple REST endpoints
* typed request/response models
* clear service functions when business logic becomes non-trivial
* synchronous code unless async provides an actual benefit

Do not introduce complex backend architecture for a small application.

A normal structure is sufficient:

```text
backend/
  app/
    main.py
    models/
    routes/
    services/
```

Do not create every directory unless it is actually needed.

For very small backends, keeping related functionality together is preferable to unnecessary file fragmentation.

---

# Repository Structure

Prefer a simple full-stack layout such as:

```text
/
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
│
├── backend/
│   ├── app/
│   ├── requirements.txt or pyproject.toml
│   └── ...
│
└── README.md
```

If the repository already has a structure, follow it rather than reorganizing the project.

Do not perform large structural refactors unless required.

---

# Development Philosophy

## Simple beats clever

Use the simplest implementation that solves the actual requirement.

Prefer:

```text
clear code
```

over:

```text
clever abstraction
```

Prefer:

```text
one obvious implementation
```

over:

```text
a configurable framework supporting hypothetical future use cases
```

Prefer:

```text
3 understandable files
```

over:

```text
12 layers of abstraction
```

Do not optimize for imaginary future requirements.

---

# Work Autonomously

Do not repeatedly stop for confirmation when the request is sufficiently clear.

Make reasonable implementation decisions and continue.

When multiple solutions are viable, choose the one that:

1. requires the least complexity,
2. introduces the fewest dependencies,
3. is easiest to understand,
4. is fastest to implement,
5. fits the existing codebase.

Only ask a question when proceeding would require making a major product decision that cannot reasonably be inferred.

---

# Before Writing Code

Quickly inspect the repository.

Identify:

* existing frontend structure
* existing backend structure
* package manager
* current dependencies
* existing patterns
* available scripts
* relevant environment configuration

Then implement the request.

Do not spend excessive time exploring unrelated files.

Do not perform a broad architectural review unless asked.

---

# Scope Discipline

Before implementing something, ask:

> Is this required to deliver the requested functionality?

If the answer is no, do not build it.

When modifying an existing codebase:

* touch the minimum number of files necessary
* preserve existing behavior unless changes are required
* do not clean up unrelated code
* do not rename unrelated files
* do not reformat the entire repository
* do not upgrade dependencies unless necessary
* do not migrate architecture unless necessary

Avoid unrelated refactoring.

A feature request is not permission to redesign the codebase.

---

# Frontend Rules

## Components

Create components when they:

* are reused
* significantly improve readability
* represent meaningful UI sections

Do not split trivial markup into dozens of tiny components.

Do not create abstractions such as:

```text
BaseContainer
GenericSection
UniversalCard
AbstractButtonFactory
DynamicRenderer
```

unless they solve an actual repeated problem.

---

## State

Use:

1. local component state first
2. lifted state when necessary
3. context only for genuinely shared application state

Do not introduce global state management unless requirements justify it.

---

## API Calls

Keep API communication simple.

A lightweight API module is fine:

```text
src/
  api/
    client.ts
```

Do not build a complex SDK around a small backend.

Handle:

* loading
* successful responses
* expected errors

Do not create elaborate retry, caching, synchronization, or request orchestration systems unless required.

---

# UI / UX

The application should feel intentional and usable, but speed matters.

Prioritize:

* obvious navigation
* readable layouts
* clear hierarchy
* usable forms
* useful loading states
* useful empty states
* useful error states
* responsive behavior

Support normal desktop and mobile widths unless requirements specify otherwise.

Do not spend excessive time creating:

* animations
* elaborate visual effects
* complex transitions
* decorative components
* custom illustration systems
* pixel-perfect design systems

unless explicitly requested.

Do not fill the interface with unnecessary marketing copy or generic filler text.

Use concise, functional copy.

---

# CSS

Use the styling approach already established in the repository.

If no system exists, choose the simplest reasonable solution.

Do not introduce a large styling framework solely for a few components.

Avoid:

* unnecessary design tokens
* huge theme systems
* complex CSS architecture
* premature responsive abstractions

Keep styles understandable and local to the relevant UI.

---

# Backend Rules

## API Design

Create only endpoints required by the frontend or explicitly requested.

Use predictable REST conventions where appropriate.

For example:

```text
GET    /items
GET    /items/{id}
POST   /items
PUT    /items/{id}
DELETE /items/{id}
```

Do not build speculative endpoints.

---

## Validation

Use Pydantic for meaningful input and output validation.

Validate actual boundaries and user-controlled input.

Do not create excessive validation for impossible internal states.

---

## Business Logic

Keep simple logic close to where it is used.

Extract services when logic becomes:

* reused
* difficult to understand
* meaningfully complex

Do not automatically create:

```text
controller
service
repository
domain
use-case
adapter
interface
implementation
```

layers for every operation.

---

# Database

Only introduce a database when persistent storage is required.

Use the simplest database appropriate for the request.

For rapid local applications, SQLite is acceptable unless requirements indicate otherwise.

Do not introduce:

* Redis
* Elasticsearch
* multiple databases
* distributed persistence
* elaborate repository abstractions

unless required.

If an ORM is already present, use it.

Do not replace working persistence technology simply because you prefer another option.

---

# Error Handling

Handle errors where they matter.

Backend:

* return sensible HTTP status codes
* return useful error messages
* avoid exposing sensitive internals

Frontend:

* show useful failure states
* prevent obvious broken interactions

Do not build a sophisticated global error-handling framework unless necessary.

---

# Security

Use reasonable baseline security practices without turning the project into a security-engineering exercise.

Never:

* commit secrets
* hardcode credentials
* expose private keys
* trust unvalidated user input
* execute arbitrary user input

Use environment variables for secrets when necessary.

Do not build authentication or authorization unless requested.

---

# Testing

Testing should support delivery rather than delay it.

Prioritize testing the functionality most likely to break.

For rapid delivery:

* test important business logic
* test important backend endpoints when useful
* manually verify the primary frontend workflow
* run existing test suites

Do not attempt to achieve arbitrary coverage percentages.

Do not create large test infrastructures for trivial code.

Do not spend more time testing simple implementation details than building the requested feature.

If the repository already has testing conventions, follow them.

---

# Verification

Before considering work complete, verify the actual application.

At minimum:

## Frontend

Run the relevant commands such as:

```bash
npm run build
```

and any existing:

```bash
npm run lint
npm test
```

Fix errors caused by your changes.

---

## Backend

Run relevant tests and verify the server starts successfully.

For example:

```bash
pytest
```

when tests exist.

Verify changed endpoints behave as expected.

---

## End-to-End

For features involving both frontend and backend, verify the complete flow:

```text
UI
↓
frontend request
↓
backend endpoint
↓
business logic
↓
response
↓
UI update
```

Do not declare a full-stack feature complete after verifying only one side.

---

# Dependency Rules

Before installing a package, ask:

> Can this reasonably be done with what is already installed?

If yes, use what already exists.

A new dependency is appropriate when it significantly reduces complexity or solves a real problem.

Avoid packages for trivial utilities that can be implemented clearly in a few lines.

Do not add competing libraries for functionality the project already has.

---

# Performance

Do not prematurely optimize.

Fix obvious problems such as:

* accidental infinite loops
* obviously wasteful network requests
* huge unnecessary payloads
* major rendering issues

Do not introduce advanced caching, memoization, batching, indexing, workers, or infrastructure without evidence they are needed.

---

# Documentation

Documentation should be short and useful.

Update the README only when needed to explain things such as:

* how to run the application
* required environment variables
* unusual setup
* important implementation decisions

Do not write extensive architecture documents unless requested.

Code should normally explain itself through:

* good names
* simple structure
* small focused comments where necessary

---

# Comments

Do not comment obvious code.

Bad:

```python
# Get the user
user = get_user()
```

Useful:

```python
# The upstream API returns 200 with an empty payload when the record
# no longer exists, so normalize that case to a 404 here.
```

Explain **why**, not **what**.

---

# Avoid Premature Abstraction

Do not create reusable abstractions before reuse actually exists.

Duplication of a few simple lines is often preferable to the wrong abstraction.

Use the rule of three as a rough guideline:

If something appears repeatedly and extracting it clearly simplifies the code, consider abstraction.

Otherwise leave it simple.

---

# Do Not Gold-Plate

Once the requested feature:

* works
* is understandable
* has reasonable error handling
* passes relevant checks
* works end-to-end

stop.

Do not continue adding improvements simply because you have ideas.

Especially avoid unsolicited:

* redesigns
* animations
* settings
* preferences
* dashboards
* extensibility
* architecture layers
* abstractions
* developer tooling
* additional features

Done is better than unnecessarily elaborate.

---

# Implementation Decision Rule

When deciding between two approaches, prefer the one with:

* fewer files
* fewer dependencies
* fewer concepts
* less configuration
* less code
* easier debugging
* faster implementation

as long as it remains clean and correct.

---

# Completion Checklist

Before finishing, confirm:

* [ ] The requested functionality exists.
* [ ] No major requested requirement was skipped.
* [ ] No unrelated features were added.
* [ ] Frontend and backend communicate correctly.
* [ ] Important loading and error states work.
* [ ] The application works at normal desktop widths.
* [ ] The application works at reasonable mobile widths when applicable.
* [ ] Frontend builds successfully.
* [ ] Backend starts successfully.
* [ ] Relevant existing tests pass.
* [ ] No obvious runtime errors remain.
* [ ] No secrets were committed.
* [ ] No unnecessary dependencies were introduced.
* [ ] No unnecessary architecture was introduced.
* [ ] No unrelated refactors were performed.

---

# Final Response

When completing a task, keep the report concise.

Include:

1. what was implemented
2. important files changed
3. verification performed
4. anything genuinely blocking or incomplete

Do not provide a lengthy essay about the implementation.

If everything requested works, say so clearly.

---

# Default Mental Model

Think like an experienced engineer delivering an MVP under a tight deadline.

Not:

> "What architecture would support every possible future requirement?"

Instead:

> "What is the cleanest, fastest, least complicated way to correctly deliver what was requested?"

Build that.
