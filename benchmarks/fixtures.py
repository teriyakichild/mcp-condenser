"""Shared fixture metadata, questions, match functions, and loaders for benchmarks."""

import json
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Fixture loader
# ---------------------------------------------------------------------------

def load_sample(fixtures_dir: Path, filename: str):
    """Load a fixture file, unwrapping {"result": "<json>"} envelope if present."""
    raw = (fixtures_dir / filename).read_text()
    data = json.loads(raw)
    if isinstance(data, dict) and set(data.keys()) == {"result"} and isinstance(data["result"], str):
        inner = data["result"]
        data = json.loads(inner)
        raw = inner
    return raw, data


# ---------------------------------------------------------------------------
# Match functions
# ---------------------------------------------------------------------------

def contains(answer: str, expected: str) -> bool:
    """Expected string appears somewhere in the LLM response."""
    return expected in answer


def numeric_close(answer: str, expected: str, tol: float = 0.01) -> bool:
    """Extract a number from the answer and check it's within tolerance."""
    expected_num = float(expected)
    numbers = re.findall(r"[\d,]+\.?\d*", answer.replace(",", ""))
    for raw_num in numbers:
        try:
            val = float(raw_num)
            if abs(val - expected_num) <= tol * max(abs(expected_num), 1):
                return True
        except ValueError:
            continue
    return False


def contains_or_numeric(answer: str, expected: str) -> bool:
    return contains(answer, expected) or numeric_close(answer, expected)


# ---------------------------------------------------------------------------
# Fixture metadata
# ---------------------------------------------------------------------------

FIXTURE_METADATA: dict[str, dict] = {
    "toolresult.json": {
        "domain": "Kubernetes",
        "label": "K8s 16-pod node",
        "description": "Kubernetes node summary stats with 16 pods (worker-1)",
    },
    "toolresult2_small.json": {
        "domain": "Kubernetes",
        "label": "K8s 6-pod node",
        "description": "Kubernetes node summary stats with 6 pods (worker-2 subset)",
    },
    "toolresult2.json": {
        "domain": "Kubernetes",
        "label": "K8s 30-pod node",
        "description": "Kubernetes node summary stats with 30 pods (worker-2 full)",
    },
    "aws_ec2_instances.json": {
        "domain": "AWS",
        "label": "EC2 instances",
        "description": "AWS EC2 describe-instances with 20 instances across 3 AZs",
    },
    "db_query_results.json": {
        "domain": "Database",
        "label": "SQL orders",
        "description": "SQL query result set — 150 order rows x 17 columns",
    },
}


# ---------------------------------------------------------------------------
# Questions per fixture
# ---------------------------------------------------------------------------

