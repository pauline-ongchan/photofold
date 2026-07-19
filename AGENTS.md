# PhotoFold repository guidance

## Source of truth

- Product requirements: `docs/PhotoFold_Developer_PRD.md`
- Implementation gates: `docs/IMPLEMENTATION_PLAN.md`
- The demo script is presentation context, not an implementation specification.

## Current implementation boundary

Phase 0 / Gate 0 and the CLI-only Phase 1 / Gate 1 compression experiment are implemented. Keep changes within repository foundation, health/doctor checks, dataset validation, generated contracts, the health-only frontend, and the deterministic Gate 1 benchmark/package/report unless a later task explicitly authorizes another gate.

Do not add upload/product flows, API job processing, multiple curated scenarios, GPT integration, authentication, billing, databases, queues, or cloud infrastructure during Phase 0–1 maintenance. Those belong to Phase 2 or later.

## Invariants

- The deterministic processor must start without network access or model credentials.
- All API contracts originate from FastAPI/Pydantic OpenAPI and TypeScript is generated.
- Dataset validation must verify real files, checksums, formats, frame count, and normalized dimensions.
- Do not add hard-coded storage or quality results.
- Use WebP as the required initial codec and fail the doctor check if Pillow lacks WebP support.
- Preserve the transform, metric, package, and error decisions in `docs/TECHNICAL_CONTRACTS.md` until a measured later-gate experiment justifies a revision.

## Commands

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e 'services/processor[dev]'
npm ci
make verify-gate0
make human-verify-gate0
make verify-gate1
make human-verify-gate1
```

Use `apply_patch` for text changes and keep generated contract files synchronized with `npm run contracts:generate`.
