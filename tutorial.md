# Connect to Data Commons Accelerator

## Welcome

This tool connects you to your deployed Data Commons Accelerator instance.

**Time to complete:** Under 3 minutes

<walkthrough-tutorial-duration duration="3"></walkthrough-tutorial-duration>

Everything runs automatically -- watch the terminal on the left.

Click **Next** to learn what's happening.

---

## Automatic Setup

The terminal is running an automated connection tool that:

1. Finds your Data Commons deployment
2. Connects to your GKE cluster
3. Sets up secure port forwarding
4. Retrieves your admin credentials

**No commands needed.** Just wait for the green checkmarks to appear.

Click **Next** once you see "Your instance is ready" in the terminal.

---

## Access Your Instance

After setup completes, you'll see two clickable links in the terminal:

- **Open Data Commons** -- your main application
- **Open Admin Panel** -- administration interface at `/admin`

Click either link to open in a new tab.

You can also use the <walkthrough-spotlight-pointer spotlightId="devshell-web-preview-button">Web Preview</walkthrough-spotlight-pointer> button and select **Preview on port 8080**.

Click **Next** to learn about the admin panel.

---

## Admin Panel

The admin panel lets you:

- Monitor data import status
- Configure data sources
- View system health
- Manage application settings

Your admin credentials are displayed in the terminal output.

Click **Next** for data upload instructions.

---

## Upload Custom Data

To upload your own data to Data Commons, use the GCS bucket shown in the terminal output:

```sh
gsutil cp -r /path/to/your/data gs://YOUR_BUCKET_NAME/input
```

Replace `YOUR_BUCKET_NAME` with the bucket name from the terminal.

**Supported formats:** CSV, JSON, MCF

After uploading, the data sync process will automatically import your data (if enabled during deployment).

Click **Next** to finish.

---

## Troubleshooting

If the automatic setup fails, you can run these commands manually:

**Connect to your cluster:**
```sh
gcloud container clusters get-credentials CLUSTER_NAME --region=REGION --project=PROJECT_ID
```

**Set up port forwarding:**
```sh
kubectl port-forward -n NAMESPACE svc/datacommons 8080:8080
```

**Get admin credentials:**
```sh
kubectl get secret datacommons -n NAMESPACE -o jsonpath='{.data.ADMIN_PANEL_PASSWORD}' | base64 -d
```

Replace CLUSTER_NAME, REGION, PROJECT_ID, and NAMESPACE with your deployment values.

Click **Next** to complete.

---

## Done

<walkthrough-conclusion-trophy></walkthrough-conclusion-trophy>

Your Data Commons Accelerator instance is ready.

**Keep this Cloud Shell tab open** to maintain the port forwarding connection. If it disconnects, simply re-run:

```sh
python3 connect.py
```

**Useful links:**
- [Data Commons Documentation](https://docs.datacommons.org/)
- [Custom Data Commons Guide](https://docs.datacommons.org/custom_dc/)
- [GCP Marketplace](https://console.cloud.google.com/marketplace)

**Cloud Shell URL format** (for sharing or bookmarking):
```
https://console.cloud.google.com/cloudshell/editor?project=PROJECT_ID&cloudshell_git_repo=https://github.com/ORG/cs-connect.git&cloudshell_tutorial=tutorial.md&show=terminal
```
Use `console.cloud.google.com` (not `shell.cloud.google.com`) to support the `?project=` parameter for auto-setting GCP project context.

To clean up resources, delete the deployment from the Infrastructure Manager console.
