#!/usr/bin/env python3
"""Data Commons Accelerator -- Cloud Shell Connection Tool.

Auto-discovers the Infrastructure Manager deployment, connects to the GKE
cluster, sets up port forwarding, retrieves admin credentials, and presents
clickable access links.

Expected Cloud Shell URL (from Terraform output):
  https://console.cloud.google.com/cloudshell/editor
    ?project=PROJECT_ID
    &cloudshell_git_repo=https://github.com/ORG/cs-connect.git
    &cloudshell_tutorial=tutorial.md
    &show=terminal

The ?project= parameter ensures DEVSHELL_PROJECT_ID is set automatically.
"""

import json
import os
import socket
import subprocess
import sys
import time
from base64 import b64decode

# ---------------------------------------------------------------------------
# Rich library bootstrap -- install automatically if missing
# ---------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    from rich import box
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "--user", "-q", "rich", "questionary"],
    )
    # Refresh sys.path so the freshly-installed packages are importable.
    import importlib
    import site

    importlib.reload(site)
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    from rich import box

console = Console()


# ============================================================================
# Helpers
# ============================================================================

def _run(cmd: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a subprocess with timeout, capturing stdout/stderr."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=f"Command timed out after {timeout}s")


def _fatal(message: str, hint: str | None = None) -> None:
    """Print an error and exit."""
    console.print(f"\n[red]{message}[/red]")
    if hint:
        console.print(f"[dim]{hint}[/dim]")
    sys.exit(1)


# ============================================================================
# Auth: Ensure gcloud is authenticated before any API calls
# ============================================================================

def ensure_auth() -> None:
    """Ensure gcloud is authenticated, triggering login automatically if needed.

    In Cloud Shell the ``gcloud auth login --update-adc`` command opens a
    one-click "Authorize" popup — no copy-pasting or manual commands required.
    After successful auth the active project is set explicitly so that all
    subsequent gcloud/kubectl calls target the correct project.
    """
    # --- silent auth check ---------------------------------------------------
    token_result = _run(["gcloud", "auth", "print-access-token"], timeout=15)
    if token_result.returncode == 0 and token_result.stdout.strip():
        # Already authenticated — make sure the project is set and return.
        _set_active_project()
        return

    # --- not authenticated — run interactive login ----------------------------
    console.print("  [cyan]Authorizing Cloud Shell access...[/cyan]")

    # Must run interactively so the browser/popup auth flow is visible.
    auth_result = subprocess.run(
        ["gcloud", "auth", "login", "--update-adc"],
        check=False,
    )

    if auth_result.returncode != 0:
        _fatal(
            "Authentication did not complete.",
            "Run manually:  gcloud auth login --update-adc",
        )

    # --- verify auth succeeded ------------------------------------------------
    verify = _run(["gcloud", "auth", "print-access-token"], timeout=15)
    if verify.returncode != 0 or not verify.stdout.strip():
        _fatal(
            "Authentication could not be verified.",
            "Run manually:  gcloud auth login --update-adc",
        )

    console.print("  [green]\u2713[/green] Authenticated")

    # --- set project ----------------------------------------------------------
    _set_active_project()


def _set_active_project() -> None:
    """Set the active gcloud project from environment variables."""
    project_id = (
        os.environ.get("DEVSHELL_PROJECT_ID")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or ""
    ).strip()
    if project_id:
        _run(["gcloud", "config", "set", "project", project_id], timeout=10)


# ============================================================================
# Phase 1: Environment Detection
# ============================================================================

def detect_environment() -> dict:
    """Detect Cloud Shell environment and active GCP project."""
    in_cloud_shell = os.environ.get("CLOUD_SHELL") == "true"
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
        "in_cloud_shell": in_cloud_shell,
        "project_id": project_id,
        "web_host": web_host,
    }


# ============================================================================
# Phase 2: Deployment Discovery
# ============================================================================

def discover_deployment(project_id: str) -> dict:
    """Find Data Commons deployment via Infrastructure Manager."""
    result = _run(
        [
            "gcloud", "infra-manager", "deployments", "list",
            f"--project={project_id}",
            "--location=-",
            "--format=json",
        ],
        timeout=60,
    )

    all_deployments: list[dict] = []
    if result.returncode == 0 and result.stdout.strip():
        try:
            deployments = json.loads(result.stdout)
        except json.JSONDecodeError:
            deployments = []
        for d in deployments:
            if d.get("state") == "ACTIVE":
                # Extract location from the resource name field:
                # projects/*/locations/*/deployments/*
                name = d.get("name", "")
                parts = name.split("/")
                if "locations" in parts:
                    loc_idx = parts.index("locations")
                    if loc_idx + 1 < len(parts):
                        d["_location"] = parts[loc_idx + 1]
                all_deployments.append(d)

    if not all_deployments:
        _fatal(
            "No active Infrastructure Manager deployments found.",
            f"Project: {project_id}\n"
            "Ensure your Data Commons deployment completed successfully.\n"
            "Check: https://console.cloud.google.com/infra-manager/deployments",
        )

    if len(all_deployments) == 1:
        return all_deployments[0]

    # Multiple deployments -- let user pick.
    console.print(f"\n[cyan]Found {len(all_deployments)} active deployments:[/cyan]\n")
    names: list[str] = []
    for i, d in enumerate(all_deployments, 1):
        name = d.get("name", "").split("/")[-1]
        names.append(name)
        create_time = d.get("createTime", "unknown")[:19]
        console.print(f"  {i}. {name} (created: {create_time})")
    console.print()

    # Try questionary for a polished selector, fall back to plain input.
    try:
        import questionary

        selected = questionary.select("Select deployment:", choices=names).ask()
        if not selected:
            sys.exit(0)
        return all_deployments[names.index(selected)]
    except ImportError:
        pass

    choice = input(f"Select deployment (1-{len(all_deployments)}): ").strip()
    try:
        idx = int(choice) - 1
        if not 0 <= idx < len(all_deployments):
            raise ValueError
    except ValueError:
        _fatal("Invalid selection.")
    return all_deployments[idx]


