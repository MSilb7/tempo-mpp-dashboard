# Tempo MPP Dashboard

Explore machine-payment activity without confusing settled transfers with workflow purpose.

Initial prototype: synthetic data only. No live indexer or operator integration is connected.

## Preview

Run `python3 -m http.server 8000` in this directory and open http://localhost:8000.

## Project context

Read [AGENTS.md](AGENTS.md), [product brief](docs/PRD.md), [technical design](docs/TECHNICAL_DESIGN.md), and [current state](docs/STATUS.md).

## Evidence model

- Chain-verified: transfer amounts, addresses, timestamps, fees and memo bytes.
- Operator-reported: workflow membership, service operation, use case and completion.
- Model-inferred: predictions with provenance and uncertainty; never silently promoted to fact.

Gross transfer volume is not end-user expenditure: customer and downstream provider payments may represent the same economic purchase.
