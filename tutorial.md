# Data Commons Quick Start

<walkthrough-tutorial-duration duration="5"></walkthrough-tutorial-duration>

## Connect to Your Instance

Run the connection script:

```sh
python3 connect.py
```

Wait for **"Your instance is ready"** to appear. The script displays your app URL, admin URL, credentials, and GCS bucket name. Keep this terminal open.

---

## Explore the Application

- Open the **app link** from the terminal output, or use <walkthrough-spotlight-pointer spotlightId="devshell-web-preview-button">Web Preview</walkthrough-spotlight-pointer> on port 8080
- Type a natural language query in the search bar, for example:
  - *"Population of California over time"*
  - *"Median household income in US counties"*
- Browse the built-in tools:
  - **Timeline** (`/tools/timeline`) — plot statistical variables over time
  - **Map** (`/tools/map`) — compare a variable across regions
  - **Stat Var Explorer** (`/tools/statvar`) — browse available variables and their metadata

---

## Admin Panel

- Open the **admin link** from the terminal and log in with the displayed credentials
- **Data & Files** tab — upload CSV data files directly through the browser
- **Theme Settings** tab — customize logo, site name, domain, and contact info

---

## Done

<walkthrough-conclusion-trophy></walkthrough-conclusion-trophy>

To reconnect later: `python3 connect.py`

- [Data Commons documentation](https://docs.datacommons.org/custom_dc/)
- [Infrastructure Manager](https://console.cloud.google.com/infra-manager/deployments)


cd /home/ubuntu/.claude && claude --resume 6cff5424-cab3-4cbd-b9bc-ae6b02956d82
