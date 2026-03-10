#!/usr/bin/env python3
"""Cloud Shell connection tool for Data Commons Accelerator.

Usage: python3 connect.py
"""

import json
import os
import socket
import subprocess
import sys
import time
from base64 import b64decode

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    import questionary
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--user", "-q",
         "rich", "questionary"],
    )
    import importlib
    import site

    importlib.reload(site)
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
    try:
        import questionary
    except ImportError:
        questionary = None

console = Console()


def _run(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a subprocess with timeout."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=f"Command timed out after {timeout}s")


def _fatal(message: str, hint: str | None = None) -> None:
    """Print error and exit."""
    console.print(f"\n[red]{message}[/red]")
    if hint:
        console.print(f"[dim]{hint}[/dim]")
    sys.exit(1)


def _find_free_port(start: int = 8080, max_attempts: int = 10) -> int:
    """Find an available local port starting from *start*."""
    for port in range(start, start + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    _fatal(f"No free port found in range {start}-{start + max_attempts - 1}.")


def detect_environment() -> dict:
    """Detect Cloud Shell environment and active GCP project."""
    project_id = (
        os.environ.get("DEVSHELL_PROJECT_ID")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or ""
    ).strip()
    web_host = os.environ.get("WEB_HOST", "").strip()

    if not project_id:
        result = _run(["gcloud", "config", "get-value", "project"], timeout=10)
        if result.returncode == 0:
            project_id = result.stdout.strip()

    if not project_id:
        _fatal(
            "Could not detect GCP project.",
            "Set your project: gcloud config set project YOUR_PROJECT_ID",
        )

    return {
        "project_id": project_id,
        "web_host": web_host,
    }


def _is_datacommons_deployment(deployment: dict) -> bool:
    """Check whether an Infrastructure Manager deployment is Data Commons."""
    blueprint = deployment.get("terraformBlueprint")
    if isinstance(blueprint, dict):
        input_values = blueprint.get("inputValues")
        if isinstance(input_values, dict):
            helm_entry = input_values.get("helm_chart_name")
            if isinstance(helm_entry, dict):
                chart_name = helm_entry.get("inputValue", "")
                if isinstance(chart_name, str) and "datacommons" in chart_name.lower():
                    return True

    name = deployment.get("name", "")
    if isinstance(name, str) and "datacommons" in name.lower():
        return True

    return False


def discover_deployments(project_id: str) -> list[dict]:
    """Fetch active Data Commons deployments from Infrastructure Manager."""
    result = _run(
        [
            "gcloud", "infra-manager", "deployments", "list",
            f"--project={project_id}",
            "--location=-",
            "--format=json",
        ],
        timeout=60,
    )

    active_deployments: list[dict] = []
    if result.returncode == 0 and result.stdout.strip():
        try:
            deployments = json.loads(result.stdout)
        except json.JSONDecodeError:
            deployments = []
        for d in deployments:
            if d.get("state") == "ACTIVE":
                name = d.get("name", "")
                parts = name.split("/")
                if "locations" in parts:
                    loc_idx = parts.index("locations")
                    if loc_idx + 1 < len(parts):
                        d["_location"] = parts[loc_idx + 1]
                active_deployments.append(d)

    if not active_deployments:
        _fatal(
            "No active Infrastructure Manager deployments found.",
            f"Project: {project_id}\n"
            "Ensure your Data Commons deployment completed successfully.\n"
            "Check: https://console.cloud.google.com/infra-manager/deployments",
        )

    dc_deployments = [d for d in active_deployments if _is_datacommons_deployment(d)]

    if not dc_deployments:
        _fatal(
            f"No Data Commons deployments found ({len(active_deployments)} other deployment"
            f"{'s' if len(active_deployments) != 1 else ''} exist).",
            "This tool only works with Data Commons Accelerator deployments from GCP Marketplace.",
        )

    return dc_deployments


def select_deployment(dc_deployments: list[dict]) -> dict:
    """Let the user pick a deployment when multiple exist."""
    if len(dc_deployments) == 1:
        return dc_deployments[0]

    labels: list[str] = []
    for d in dc_deployments:
        name = d.get("name", "").split("/")[-1]
        region = d.get("_location", "unknown")
        create_date = d.get("createTime", "")[:10] or "unknown"
        labels.append(f"{name} ({region}, created: {create_date})")

    if questionary:
        console.print()
        selected = questionary.select(
            "Select deployment:",
            choices=labels,
        ).ask()
        if not selected:
            sys.exit(0)
        return dc_deployments[labels.index(selected)]

    console.print()
    for i, label in enumerate(labels, 1):
        console.print(f"  {i}. {label}")
    console.print()
    choice = input(f"Select deployment (1-{len(dc_deployments)}): ").strip()
    try:
        idx = int(choice) - 1
        if not 0 <= idx < len(dc_deployments):
            raise ValueError
    except ValueError:
        _fatal("Invalid selection.")
    return dc_deployments[idx]


def extract_details(deployment: dict, project_id: str) -> dict:
    """Extract cluster name, region, namespace from the deployment."""
    deployment_name = deployment.get("name", "")
    location = deployment.get("_location", "us-central1")

    latest_revision = deployment.get("latestRevision", "")
    if not latest_revision:
        deployment_short = deployment_name.split("/")[-1]
        latest_revision = (
            f"projects/{project_id}/locations/{location}"
            f"/deployments/{deployment_short}/revisions/r-0"
        )

    result = _run(
        [
            "gcloud", "infra-manager", "resources", "list",
            f"--revision={latest_revision}",
            "--format=json",
        ],
        timeout=30,
    )

    cluster_name: str | None = None
    cluster_region: str | None = None
    namespace: str | None = None
    gcs_bucket: str | None = None

    if result.returncode == 0 and result.stdout.strip():
        try:
            resources = json.loads(result.stdout)
        except json.JSONDecodeError:
            resources = []

        for r in resources:
            if not isinstance(r, dict):
                continue
            tf_info = r.get("terraformInfo", {})
            if not isinstance(tf_info, dict):
                continue
            tf_type = tf_info.get("type", "")
            tf_id = tf_info.get("id", "")

            if tf_type == "google_container_cluster":
                cluster_name = tf_id
                for asset in r.get("caiAssets", []):
                    if not isinstance(asset, dict):
                        continue
                    full_name = asset.get("fullResourceName", "")
                    parts = full_name.split("/")
                    if "locations" in parts:
                        loc_idx = parts.index("locations")
                        if loc_idx + 1 < len(parts):
                            cluster_region = parts[loc_idx + 1]

            if tf_type == "kubernetes_namespace":
                namespace = tf_id

            if tf_type == "google_storage_bucket":
                gcs_bucket = tf_id

    # Fallback: read revision outputs.
    if not cluster_name or not namespace:
        rev_result = _run(
            [
                "gcloud", "infra-manager", "revisions", "describe",
                latest_revision, "--format=json",
            ],
            timeout=30,
        )
        if rev_result.returncode == 0 and rev_result.stdout.strip():
            try:
                revision = json.loads(rev_result.stdout)
                outputs = revision.get("applyResults", {}).get("outputs", {})
                if not isinstance(outputs, dict):
                    outputs = {}
                if "namespace" in outputs:
                    raw = outputs["namespace"]
                    namespace = namespace or (raw.get("value") if isinstance(raw, dict) else raw)
                if "gcs_bucket_url" in outputs:
                    raw = outputs["gcs_bucket_url"]
                    gcs_bucket = gcs_bucket or (raw.get("value") if isinstance(raw, dict) else raw)
            except json.JSONDecodeError:
                pass

    if not cluster_name:
        _fatal(
            "Could not find GKE cluster in deployment.",
            "Verify the deployment includes a google_container_cluster resource.",
        )

    cluster_region = cluster_region or location
    namespace = namespace or deployment_name.split("/")[-1]

    return {
        "cluster_name": cluster_name,
        "region": cluster_region,
        "namespace": namespace,
        "gcs_bucket": gcs_bucket,
    }


def connect_to_cluster(details: dict, project_id: str) -> None:
    """Configure kubectl credentials for the target cluster."""
    result = _run(
        [
            "gcloud", "container", "clusters", "get-credentials",
            details["cluster_name"],
            f"--region={details['region']}",
            f"--project={project_id}",
        ],
        timeout=60,
    )
    if result.returncode != 0:
        _fatal(
            f"Failed to connect to cluster: {details['cluster_name']}",
            result.stderr.strip() or None,
        )


def start_port_forward(namespace: str, local_port: int) -> tuple[subprocess.Popen, int]:
    """Start kubectl port-forward in the background.

    Returns (process, local_port).
    """
    process = subprocess.Popen(
        [
            "kubectl", "port-forward",
            "-n", namespace,
            "svc/datacommons", f"{local_port}:8080",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    for _ in range(20):
        if process.poll() is not None:
            stderr = process.stderr.read().decode() if process.stderr else ""
            _fatal("Port-forward failed.", stderr.strip() or None)
        try:
            with socket.create_connection(("127.0.0.1", local_port), timeout=0.5):
                return process, local_port
        except OSError:
            time.sleep(0.5)

    if process.poll() is not None:
        stderr = process.stderr.read().decode() if process.stderr else ""
        _fatal("Port-forward failed.", stderr.strip() or None)

    return process, local_port


def get_credentials(namespace: str) -> tuple[str, str]:
    """Retrieve admin credentials from the Kubernetes secret."""
    username = ""
    password = ""

    try:
        result = _run(
            [
                "kubectl", "get", "secret", "datacommons",
                "-n", namespace,
                "-o", "jsonpath={.data.ADMIN_PANEL_USERNAME}",
            ],
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            username = b64decode(result.stdout.strip()).decode()

        result = _run(
            [
                "kubectl", "get", "secret", "datacommons",
                "-n", namespace,
                "-o", "jsonpath={.data.ADMIN_PANEL_PASSWORD}",
            ],
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            password = b64decode(result.stdout.strip()).decode()
    except Exception as exc:
        console.print(f"[yellow]Warning: Could not retrieve credentials: {exc}[/yellow]")

    return username or "admin", password or "(could not retrieve)"


def display_results(
    env: dict,
    details: dict,
    username: str,
    password: str,
    local_port: int = 8080,
) -> None:
    """Show clickable links, credentials, and bucket info."""
    web_host = env.get("web_host", "")

    if web_host:
        app_url = f"https://{local_port}-{web_host}"
        admin_url = f"https://{local_port}-{web_host}/admin"
    else:
        app_url = f"http://localhost:{local_port}"
        admin_url = f"http://localhost:{local_port}/admin"

    gcs_line = ""
    if details.get("gcs_bucket"):
        gcs_line = f"\n  [cyan]Data Bucket:[/cyan]  {details['gcs_bucket']}"

    body = (
        f"\n"
        f"  [bold cyan]Open Data Commons:[/bold cyan]\n"
        f"    {app_url}\n"
        f"\n"
        f"  [bold cyan]Open Admin Panel:[/bold cyan]\n"
        f"    {admin_url}\n"
        f"\n"
        f"  [cyan]Admin Username:[/cyan]  {username}\n"
        f"  [cyan]Admin Password:[/cyan]  {password}"
        f"{gcs_line}\n"
        f"\n"
        f"  [dim]Port forwarding is active. Press Ctrl+C to stop.[/dim]\n"
    )

    console.print()
    console.print(
        Panel(
            body,
            title="[bold white] Data Commons Accelerator [/bold white]",
            subtitle="[bold green]Your instance is ready[/bold green]",
            border_style="green",
            box=box.DOUBLE,
            padding=(1, 2),
        )
    )
    console.print()


def main() -> None:
    console.print()
    console.print(
        Panel(
            "[bold white]Data Commons Accelerator[/bold white]\n"
            "[dim]Connecting to your deployed instance...[/dim]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
            width=50,
        )
    )
    console.print()

    with Progress(
        SpinnerColumn(), TextColumn("[cyan]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Detecting environment...", total=None)
        env = detect_environment()
    console.print(f"  [green]\u2713[/green] Project: {env['project_id']}")

    with Progress(
        SpinnerColumn(), TextColumn("[cyan]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Discovering deployments...", total=None)
        dc_deployments = discover_deployments(env["project_id"])
    console.print(f"  [green]\u2713[/green] Found {len(dc_deployments)} deployment{'s' if len(dc_deployments) != 1 else ''}")

    deployment = select_deployment(dc_deployments)
    deployment_name = deployment.get("name", "").split("/")[-1]
    console.print(f"  [green]\u2713[/green] Selected: {deployment_name}")

    with Progress(
        SpinnerColumn(), TextColumn("[cyan]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Reading deployment configuration...", total=None)
        details = extract_details(deployment, env["project_id"])
    console.print(
        f"  [green]\u2713[/green] Cluster: {details['cluster_name']} ({details['region']})"
    )
    console.print(f"  [green]\u2713[/green] Namespace: {details['namespace']}")

    with Progress(
        SpinnerColumn(), TextColumn("[cyan]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Connecting to cluster...", total=None)
        connect_to_cluster(details, env["project_id"])
    console.print(f"  [green]\u2713[/green] Connected to cluster")

    with Progress(
        SpinnerColumn(), TextColumn("[cyan]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Setting up access...", total=None)
        local_port = _find_free_port()
        pf_process, local_port = start_port_forward(details["namespace"], local_port)
        username, password = get_credentials(details["namespace"])
    console.print(f"  [green]\u2713[/green] Port forwarding active (port {local_port})")
    console.print(f"  [green]\u2713[/green] Credentials retrieved")

    display_results(env, details, username, password, local_port)

    try:
        pf_process.wait()
    except KeyboardInterrupt:
        console.print("\n[dim]Stopping port forwarding...[/dim]")
        pf_process.terminate()
        try:
            pf_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pf_process.kill()
        console.print("[dim]Done. Run this tool again to reconnect.[/dim]\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]\n")
        sys.exit(0)
    except Exception as exc:
        error_msg = str(exc).replace("[", "\\[").replace("]", "\\]")
        console.print(f"\n[red]Error: {error_msg}[/red]\n")
        sys.exit(1)
