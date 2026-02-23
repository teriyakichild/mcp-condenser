# Benchmark Results

## Token Reduction

| Fixture | Domain | JSON tokens | TOON tokens | Reduction |
|---------|--------|-------------|-------------|-----------|
| K8s 16-pod node | Kubernetes | 9,876 | 3,656 | **63.0%** |
| K8s 6-pod node | Kubernetes | 15,285 | 8,250 | **46.0%** |
| EC2 instances | AWS | 33,498 | 6,072 | **81.9%** |
| SQL orders | Database | 26,165 | 11,298 | **56.8%** |

## JSON Accuracy (baseline)

| Model | K8s 16-pod node | K8s 6-pod node | EC2 instances | SQL orders |
|-------|-----|-----|-----|-----|
| **qwen3:1.7b** | 9/20 (45%) | 14/25 (56%) | 2/14 (14%) | 2/13 (15%) |
| **qwen3:4b** | 17/20 (85%) | 25/25 (100%) | 12/15 (80%) | 7/15 (47%) |
| **llama3.1:8b** | 11/20 (55%) | 10/25 (40%) | 2/15 (13%) | 0/15 (0%) |
| **qwen3:14b** | 18/20 (90%) | 24/25 (96%) | 8/12 (67%) | 7/13 (54%) |
| **qwen3:30b** | 19/20 (95%) | 25/25 (100%) | 13/15 (87%) | 12/15 (80%) |

## TOON Accuracy (balanced profile)

| Model | K8s 16-pod node | K8s 6-pod node | EC2 instances | SQL orders |
|-------|-----|-----|-----|-----|
| **qwen3:1.7b** | 14/20 (70%) | 15/25 (60%) | 12/15 (80%) | 3/14 (21%) |
| **qwen3:4b** | 20/20 (100%) | 25/25 (100%) | 15/15 (100%) | 10/15 (67%) |
| **llama3.1:8b** | 10/20 (50%) | 13/25 (52%) | 6/15 (40%) | 3/15 (20%) |
| **qwen3:14b** | 20/20 (100%) | 25/25 (100%) | 11/15 (73%) | 10/14 (71%) |
| **qwen3:30b** | 19/19 (100%) | 25/25 (100%) | 15/15 (100%) | 9/15 (60%) |

## Context Window Enablement

| Fixture | JSON tok | TOON tok | 8K | 16K | 32K | 64K | 128K |
|---------|----------|----------|-----|-----|-----|-----|-----|
| K8s 16-pod node | 9,876 | 3,656 | Neither | **TOON only** | JSON + TOON | JSON + TOON | JSON + TOON |
| K8s 6-pod node | 15,285 | 8,250 | Neither | Neither | **TOON only** | JSON + TOON | JSON + TOON |
| EC2 instances | 33,498 | 6,072 | Neither | Neither | **TOON only** | **TOON only** | JSON + TOON |
| SQL orders | 26,165 | 11,298 | Neither | Neither | Neither | **TOON only** | JSON + TOON |
| K8s 30-pod node | 69,885 | 32,125 | Neither | Neither | Neither | Neither | **TOON only** |
