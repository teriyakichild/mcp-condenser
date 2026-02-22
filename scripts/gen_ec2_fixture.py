#!/usr/bin/env python3
"""Generate a realistic AWS EC2 describe-instances JSON fixture.

Produces ~35-40K tokens of deterministic output at
tests/fixtures/aws_ec2_instances.json.
"""

from __future__ import annotations

import json
import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Deterministic seed
# ---------------------------------------------------------------------------
SEED = 42
rng = random.Random(SEED)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
OWNER_ID = "123456789012"
VPC_ID = "vpc-0a1b2c3d4e5f67890"
IMAGE_ID = "ami-0abcdef1234567890"
KEY_NAME = "prod-us-east-1"
REGION = "us-east-1"

AZS = ["us-east-1a", "us-east-1b", "us-east-1c"]

INSTANCE_TYPES = ["t3.micro", "t3.medium", "m5.large", "m5.xlarge", "r5.2xlarge"]
INSTANCE_TYPE_WEIGHTS = [4, 5, 5, 4, 2]  # how many of each (total 20)

STATES = {
    "running": 14,
    "stopped": 4,
    "terminated": 2,
}

ENVIRONMENTS = ["prod", "staging", "dev"]
TEAMS = ["platform", "data", "backend", "frontend"]
APPLICATIONS = [
    "web-api",
    "auth-service",
    "data-pipeline",
    "metrics-collector",
    "worker",
    "scheduler",
    "gateway",
    "notification-service",
    "search-indexer",
    "cache-warmer",
    "log-aggregator",
    "config-server",
    "ml-inference",
    "batch-processor",
    "cdn-origin",
    "admin-dashboard",
    "billing-service",
    "audit-trail",
    "feature-flags",
    "health-checker",
]
COST_CENTERS = ["CC-1001", "CC-1002", "CC-1003", "CC-2001", "CC-2002", "CC-3001"]

SUBNET_MAP = {
    "us-east-1a": ["subnet-0aaa1111bbbb2222c", "subnet-0aaa3333dddd4444e"],
    "us-east-1b": ["subnet-0bbb5555eeee6666f", "subnet-0bbb7777ffff8888a"],
    "us-east-1c": ["subnet-0ccc9999aaaa0000b", "subnet-0cccbbbbccccdddd1"],
}

SG_POOL = [
    {"GroupId": "sg-0a1b2c3d4e5f00001", "GroupName": "default"},
    {"GroupId": "sg-0a1b2c3d4e5f00002", "GroupName": "web-tier"},
    {"GroupId": "sg-0a1b2c3d4e5f00003", "GroupName": "app-tier"},
    {"GroupId": "sg-0a1b2c3d4e5f00004", "GroupName": "db-tier"},
    {"GroupId": "sg-0a1b2c3d4e5f00005", "GroupName": "monitoring"},
    {"GroupId": "sg-0a1b2c3d4e5f00006", "GroupName": "bastion-access"},
    {"GroupId": "sg-0a1b2c3d4e5f00007", "GroupName": "internal-services"},
    {"GroupId": "sg-0a1b2c3d4e5f00008", "GroupName": "load-balancer"},
]

