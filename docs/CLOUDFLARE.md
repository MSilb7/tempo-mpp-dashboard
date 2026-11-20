# Cloudflare readiness

On 2026-11-18 the newly connected Cloudflare connector successfully performed authenticated read-only account discovery and R2 bucket, D1 database and Workers script listings. This confirms read access for those API routes. It does not establish write permissions, billing readiness, production capacity or a deployed project. No resources were created or changed. Account identifiers, inventory and authenticated response payloads are intentionally absent from this public repository.

## Proposed role

The [platform plan](DATA_PLATFORM.md) proposes R2 for durable evidence and versioned artifacts, with Workers and optionally D1 for a compact serving layer. These are architectural candidates. The current Python/Node execution environment remains local; there is no Cloudflare deployment configuration or cloud scheduler in this repository.

Before implementation:

1. Measure bounded ingestion volume, model runtime and artifact size; decide retention and cost limits.
2. Choose the compute host and schedule for Python SQLMesh/Node ingestion, plus production state, single-writer coordination and recovery.
3. Define private evidence storage and an explicitly approved public aggregate projection. Do not upload local `latest.json` directly: it includes provenance and transfer evidence.
4. Choose serving storage from measured query needs; keep metric computation in the model layer.
5. Add narrowly scoped bindings/credentials, deployment configuration, rollback and monitoring. Verify current product limits against official documentation during that implementation.

No Cloudflare access is required to [get started locally](START_HERE.md). Connector setup is specific to the current user's client; teammates need their own authorized access if they later operate cloud resources. No credentials belong in source control.


## Cloud runner research handoff — 2026-11-20

A user-authorized side-chat identified Cloudflare Containers as a candidate native Linux runner and proposed a portable `linux/amd64` image. This has not been tested or selected. The next spike should run the existing label/backfill and interruption/overlap tests in a container, then compare durable storage before deploying. Ordinary Python Workers must not be assumed to support the current native dependency stack.

Research leads to validate: [Container architecture](https://developers.cloudflare.com/containers/concepts/architecture/), [R2 mounts](https://developers.cloudflare.com/containers/examples/r2-fuse-mount/), [SQLMesh DuckDB state guidance](https://sqlmesh.readthedocs.io/en/stable/integrations/engines/duckdb/), [MotherDuck integration](https://sqlmesh.readthedocs.io/en/stable/integrations/engines/motherduck/) and [DuckLake compatibility](https://ducklake.select/docs/stable/duckdb/introduction). Compare serialized restore/upload of closed DuckDB checkpoints, a durable analytical backend, and a cloud runner with persistent disk. Do not assume an ephemeral container, R2 mount or local file lock provides durable shared database semantics. An external SQLMesh state database must not advance intervals beyond durably stored warehouse results. D1 and Hyperdrive must not be assumed to supply a supported PostgreSQL state backend.

These are research candidates and failure-mode considerations, not a backend decision, version upgrade, benchmark or authorization to provision paid infrastructure. Preserve the last good publication while validating replacement results and cloud-safe single-writer coordination.