QUESTIONS: dict[str, list[tuple[str, str, callable]]] = {
    "toolresult.json": [
        # --- direct lookups ---
        (
            "What is the node's available filesystem space in bytes?",
            "29417222144",
            contains,
        ),
        (
            "What is the node's filesystem capacity in bytes?",
            "40571502592",
            contains,
        ),
        (
            "What is the 10-second average CPU PSI (some) value?",
            "1.79",
            contains_or_numeric,
        ),
        (
            "What is the node's memory working set in bytes?",
            "3740188672",
            contains,
        ),
        (
            "What is the node name?",
            "talos-default-worker-1",
            contains,
        ),
        (
            "How many pods are listed in the pods array?",
            "16",
            contains_or_numeric,
        ),
        (
            "What is the node's memory RSS bytes?",
            "2135183360",
            contains,
        ),
        (
            "How many system containers are listed?",
            "3",
            contains_or_numeric,
        ),
        (
            "What namespace is the jaeger pod running in?",
            "ecommerce-prod",
            contains,
        ),
        (
            "What is the node's filesystem used bytes?",
            "11154280448",
            contains,
        ),
        # --- harder: cross-reference, comparison, aggregation ---
        (
            "Which pod has the highest CPU usage (usageNanoCores)? Give the pod name only.",
            "cilium-8z7hq",
            contains,
        ),
        (
            "How many unique namespaces are pods running in?",
            "8",
            contains_or_numeric,
        ),
        (
            "How many pods are in the kube-system namespace?",
            "3",
            contains_or_numeric,
        ),
        (
            "Which pod has the highest memory RSS bytes? Give the pod name only.",
            "kafka",
            contains,
        ),
        (
            "Which system container uses the most CPU (usageNanoCores)? Give the name only.",
            "pods",
            contains,
        ),
        # --- multi-hop, arithmetic, ranking ---
        (
            "What is the memory rssBytes of the pod with the highest CPU usageNanoCores? Give the number only.",
            "136196096",
            contains,
        ),
        (
            "How many pods are NOT in the kube-system namespace?",
            "13",
            contains_or_numeric,
        ),
        (
            "What is the name of the pod with the third highest memory workingSetBytes? Give the pod name only.",
            "cilium",
            contains,
        ),
        (
            "What percentage of node filesystem capacity is used? Round to one decimal place.",
            "27.5",
            contains_or_numeric,
        ),
        (
            "Which pod has the lowest CPU usageNanoCores? Give the pod name only.",
            "kube-proxy",
            contains,
        ),
    ],
    "toolresult2_small.json": [
        # --- direct lookups ---
        (
            "How many pods are listed in the pods array?",
            "6",
            contains_or_numeric,
        ),
        (
            "Which pod has the highest memory working set bytes? Give the pod name only.",
            "opensearch-0",
            contains,
        ),
        (
            "What is the node's filesystem capacity in bytes?",
            "40571502592",
            contains,
        ),
        (
            "What is the memory working set bytes for the grafana pod?",
            "404434944",
            contains,
        ),
        (
            "What is the 10-second average CPU PSI (some) value for the node?",
            "6.24",
            contains_or_numeric,
        ),
        (
            "Which pod has the lowest memory working set bytes? Give the pod name only.",
            "coredns",
            contains,
        ),
        (
            "What is the node name?",
            "talos-default-worker-2",
            contains,
        ),
        (
            "What namespace is the basic-memory pod in?",
            "aura",
            contains,
        ),
        (
            "How many containers does the grafana pod have?",
            "4",
            contains_or_numeric,
        ),
        (
            "What is the IO PSI full avg10 value for the node?",
            "0.44",
            contains_or_numeric,
        ),
        (
            "What is the opensearch pod's memory RSS bytes?",
            "824295424",
            contains,
        ),
        # --- harder: cross-reference, comparison, filtering ---
        (
            "Which pod has the highest CPU usage (usageNanoCores)? Give the pod name only.",
            "grafana",
            contains,
        ),
        (
            "How many pods are in the ecommerce-prod namespace?",
            "3",
            contains_or_numeric,
        ),
        (
            "Which pod has the second highest memory RSS bytes? Give the pod name only.",
            "grafana",
            contains,
        ),
        (
            "How many unique namespaces are pods running in?",
            "3",
            contains_or_numeric,
        ),
        (
            "Which pod has the most volumes? Give the pod name only.",
            "grafana",
            contains,
        ),
        (
            "What is the name of the grafana container that uses the most memory (rssBytes)?",
            "grafana",
            contains,
        ),
        (
            "What is the opensearch container's rootfs used bytes?",
            "2640306176",
            contains,
        ),
        # --- multi-hop, arithmetic, cross-section, ranking ---
        (
            "What is the memory rssBytes of the pod with the highest CPU usageNanoCores? Give the number only.",
            "376483840",
            contains,
        ),
        (
            "How many containers does the pod with the highest memory workingSetBytes have?",
            "1",
            contains_or_numeric,
        ),
        (
            "How many pods are NOT in the kube-system namespace?",
            "4",
            contains_or_numeric,
        ),
        (
            "What is the name of the pod with the third highest memory workingSetBytes? Give the pod name only.",
            "basic-memory",
            contains,
        ),
        (
            "What percentage of node filesystem capacity is used? Round to one decimal place.",
            "44.7",
            contains_or_numeric,
        ),
        (
            "What is the constant ephemeral-storage availableBytes value shared by all pods?",
            "22442622976",
            contains,
        ),
        (
            "How many total containers are there across all pods combined?",
            "9",
            contains_or_numeric,
        ),
    ],
    "toolresult2.json": [
        # --- direct lookups ---
        (
            "How many pods are listed in the pods array?",
            "30",
            contains_or_numeric,
        ),
        (
            "What is the node name?",
            "talos-default-worker-2",
            contains,
        ),
        (
            "What is the 10-second average CPU PSI (some) value for the node?",
            "6.24",
            contains_or_numeric,
        ),
        (
            "What is the node's filesystem capacity in bytes?",
            "40571502592",
            contains,
        ),
        (
            "What is the node's memory working set in bytes?",
            "4382687232",
            contains,
        ),
        # --- cross-reference, comparison ---
        (
            "Which pod has the highest CPU usage (usageNanoCores)? Give the pod name only.",
            "grafana",
            contains,
        ),
        (
            "Which pod has the highest memory working set bytes? Give the pod name only.",
            "opensearch",
            contains,
        ),
        (
            "How many unique namespaces are pods running in?",
            "5",
            contains_or_numeric,
        ),
        (
            "How many pods are in the kube-system namespace?",
            "7",
            contains_or_numeric,
        ),
        (
            "How many pods are in the ecommerce-prod namespace?",
            "20",
            contains_or_numeric,
        ),
        # --- multi-hop, arithmetic, ranking ---
        (
            "What is the memory rssBytes of the pod with the highest CPU usageNanoCores? Give the number only.",
            "376483840",
            contains,
        ),
        (
            "How many pods are NOT in the ecommerce-prod namespace?",
            "10",
            contains_or_numeric,
        ),
        (
            "What percentage of node filesystem capacity is used? Round to one decimal place.",
            "44.7",
            contains_or_numeric,
        ),
        (
            "Which pod has the lowest CPU usageNanoCores? Give the pod name only.",
            "kube-proxy",
            contains,
        ),
        (
            "How many total containers are there across all pods combined?",
            "37",
            contains_or_numeric,
        ),
    ],
    "aws_ec2_instances.json": [
        # --- direct lookups ---
        (
            "How many EC2 instances are listed in total?",
            "20",
            contains_or_numeric,
        ),
        (
            "How many instances are in the 'running' state?",
            "14",
            contains_or_numeric,
        ),
        (
            "How many instances are in the 'stopped' state?",
            "4",
            contains_or_numeric,
        ),
        (
            "How many instances are in the 'terminated' state?",
            "2",
            contains_or_numeric,
        ),
        (
            "How many unique availability zones are instances spread across?",
            "3",
            contains_or_numeric,
        ),
        # --- filtering, counting ---
        (
            "How many instances have the instance type 't3.medium'?",
            "5",
            contains_or_numeric,
        ),
        (
            "How many instances are tagged with Environment=prod?",
            "11",
            contains_or_numeric,
        ),
        (
            "How many instances are tagged with Environment=staging?",
            "7",
            contains_or_numeric,
        ),
        (
            "How many instances are in availability zone us-east-1a?",
            "7",
            contains_or_numeric,
        ),
        (
            "How many instances are tagged with Team=data?",
            "8",
            contains_or_numeric,
        ),
        # --- cross-reference, lookup ---
        (
            "What is the instance type of the instance named 'web-api-prod-00'?",
            "r5.2xlarge",
            contains,
        ),
        (
            "What is the state of the instance named 'scheduler-dev-05'?",
            "stopped",
            contains,
        ),
        (
            "What is the Name tag of instance i-ca4b8601ee8d9224e?",
            "data-pipeline-prod-02",
            contains,
        ),
        # --- multi-hop ---
        (
            "How many 'running' instances have instance type 'm5.large'?",
            "3",
            contains_or_numeric,
        ),
        (
            "How many instances tagged Environment=staging are in the 'running' state?",
            "4",
            contains_or_numeric,
        ),
    ],
    "db_query_results.json": [
        # --- direct lookups ---
        (
            "How many orders are in the data set?",
            "150",
            contains_or_numeric,
        ),
        (
            "How many orders have status 'delivered'?",
            "47",
            contains_or_numeric,
        ),
        (
            "How many orders have status 'cancelled'?",
            "12",
            contains_or_numeric,
        ),
        (
            "How many orders have status 'pending'?",
            "28",
            contains_or_numeric,
        ),
        (
            "How many orders have status 'shipped'?",
            "39",
            contains_or_numeric,
        ),
        # --- filtering, counting ---
        (
            "How many orders use the 'credit_card' payment method?",
            "81",
            contains_or_numeric,
        ),
        (
            "How many orders are in the 'southeast' region?",
            "39",
            contains_or_numeric,
        ),
        (
            "How many orders have a non-zero discount amount?",
            "31",
            contains_or_numeric,
        ),
        (
            "What is the most common currency in the data set?",
            "USD",
            contains,
        ),
        (
            "What is the most common country in the data set?",
            "US",
            contains,
        ),
        # --- cross-reference, extremes ---
        (
            "What is the order_id of the order with the highest total_amount?",
            "ORD-10090",
            contains,
        ),
        (
            "What is the highest total_amount in the data set?",
            "2477.17",
            contains_or_numeric,
        ),
        (
            "What is the order_id of the order with the lowest total_amount?",
            "ORD-10124",
            contains,
        ),
        (
            "How many orders have free shipping (shipping_cost of 0)?",
            "106",
            contains_or_numeric,
        ),
        (
            "How many orders are in the 'northeast' region?",
            "34",
            contains_or_numeric,
        ),
    ],
}