# Base time for LaunchTime spread
BASE_TIME = datetime(2026, 2, 15, 8, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _hex(n: int) -> str:
    return "".join(rng.choices("0123456789abcdef", k=n))


def _instance_id() -> str:
    return f"i-{_hex(17)}"


def _reservation_id() -> str:
    return f"r-{_hex(17)}"


def _eni_id() -> str:
    return f"eni-{_hex(17)}"


def _vol_id() -> str:
    return f"vol-{_hex(17)}"


def _attachment_id() -> str:
    return f"eni-attach-{_hex(17)}"


def _private_ip() -> str:
    return f"10.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def _public_ip() -> str:
    return f"{rng.randint(3, 54)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


def _private_dns(ip: str) -> str:
    return f"ip-{ip.replace('.', '-')}.ec2.internal"


def _public_dns(ip: str) -> str:
    return f"ec2-{ip.replace('.', '-')}.compute-1.amazonaws.com"


def _mac() -> str:
    return ":".join(_hex(2) for _ in range(6))


def _launch_time(index: int) -> str:
    """Spread launches over ~5 days with some variation."""
    offset_hours = rng.randint(0, 120)
    offset_minutes = rng.randint(0, 59)
    offset_seconds = rng.randint(0, 59)
    dt = BASE_TIME + timedelta(hours=offset_hours, minutes=offset_minutes, seconds=offset_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _iam_instance_profile(app_name: str) -> dict:
    profile_name = f"{app_name}-instance-profile"
    return {
        "Arn": f"arn:aws:iam::{OWNER_ID}:instance-profile/{profile_name}",
        "Id": f"AIPA{''.join(rng.choices(string.ascii_uppercase + string.digits, k=17))}",
    }


def _ebs_volume(instance_id: str, device: str, size_gb: int, vol_type: str, attach_time: str) -> dict:
    return {
        "DeviceName": device,
        "Ebs": {
            "AttachTime": attach_time,
            "DeleteOnTermination": device == "/dev/xvda",
            "Status": "attached",
            "VolumeId": _vol_id(),
        },
    }


def _network_interface(
    index: int,
    subnet_id: str,
    az: str,
    security_groups: list[dict],
    is_running: bool,
) -> dict:
    priv_ip = _private_ip()
    mac = _mac()
    eni_id = _eni_id()
    attachment_id = _attachment_id()

    eni: dict = {
        "Association": None,
        "Attachment": {
            "AttachTime": _launch_time(0),
            "AttachmentId": attachment_id,
            "DeleteOnTermination": index == 0,
            "DeviceIndex": index,
            "Status": "attached",
            "NetworkCardIndex": 0,
        },
        "Description": f"Primary network interface" if index == 0 else f"Secondary network interface",
        "Groups": security_groups,
        "Ipv6Addresses": [],
        "MacAddress": mac,
        "NetworkInterfaceId": eni_id,
        "OwnerId": OWNER_ID,
        "PrivateDnsName": _private_dns(priv_ip),
        "PrivateIpAddress": priv_ip,
        "PrivateIpAddresses": [
            {
                "Primary": True,
                "PrivateDnsName": _private_dns(priv_ip),
                "PrivateIpAddress": priv_ip,
            }
        ],
        "SourceDestCheck": True,
        "Status": "in-use",
        "SubnetId": subnet_id,
        "VpcId": VPC_ID,
        "InterfaceType": "interface",
    }

    # Running instances get a public IP on the primary ENI
    if is_running and index == 0:
        pub_ip = _public_ip()
        eni["Association"] = {
            "IpOwnerId": "amazon",
            "PublicDnsName": _public_dns(pub_ip),
            "PublicIp": pub_ip,
        }
        eni["PrivateIpAddresses"][0]["Association"] = {
            "IpOwnerId": "amazon",
            "PublicDnsName": _public_dns(pub_ip),
            "PublicIp": pub_ip,
        }
    else:
        del eni["Association"]

    return eni


# ---------------------------------------------------------------------------
# Build the instance list
# ---------------------------------------------------------------------------
def _build_instance_type_pool() -> list[str]:
    """Create a pool of 20 instance types matching the weights."""
    pool: list[str] = []
    for itype, count in zip(INSTANCE_TYPES, INSTANCE_TYPE_WEIGHTS):
        pool.extend([itype] * count)
    rng.shuffle(pool)
    return pool


def _build_state_list() -> list[str]:
    """Build the ordered state list then shuffle."""
    states: list[str] = []
    for state, count in STATES.items():
        states.extend([state] * count)
    rng.shuffle(states)
    return states


STATE_CODES = {
    "running": 16,
    "stopped": 80,
    "terminated": 48,
}


def build_instance(index: int, instance_type: str, state: str) -> dict:
    iid = _instance_id()
    az = AZS[index % len(AZS)]
    subnets = SUBNET_MAP[az]
    primary_subnet = subnets[0]
    app_name = APPLICATIONS[index]
    env = rng.choice(ENVIRONMENTS)
    team = rng.choice(TEAMS)
    cost_center = rng.choice(COST_CENTERS)
    launch_time = _launch_time(index)
    is_running = state == "running"

    # Security groups: 2-3 per instance
    num_sgs = rng.randint(2, 3)
    sgs = rng.sample(SG_POOL, num_sgs)

    # Network interfaces: 1-2 per instance
    num_enis = rng.choice([1, 1, 1, 2])  # weighted toward 1
    enis = []
    for eni_idx in range(num_enis):
        subnet = subnets[eni_idx % len(subnets)]
        enis.append(_network_interface(eni_idx, subnet, az, sgs, is_running))

    primary_eni = enis[0]
    priv_ip = primary_eni["PrivateIpAddress"]
    priv_dns = primary_eni["PrivateDnsName"]

    # EBS volumes
    root_vol = _ebs_volume(iid, "/dev/xvda", rng.choice([8, 20, 30]), "gp3", launch_time)
    block_devices = [root_vol]
    if instance_type.startswith(("m5", "r5")):
        data_vol = _ebs_volume(
            iid,
            "/dev/xvdb",
            rng.choice([50, 100, 200, 500]),
            rng.choice(["gp3", "io1", "st1"]),
            launch_time,
        )
        block_devices.append(data_vol)
    if instance_type.startswith("r5"):
        extra_vol = _ebs_volume(
            iid,
            "/dev/xvdc",
            rng.choice([200, 500, 1000]),
            "gp3",
            launch_time,
        )
        block_devices.append(extra_vol)

    # Tags
    tags = [
        {"Key": "Name", "Value": f"{app_name}-{env}-{index:02d}"},
        {"Key": "Environment", "Value": env},
        {"Key": "Team", "Value": team},
        {"Key": "CostCenter", "Value": cost_center},
        {"Key": "Application", "Value": app_name},
        {"Key": "ManagedBy", "Value": "terraform"},
        {"Key": "aws:autoscaling:groupName", "Value": f"asg-{app_name}-{env}"},
        {"Key": "kubernetes.io/cluster/main", "Value": "owned"},
        {"Key": "CreatedBy", "Value": f"arn:aws:iam::{OWNER_ID}:role/deploy-{team}"},
    ]

    # Monitoring
    monitoring = {"State": "enabled" if env == "prod" else "disabled"}

    # Placement
    placement = {
        "AvailabilityZone": az,
        "GroupName": "",
        "Tenancy": "default",
    }

    # CpuOptions - vary by instance type
    cpu_map = {
        "t3.micro": {"CoreCount": 1, "ThreadsPerCore": 2},
        "t3.medium": {"CoreCount": 1, "ThreadsPerCore": 2},
        "m5.large": {"CoreCount": 1, "ThreadsPerCore": 2},
        "m5.xlarge": {"CoreCount": 2, "ThreadsPerCore": 2},
        "r5.2xlarge": {"CoreCount": 4, "ThreadsPerCore": 2},
    }

    instance: dict = {
        "AmiLaunchIndex": 0,
        "ImageId": IMAGE_ID,
        "InstanceId": iid,
        "InstanceType": instance_type,
        "KeyName": KEY_NAME,
        "LaunchTime": launch_time,
        "Monitoring": monitoring,
        "Placement": placement,
        "PrivateDnsName": priv_dns,
        "PrivateIpAddress": priv_ip,
        "ProductCodes": [],
        "PublicDnsName": "",
        "State": {
            "Code": STATE_CODES[state],
            "Name": state,
        },
        "StateTransitionReason": "" if state == "running" else f"User initiated ({_launch_time(index)})",
        "SubnetId": primary_subnet,
        "VpcId": VPC_ID,
        "Architecture": "x86_64",
        "BlockDeviceMappings": block_devices,
        "ClientToken": str(uuid.UUID(int=rng.getrandbits(128))),
        "EbsOptimized": instance_type not in ("t3.micro",),
        "EnaSupport": True,
        "Hypervisor": "xen",
        "IamInstanceProfile": _iam_instance_profile(app_name),
        "NetworkInterfaces": enis,
        "RootDeviceName": "/dev/xvda",
        "RootDeviceType": "ebs",
        "SecurityGroups": sgs,
        "SourceDestCheck": True,
        "Tags": tags,
        "VirtualizationType": "hvm",
        "CpuOptions": cpu_map[instance_type],
        "CapacityReservationSpecification": {"CapacityReservationPreference": "open"},
        "HibernationOptions": {"Configured": False},
        "MetadataOptions": {
            "State": "applied",
            "HttpTokens": "required",
            "HttpPutResponseHopLimit": 2,
            "HttpEndpoint": "enabled",
            "HttpProtocolIpv6": "disabled",
            "InstanceMetadataTags": "disabled",
        },
        "EnclaveOptions": {"Enabled": False},
        "PlatformDetails": "Linux/UNIX",
        "UsageOperation": "RunInstances",
        "UsageOperationUpdateTime": launch_time,
        "MaintenanceOptions": {"AutoRecovery": "default"},
        "CurrentInstanceBootMode": "legacy-bios",
    }

    # Running instances get public IP info
    if is_running and "Association" in primary_eni:
        instance["PublicDnsName"] = primary_eni["Association"]["PublicDnsName"]
        instance["PublicIpAddress"] = primary_eni["Association"]["PublicIp"]

    # Terminated instances lose some fields
    if state == "terminated":
        instance["StateReason"] = {
            "Code": "Client.UserInitiatedShutdown",
            "Message": "Client.UserInitiatedShutdown: User initiated shutdown",
        }

    return instance


def build_response() -> dict:
    """Build the full DescribeInstances-style response."""
    type_pool = _build_instance_type_pool()
    state_list = _build_state_list()

    # Group into reservations (4-6 instances each, simulating launch groups)
    reservations = []
    instances_all = []

    for i in range(20):
        inst = build_instance(i, type_pool[i], state_list[i])
        instances_all.append(inst)

    # Split into reservations of varying sizes
    reservation_sizes = [5, 4, 4, 3, 4]  # = 20
    offset = 0
    for size in reservation_sizes:
        chunk = instances_all[offset : offset + size]
        offset += size
        reservations.append(
            {
                "ReservationId": _reservation_id(),
                "OwnerId": OWNER_ID,
                "Groups": [],
                "Instances": chunk,
            }
        )

    return {"Reservations": reservations}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    response = build_response()
    output_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "aws_ec2_instances.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    json_text = json.dumps(response, indent=2)
    output_path.write_text(json_text + "\n")

    size_kb = len(json_text) / 1024
    num_instances = sum(len(r["Instances"]) for r in response["Reservations"])
    num_reservations = len(response["Reservations"])

    print(f"Wrote {output_path}")
    print(f"  Reservations: {num_reservations}")
    print(f"  Instances:    {num_instances}")
    print(f"  File size:    {size_kb:.1f} KB")
    print(f"  Characters:   {len(json_text):,}")


if __name__ == "__main__":
    main()
