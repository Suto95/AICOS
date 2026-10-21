# Branching and Rollback Workflow

## Objective
Protect the existing Streamlit codebase while migration is implemented in parallel.

## Branching Model
- `main`: stable production branch.
- `migration/react-ui`: long-running migration branch.
- `feature/*`: short-lived branches merged into `migration/react-ui`.

## Required Rules
- No direct push to `main`.
- PR required for all merges.
- CI must pass before merge.
- Keep Streamlit paths intact until production cutover is accepted.

## Safe Snapshot Before Major Changes
Run:

```bash
./tools/migration/create_safety_snapshot.sh
```

This creates:
- a local backup branch `backup/<timestamp>`
- a local annotated tag `snapshot/<timestamp>`

## Rollback Scenarios

### 1) Roll Back Code to Last Safe Snapshot
```bash
git checkout main
git checkout snapshot/<timestamp>
```

Then cherry-pick only validated commits into a new fix branch.

### 2) Roll Back Deployment
- Keep old Streamlit deployment active until React stack is stable.
- Re-point traffic/DNS to last known good deployment target.
- Revert production release commit if needed.

### 3) Roll Back Database
- Always take a DB backup before schema changes.
- Restore backup in staging first.
- Restore production only after validation.

## Minimal Approval Gates
- Gate A: API contract approved.
- Gate B: staging parity approved.
- Gate C: production cutover approved.

## Operational Checklist
- [ ] Safety snapshot created.
- [ ] Migration work isolated to migration branches.
- [ ] CI green on migration branch.
- [ ] Staging smoke checks passed.
- [ ] Rollback drill completed once before production.