# InTrac

Operation logs and weapon records for a weapon seizure tracing application.

- **ADMINISTRATOR:** creates users with a first name, last name, username, password, and either role.
- **VERIFIER:** creates operation logs, adds individual weapon records, and verifies their own logs to close them.
- Passwords are salted and hashed with scrypt. Sessions use expiring HttpOnly cookies and are stored in SQLite.

## Install and host the complete application

**Start here: [Windows and Mac setup guide](docs/SETUP.md).** It covers a clean computer, downloading this project, installing Docker Desktop, and creating your first administrator. No preinstalled Git, Node.js, Python, or package manager is needed.

- Windows: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup-windows.ps1` in an Administrator PowerShell window.
- Mac: `bash setup-macos.sh` in Terminal as your normal user.

Run the command from the extracted project folder. Windows may require a restart and a rerun. Complete Docker Desktop's first-run prompts. Setup builds the UI and API, starts them, waits for health checks, and asks for an administrator password. Open **http://localhost** and sign in as **admin**.

The Docker stack has a FastAPI container and a Caddy container serving the built React frontend. SQLite, users, records, and photos persist in the `intrac_intrac_data` Docker volume. Local workspace data and passwords are never included in the image or Git repository.

- [Cloudflare guide: every step to a free public HTTPS URL, plus a permanent-domain option](docs/CLOUDFLARE.md)
- [HTTPS on your local network or directly on a public domain](docs/HTTPS.md)
- [Start, stop, update, back up, and restore](docs/OPERATIONS.md)

Cloudflare Tunnel runs alongside the app on your computer. Your computer must remain on; Cloudflare does not provide free Docker hosting for this stack. The no-domain Quick Tunnel is for testing and has a changing address. See the guide for current costs and limits.

## Run locally for development

Requires Python 3.10+ and Node.js 20.19+ or 22.12+.

Start the backend in one terminal:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend in another:

```bash
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. The frontend proxies `/api` to the backend.

The development server also accepts connections from other devices on the same network. On your phone, open `http://<this computer's Wi-Fi IP>:5173` while both servers are running. The computer must remain awake and connected to the network. Browser location on a phone requires trusted HTTPS; use the setup below for automatic location.

### HTTPS for phone location

From `frontend`, generate a local certificate for this computer's Wi-Fi IP, then start HTTPS alongside the existing HTTP server:

```bash
npm run setup:https -- 172.16.0.124
npm run dev:https
```

Replace the example IP if it changes. HTTPS runs on port **5174**, with the same backend and data. The setup command requires OpenSSL and does not change any device's trust settings. It keeps private keys in ignored `.local/https/`; only the public CA certificate is exported in `frontend/public/intrac-local-ca.cer` and the iPhone `.mobileconfig` profile. Never share the private keys.

For iPhone/iPad, on the same Wi-Fi:

