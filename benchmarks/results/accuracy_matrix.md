# Benchmark Results

## Token Reduction

| Fixture | Domain | JSON tokens | TOON tokens | Reduction |
|---------|--------|-------------|-------------|-----------|
| K8s 16-pod node | Kubernetes | 9,876 | 3,656 | **63.0%** |
| K8s 6-pod node | Kubernetes | 15,285 | 5,919 | **61.3%** |
| EC2 instances | AWS | 33,498 | 4,386 | **86.9%** |
| SQL orders | Database | 26,165 | 11,298 | **56.8%** |

## Accuracy Matrix

*JSON accuracy / TOON accuracy per model and fixture.*

| Model | K8s 16-pod node | K8s 6-pod node | EC2 instances | SQL orders |
|-------|-----|-----|-----|-----|
| **qwen3:1.7b** | 9/20 (45%) / 13/20 (65%) | 14/25 (56%) / 14/25 (56%) | 2/14 (14%) / 4/15 (27%) | 2/13 (15%) / 4/14 (29%) |
| **qwen3:4b** | 17/20 (85%) / 20/20 (100%) | 25/25 (100%) / 25/25 (100%) | 12/15 (80%) / 9/15 (60%) | 7/15 (47%) / 7/15 (47%) |
| **llama3.1:8b** | 11/20 (55%) / 11/20 (55%) | 10/25 (40%) / 13/25 (52%) | 2/15 (13%) / 7/15 (47%) | 0/15 (0%) / 4/15 (27%) |
| **qwen3:14b** | 18/20 (90%) / 20/20 (100%) | 24/25 (96%) / 25/25 (100%) | 8/12 (67%) / 6/14 (43%) | 7/13 (54%) / 10/14 (71%) |
| **qwen3:30b** | 19/20 (95%) / 20/20 (100%) | 25/25 (100%) / 25/25 (100%) | 13/15 (87%) / 9/15 (60%) | 12/15 (80%) / 10/15 (67%) |

*Cells show JSON accuracy / TOON accuracy.*

## Context Window Enablement

| Fixture | JSON tok | TOON tok | 8K | 16K | 32K | 64K | 128K |
|---------|----------|----------|-----|-----|-----|-----|-----|
| K8s 16-pod node | 9,876 | 3,656 | -- | **TOON only** | Both | Both | Both |
| K8s 6-pod node | 15,285 | 5,919 | -- | -- | **TOON only** | Both | Both |
| EC2 instances | 33,498 | 4,386 | -- | **TOON only** | **TOON only** | **TOON only** | Both |
| SQL orders | 26,165 | 11,298 | -- | -- | -- | **TOON only** | Both |
| K8s 30-pod node | 69,885 | 22,229 | -- | -- | -- | -- | **TOON only** |
