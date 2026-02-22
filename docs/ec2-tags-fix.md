# EC2 Tags Dropped During Condensing

## Problem

The condenser silently drops AWS EC2 `Tags` arrays (and other nested arrays like
`SecurityGroups`, `BlockDeviceMappings`, `NetworkInterfaces`) when rendering
sub-tables. This makes it impossible for an LLM to answer tag-based questions
from TOON output.

## Impact

In benchmark testing across 4 models (qwen3:1.7b through qwen3:14b), 5 of 15
EC2 questions are **impossible to answer** from TOON because the required data
is missing:

| Question | Expected | All Models Answered |
|----------|----------|-------------------|
| How many instances tagged Environment=prod? | 11 | 0 |
| How many instances tagged Environment=staging? | 7 | 0 |
| How many instances tagged Team=data? | 8 | 0 |
| What is the Name tag of instance i-ca4b...? | data-pipeline-prod-02 | (hallucinated) |
| How many staging instances are running? | 4 | 0 |

These 5 questions account for most of the TOON accuracy gap on the EC2 fixture.
The remaining EC2 failures are counting difficulty on wide tables (State, AZ,
InstanceType are all present — models just miscount across 20 dense rows).

## Root Cause

The condenser performs **single-level sub-table extraction**. The code path:

1. `render_table()` receives the top-level `Reservations` array
2. It detects `Reservations.Instances` as a homogeneous nested array and
   extracts it as a sub-table
3. When rendering the `Instances` sub-table, `preprocess_table()` calls
   `union_columns()` which explicitly **skips list fields**:
   ```python
   if not isinstance(v, list):
       cols[k] = ...
   ```
4. As a result, `Tags`, `SecurityGroups`, `BlockDeviceMappings`,
   `NetworkInterfaces`, and `ProductCodes` are all silently discarded

There is no recursive pass to extract sub-sub-tables from the Instances rows.

## What IS Present in TOON Output

The Instances table has 22 scalar columns including `State.Name`, `InstanceId`,
`InstanceType`, `Placement.AvailabilityZone`, and `IamInstanceProfile.Arn`.
Counting by state, AZ, or instance type is possible but difficult due to table
width.

## What IS NOT Present

All Tags are missing:
- `Name` (e.g., "web-api-prod-00")
- `Environment` (e.g., "prod", "staging", "dev")
- `Team` (e.g., "data", "backend", "frontend")
- `CostCenter`, `Application`, `ManagedBy`, `CreatedBy`, etc.

## Proposed Fix

Two approaches, not mutually exclusive:

### Option A: Pivot Key-Value Tag Arrays

Detect arrays of `{Key, Value}` objects (AWS tag convention) and pivot them
into per-row scalar columns:

```
Tags: [{Key: "Name", Value: "web-api-prod-00"}, {Key: "Environment", Value: "prod"}]
```
becomes:
```
Tags.Name: web-api-prod-00
Tags.Environment: prod
```

This is the highest-value fix since AWS tags are the most common use case for
this pattern. It produces clean, queryable columns.

### Option B: Recursive Sub-Table Extraction

When rendering a sub-table, detect homogeneous array fields within those rows
and render them as additional sub-sub-tables with parent back-references. This
is more general but produces more complex output.

### Recommendation

Option A for `[{Key, Value}]` patterns (covers AWS tags, Kubernetes labels,
and similar). Option B as a follow-up for arbitrary nested arrays like
SecurityGroups.

## SQL Findings (No Fix Needed)

The SQL fixture failures are **not a TOON problem**. All 150 rows and 17
columns are fully preserved with no elisions. JSON fails equally or worse on
the same questions. The failures are a fundamental limitation of small LLMs
counting over 150 rows of dense tabular data.
