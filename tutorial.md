# Data Commons Accelerator

<walkthrough-tutorial-duration duration="3"></walkthrough-tutorial-duration>

## Connect

```sh
python3 connect.py
```

The script finds your deployment, connects, and displays links and credentials. Wait for **"Your instance is ready"**, then click **Next**.

---

## Use Your Instance

Everything you need is in the terminal output: app links, admin credentials, and GCS bucket name.

You can also use <walkthrough-spotlight-pointer spotlightId="devshell-web-preview-button">Web Preview</walkthrough-spotlight-pointer> on port 8080.

To upload custom data: `gsutil cp -r ./your-data/* gs://YOUR_BUCKET_NAME/`

---

## Done

<walkthrough-conclusion-trophy></walkthrough-conclusion-trophy>

To reconnect: `python3 connect.py`

[Data Commons docs](https://docs.datacommons.org/custom_dc/) | [Infrastructure Manager](https://console.cloud.google.com/infra-manager/deployments)
