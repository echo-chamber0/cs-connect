# Connect to Data Commons Accelerator

<walkthrough-tutorial-duration duration="3"></walkthrough-tutorial-duration>

## Welcome

The connection script is running automatically in the terminal on the left.

Watch for green checkmarks as it connects to your deployment. No commands needed.

If the script did not start automatically, run it manually:

```sh
python3 connect.py
```

Click **Next** once you see **"Your instance is ready"** in the terminal.

---

## Access Your Instance

The terminal now shows two clickable links:

- **Open Data Commons** -- your main application
- **Open Admin Panel** -- administration interface (credentials shown in terminal)

Click either link, or use the <walkthrough-spotlight-pointer spotlightId="devshell-web-preview-button">Web Preview</walkthrough-spotlight-pointer> button and select **Preview on port 8080**.

---

## Upload Custom Data

Copy files to the GCS bucket shown in the terminal output:

```sh
gsutil cp -r ./your-data/* gs://YOUR_BUCKET_NAME/
```

Replace `YOUR_BUCKET_NAME` with the bucket name from the terminal.

---

## Done

<walkthrough-conclusion-trophy></walkthrough-conclusion-trophy>

To reconnect later:

```sh
python3 connect.py
```

To delete this deployment, use the [Infrastructure Manager console](https://console.cloud.google.com/infra-manager/deployments).

[Data Commons documentation](https://docs.datacommons.org/custom_dc/)
