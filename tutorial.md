# Data Commons Accelerator

<walkthrough-tutorial-duration duration="3"></walkthrough-tutorial-duration>

## Connecting

The setup script connects to your deployed Data Commons instance automatically.

If it hasn't started yet, run:

```sh
python3 connect.py
```

Watch the terminal for green checkmarks. Once you see **"Your instance is ready"**, click **Next**.

---

## Access Your Instance

Click the links shown in the terminal:

- **Open Data Commons** -- your main application
- **Open Admin Panel** -- administration at `/admin` (credentials in terminal)

Or use <walkthrough-spotlight-pointer spotlightId="devshell-web-preview-button">Web Preview</walkthrough-spotlight-pointer> on port 8080.

---

## Upload Data

To upload custom data, copy files to the GCS bucket shown in the terminal:

```sh
gsutil cp -r ./your-data/* gs://YOUR_BUCKET_NAME/
```

---

## Done

<walkthrough-conclusion-trophy></walkthrough-conclusion-trophy>

To reconnect: `python3 connect.py`

[Data Commons documentation](https://docs.datacommons.org/custom_dc/) | [Infrastructure Manager](https://console.cloud.google.com/infra-manager/deployments)