# ============================================================================
# Phase 3: Extract Deployment Details
# ============================================================================

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

    # List resources to locate the GKE cluster.
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


# ============================================================================
# Phase 4: Connect to Cluster
# ============================================================================

def connect_to_cluster(details: dict, project_id: str) -> None:
    """Configure kubectl credentials and wait for pods to become ready."""
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

    # Wait for datacommons pods.
    result = _run(
        [
            "kubectl", "wait", "--for=condition=ready", "pod",
            "-l", "app=datacommons",
            f"-n", details["namespace"],
            "--timeout=180s",
        ],
        timeout=200,
    )
    if result.returncode != 0:
        # Show pod status for diagnostics but continue.
        diag = _run(["kubectl", "get", "pods", "-n", details["namespace"]], timeout=10)
        if diag.returncode == 0:
            console.print(f"[dim]{diag.stdout}[/dim]")
        console.print("[yellow]Some pods may not be ready yet. Continuing...[/yellow]")


# ============================================================================
# Phase 5: Port Forwarding and Credentials
# ============================================================================

def start_port_forward(namespace: str) -> subprocess.Popen:
    """Start kubectl port-forward in the background."""
    process = subprocess.Popen(
        [
            "kubectl", "port-forward",
            "-n", namespace,
            "svc/datacommons", "8080:8080",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    # Poll for port to become available (up to 10 seconds)
    for _ in range(20):
        if process.poll() is not None:
            stderr = process.stderr.read().decode() if process.stderr else ""
            _fatal("Port-forward failed.", stderr.strip() or None)
        try:
            with socket.create_connection(("127.0.0.1", 8080), timeout=0.5):
                return process
        except OSError:
            time.sleep(0.5)

    # If still not ready after 10s, check if process is alive
    if process.poll() is not None:
        stderr = process.stderr.read().decode() if process.stderr else ""
        _fatal("Port-forward failed.", stderr.strip() or None)

    return process  # Process alive but port may not be ready yet


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


# ============================================================================
# Phase 6: Display Results
# ============================================================================

def display_results(
    env: dict,
    details: dict,
    username: str,
    password: str,
) -> None:
    """Show clickable links, credentials, and bucket info."""
    web_host = env.get("web_host", "")

    if web_host:
        app_url = f"https://8080-{web_host}"
        admin_url = f"https://8080-{web_host}/admin"
    else:
        app_url = "http://localhost:8080"
        admin_url = "http://localhost:8080/admin"

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


# ============================================================================
# Main
# ============================================================================

def main() -> None:
    """Orchestrate the full connection flow."""

    # Welcome banner
    console.print()
    console.print(
        Panel(
            "[bold white]Data Commons Accelerator[/bold white]\n"
            "[dim]Connecting to your deployed instance...[/dim]",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()

    # Auth: ensure gcloud credentials before any API calls
    ensure_auth()

    # Phase 1: Environment
    with Progress(
        SpinnerColumn(), TextColumn("[cyan]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Detecting environment...", total=None)
        env = detect_environment()
    console.print(f"  [green]\u2713[/green] Project: {env['project_id']}")

    # Phase 2: Discovery
    with Progress(
        SpinnerColumn(), TextColumn("[cyan]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Discovering deployment...", total=None)
        deployment = discover_deployment(env["project_id"])
    deployment_name = deployment.get("name", "").split("/")[-1]
    console.print(f"  [green]\u2713[/green] Deployment: {deployment_name}")

    # Phase 3: Extract details
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

    # Phase 4: Connect
    with Progress(
        SpinnerColumn(), TextColumn("[cyan]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Connecting to cluster and waiting for pods...", total=None)
        connect_to_cluster(details, env["project_id"])
    console.print(f"  [green]\u2713[/green] Connected to cluster")

    # Phase 5: Port forward + credentials
    with Progress(
        SpinnerColumn(), TextColumn("[cyan]{task.description}"),
        console=console, transient=True,
    ) as progress:
        progress.add_task("Setting up access...", total=None)
        pf_process = start_port_forward(details["namespace"])
        username, password = get_credentials(details["namespace"])
    console.print(f"  [green]\u2713[/green] Port forwarding active (localhost:8080)")
    console.print(f"  [green]\u2713[/green] Credentials retrieved")

    # Phase 6: Display results
    display_results(env, details, username, password)

    # Keep running until user exits.
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
        # Escape Rich markup in the error message to avoid rendering issues.
        error_msg = str(exc).replace("[", "\\[").replace("]", "\\]")
        console.print(f"\n[red]Error: {error_msg}[/red]\n")
        sys.exit(1)
