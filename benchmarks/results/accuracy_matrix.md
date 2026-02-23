# Benchmark Results

## Token Reduction

| Fixture | Domain | JSON tokens | TOON tokens | Reduction |
|---------|--------|-------------|-------------|-----------|
| K8s 16-pod node | Kubernetes | 9,876 | 3,656 | **63.0%** |
| K8s 6-pod node | Kubernetes | 15,285 | 8,250 | **46.0%** |
| EC2 instances | AWS | 33,498 | 6,072 | **81.9%** |
| SQL orders | Database | 26,165 | 11,298 | **56.8%** |

## Accuracy Matrix

*JSON accuracy / TOON accuracy per model and fixture.*

| Model | K8s 16-pod node | K8s 6-pod node | EC2 instances | SQL orders |
|-------|-----|-----|-----|-----|
| **qwen3:1.7b** | -- / 14/20 (70%) | -- / 15/25 (60%) | -- / 12/15 (80%) | -- / 3/14 (21%) |
| **qwen3:4b** | -- / 20/20 (100%) | -- / 25/25 (100%) | -- / 15/15 (100%) | -- / 10/15 (67%) |
| **llama3.1:8b** | -- / 10/20 (50%) | -- / 13/25 (52%) | -- / 6/15 (40%) | -- / 3/15 (20%) |
| **qwen3:14b** | -- / 20/20 (100%) | -- / 25/25 (100%) | -- / 11/15 (73%) | -- / 10/14 (71%) |
| **qwen3:30b** | -- / 19/19 (100%) | -- / 25/25 (100%) | -- / 15/15 (100%) | -- / 9/15 (60%) |

*Cells show JSON accuracy / TOON accuracy.*

## Context Window Enablement

| Fixture | JSON tok | TOON tok | 8K | 16K | 32K | 64K | 128K |
|---------|----------|----------|-----|-----|-----|-----|-----|
| K8s 16-pod node | 9,876 | 3,656 | Neither | **TOON only** | JSON + TOON | JSON + TOON | JSON + TOON |
| K8s 6-pod node | 15,285 | 8,250 | Neither | Neither | **TOON only** | JSON + TOON | JSON + TOON |
| EC2 instances | 33,498 | 6,072 | Neither | Neither | **TOON only** | **TOON only** | JSON + TOON |
| SQL orders | 26,165 | 11,298 | Neither | Neither | Neither | **TOON only** | JSON + TOON |
| K8s 30-pod node | 69,885 | 32,125 | Neither | Neither | Neither | Neither | **TOON only** |
