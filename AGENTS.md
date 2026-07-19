# PhotoFold repository guidance

## Source of truth

- Product requirements: `docs/PhotoFold_Developer_PRD.md`
- Implementation gates: `docs/IMPLEMENTATION_PLAN.md`
- The demo script is presentation context, not an implementation specification.

## Current implementation boundary

Only Phase 0 / Gate 0 is implemented. Keep changes within repository foundation, health/doctor checks, dataset validation, generated contracts, and the health-only frontend unless a later task explicitly authorizes another gate.

Do not add alignment, change detection, compression, reconstruction, upload/product flows, job processing, GPT integration, authentication, billing, databases, queues, or cloud infrastructure during Phase 0 maintenance.

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
```

Use `apply_patch` for text changes and keep generated contract files synchronized with `npm run contracts:generate`.

