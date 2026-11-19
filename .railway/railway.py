"""Railway settings for the OPTIONAL online copy of WattWise (synthetic data only).

This replaces railway.json (Railway stops reading railway.json on 2026-12-01).
The competition demo does not need it: locally, use scripts/run_demo.py.
Preview a change with `railway config plan`, then `railway config apply`.
Needs `pip install railway-sdk` on the machine that runs those commands.
"""

from railway_sdk import define_railway, github, project, service, volume

# This repository manages only its own resources in the Railway project.
PARTIAL = "WattWise"


@define_railway
def main(ctx=None):
    # The database lives on this volume so it survives a redeploy.
    data = volume("wattwise-volume", region="sfo", sizeMB=500)

    wattwise = service(
        "WattWise",
        source=github("dxqxwm6ctk-spec/WattWise", branch="main"),
        start="python scripts/cloud_start.py",
        healthcheck="/api/health",
        healthcheckTimeout=120,
        deploy={"restartPolicyType": "ON_FAILURE", "restartPolicyMaxRetries": 5},
        env={"WATTWISE_DB": "/data/wattwise.db"},
        volumeMounts={"/data": data},
    )
    return project("resourceful-reprieve", resources=[data, wattwise])