1. Open Safari directly and enter `http://<Wi-Fi IP>:5173/intrac-local-ca.mobileconfig` in its address bar. Tap **Allow** when asked to download a configuration profile, then **Close** after **Profile Downloaded** appears.
2. Immediately open **Settings → Profile Downloaded**, or **Settings → General → VPN & Device Management**, and select **InTrac Local Development CA**. Tap **Install**, enter your iPhone passcode if prompted, and complete the installation. The profile contains one root certificate; it includes no device-management enrollment. It is unsigned, so Settings may show **Not Signed**.
3. Open **Settings → General → About → Certificate Trust Settings** and enable full trust for **InTrac Local Development CA**, confirming when prompted. [Apple's installation instructions](https://support.apple.com/en-us/102400) and [SSL trust instructions](https://support.apple.com/en-us/102390).
4. Open `https://<Wi-Fi IP>:5174`, sign in, create a log, and allow location access. The address must load without a certificate warning. If permission was previously denied, enable it in the browser's website settings and the device's Location Services settings.

If no profile appears, reopen the `.mobileconfig` link directly in Safari and ensure you see **Profile Downloaded**. A file saved to Downloads is not evidence that iOS has staged it for installation. Install immediately: Apple removes uninstalled downloaded profiles after eight minutes. If it is already installed under **VPN & Device Management**, continue to the certificate trust step. If iOS shows a restriction or installation error, use that exact message to diagnose it.

Other devices must also import the public certificate as a trusted certificate authority in their operating system/browser before opening the HTTPS address. This trusts certificates signed by this project's local CA; remove that trust when local testing is finished. The server certificate lasts 90 days. Rerun `setup:https` and restart the HTTPS server to renew it or add a new Wi-Fi IP; the existing CA is reused so devices do not need to reinstall it. The CA itself lasts one year.

For a new database, create an administrator from the `backend` directory:

```bash
.venv/bin/python -m app.create_admin --first-name System --last-name Administrator --username admin
```

The command prompts for a password and confirmation. It also accepts `INTRAC_ADMIN_PASSWORD` from the environment for automated setup; no default password is embedded in the application. Existing usernames are never overwritten.

## Data and configuration

- Development uses `backend/data/intrac.db`. Docker uses `/data/intrac.db` inside the persistent `intrac_intrac_data` volume. Users and sessions persist across server restarts.
- Set `INTRAC_DB_PATH` to choose another database file.
- Sessions expire after 12 hours. Sign-out invalidates the server session.
- HTTPS requests automatically receive Secure session cookies. `INTRAC_COOKIE_SECURE=true` can require this on all requests. Serve the frontend and API from the same origin and preserve the original host and scheme in the reverse proxy.
- Usernames are case-insensitive and allow 3–64 letters, numbers, periods, underscores, or hyphens. Passwords require 12–128 characters.

## Verifier workflow

1. Select **Create log** and enter the operation name. Optionally enter the **LAF Soldier Name**: the LAF soldier carrying out the operation you are observing. It starts blank and is separate from the signed-in verifier who verifies the log. Date is filled from your device and can be edited before saving. Time is captured automatically when the form opens.
2. Allow the browser to retrieve your location. If location is unavailable, retry or enter the operation location manually. Browser coordinates and accuracy are saved when available; no external mapping service is used.
3. Create the log, then select **Add weapon**. Item type and quantity are required. Choose **Other / custom** to enter a custom weapon type. Name/model, serial numbers, and a photo are optional. Use **Add serial number** to enter one number per unit where available; unknown numbers can be left blank. Serial numbers must be unique within the entry, and their count cannot exceed its quantity.
4. Save each weapon and add the next one. Select **All logs** to reopen saved operations and their weapon records.
5. Select **Verify log**, check the operation and weapon details, and tick the named accuracy confirmation. **Verify and close log** closes the log and records the verifier's name and verification time. Verified logs and photos remain viewable, and the server prevents further weapon additions.
6. Select **Generate report**, choose an operation-date range, and check the operations to include. All matching operations start selected; uncheck any to exclude them. Download a PDF with a one-page summary followed by photo records for the selected logs. Dates initially cover your full log history; your last chosen dates are remembered per account on this browser. **Entire duration** restores the full range. The summary includes verification totals, recorded quantities, and serial-number coverage by unit (including ammunition).

Each recorded photo appears on a normal PDF page with concise operation, date, location, LAF soldier, weapon, serial-number, and verification details. Long details continue onto additional pages. Original image files are also embedded, named by log and weapon ID, with `photo-metadata.txt` and `photo-metadata.json` indexes containing the complete metadata, including technical file information and record timestamps. Reports without photos contain only the summary.

If another tab adds a weapon while you verify, reload the log and confirm the updated record before closing it. Existing logs migrate to **Unverified** automatically when the backend starts.

Browser location requires permission and a secure context (HTTPS or localhost). Dates display in the viewer's local timezone; timestamps retain their timezone in storage. Logs and photos are restricted to the verifier who created the log. Administrators retain their user-creation view.

Photos accept JPEG, PNG, or WebP up to 8 MB and 20 megapixels. The server verifies image content and stores it with the weapon record in SQLite. Back up the database to retain users, logs, weapons, and photos together.

## Deferred question

How should a log represent multiple LAF soldiers? Not implemented; each log currently has one optional soldier name.

## Verify

```bash
cd backend
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

```bash
cd frontend
npm run build
```

The API tests cover authentication, persistence, session expiry and revocation, role and log ownership restrictions, input validation, photos, duplicate usernames, cookie settings, origin protection, verification confirmation, migration, and concurrent closeout. Browser checks cover sign-in, account creation, log/weapon/verification workflows, errors, and mobile layout.
