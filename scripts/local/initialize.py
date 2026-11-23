"""Idempotent local-only initialization; no observation data or remote services."""

import os
import subprocess
import sys

if sys.argv[1] == "storage":
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["MLFLOW_S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    existing = {b["Name"] for b in client.list_buckets()["Buckets"]}
    for name in ("mlflow", "data"):
        if name not in existing:
            client.create_bucket(Bucket=name)
    print("Local artifact buckets ready")
elif sys.argv[1] == "prefect":
    result = subprocess.run(
        ["prefect", "work-pool", "inspect", "default"], capture_output=True
    )
    if result.returncode:
        subprocess.run(
            ["prefect", "work-pool", "create", "--type", "process", "default"],
            check=True,
        )
    # Upserts every deployment in the single manifest; safe to rerun.
    subprocess.run(
        ["prefect", "deploy", "--prefect-file", "/app/flows/prefect.yaml", "--all"],
        check=True,
    )
    import httpx
    import yaml

    from deeprootgen.pipeline.submission import DEPLOYMENTS

    manifest = yaml.safe_load(open("/app/flows/prefect.yaml"))
    declared = {item["name"] for item in manifest["deployments"]}
    expected = {name.split("/", 1)[1] for name in DEPLOYMENTS.values()}
    if declared != expected:
        raise SystemExit(f"Manifest/page mismatch: {sorted(declared ^ expected)}")
    api = os.environ["PREFECT_API_URL"].rstrip("/")
    missing = [name for name in DEPLOYMENTS.values()
               if httpx.get(f"{api}/deployments/name/{name}", timeout=10).status_code != 200]
    if missing:
        raise SystemExit(f"Deployments missing after registration: {missing}")
    print(f"Registered {len(DEPLOYMENTS)} dashboard deployments on work pool default")
else:
    raise SystemExit("Expected storage or prefect")
