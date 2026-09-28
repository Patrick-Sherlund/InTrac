# Put InTrac online through Cloudflare: a complete beginner's guide

Last checked: September 28, 2026. Dashboard labels can change; links to Cloudflare's instructions are included at the relevant steps.

## Read this first: what “free hosting” means here

**Your Windows PC or Mac runs InTrac and stores its database. Cloudflare Tunnel gives people an HTTPS address that connects to that computer.** Leave the computer on, awake, connected to the Internet, and running Docker Desktop. Turning it off takes the application offline. GitHub stores the code; it does not run this application.

This is the free way to publish the existing Docker application through Cloudflare. Hosting the containers themselves on Cloudflare requires its Workers Paid plan, currently starting at $5/month plus applicable usage. A deployment with no computer running at your end is therefore not a free Cloudflare container deployment. [Cloudflare Containers pricing](https://developers.cloudflare.com/containers/platform/pricing/).

| Option | Cloudflare charge | Address | Appropriate use |
| --- | --- | --- | --- |
| **A. Quick Tunnel** | $0; no Cloudflare account or domain required | Random `https://...trycloudflare.com` address; changes when the tunnel restarts | Trials, demonstrations, learning the app |
| **B. Named Tunnel** | Free Tunnel and Free website plan | A stable address such as `https://intrac.yourdomain.com` | Ongoing use with a domain you own |

Option B requires a registered domain. Buying and renewing a domain costs money; Cloudflare does not supply a free permanent domain in this workflow. If you already own one, you can use an unused subdomain without buying another. Both options use your computer, electricity, Internet connection, and disk space. Docker Desktop is only free for eligible uses; government entities and some organizations require a subscription, as explained in the [setup guide](SETUP.md).

Cloudflare calls Quick Tunnels testing/development tools, provides no uptime guarantee, limits them to 200 simultaneous in-flight requests, and does not support Server-Sent Events. InTrac does not use Server-Sent Events. Do not present Option A as dependable permanent hosting. [Quick Tunnel documentation](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/).

## Before either option: finish the local installation

1. Complete **every step** in [Install on a new Windows PC or Mac](SETUP.md), including creating the administrator and a verifier.
2. Confirm you can sign in at `http://localhost` and create a test operation log. If you changed the local port during setup, use that address instead.
3. Keep Docker Desktop running.
4. Open the command window for your system. You will paste the commands below into this window, one block at a time, and press **Enter/Return**. Do not include the surrounding triple backticks if copying from a text file.

**Windows:** open **Windows PowerShell** from Start. Administrator mode is usually unnecessary after installation. Run:

```powershell
Set-Location "$env:USERPROFILE\InTrac"
docker compose ps
```

**Mac:** press **Command + Space**, open **Terminal**, and run:

```bash
cd "$HOME/InTrac"
docker compose ps
```

If `docker` is not recognized, close and reopen the command window after finishing Docker setup. On Mac, you can also run this line in the same Terminal window:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

On Windows, for the standard installation, run:

```powershell
$env:Path = "$env:ProgramFiles\Docker\Docker\resources\bin;" + $env:Path
```

You should see both **api** and **web** with a running/healthy status. If not, run `docker compose up -d --wait` and check the error. Do not proceed to Cloudflare until local sign-in works.

## Option A: a free HTTPS link with no account or domain

### A1. Start the tunnel

1. In your command window, still in the InTrac folder, paste this command. It is identical on Windows and Mac:

   ```text
   docker compose -f compose.yaml -f compose.cloudflare-quick.yaml up -d --wait
   ```

2. Wait for the image download and for the **tunnel** container to start. Docker downloads Cloudflare's connector itself; you do not need to install `cloudflared` on your computer.
3. Display the connector's messages:

   ```text
   docker compose -f compose.yaml -f compose.cloudflare-quick.yaml logs --tail=100 tunnel
   ```

4. Look for the box containing an address ending in **`.trycloudflare.com`**. For example, it might look like `https://four-random-words.trycloudflare.com`. Your words will be different. Copy the whole `https://...` address, without the box's vertical bars or spaces.
5. If the box has not appeared, wait 15–30 seconds and run the logs command again. If there is a connection error, see troubleshooting below.

The printed address is the one you use. `http://web:8081`, shown in configuration files, is an internal Docker address, not a link to send to users.

### A2. Test the public link

1. Paste your actual `https://...trycloudflare.com` address into a new browser tab. Give a new link a short time to become available.
2. Confirm that the **InTrac sign-in** page appears without a certificate warning.
3. Sign in using your verifier account. Your local sign-in session does not carry over to the new address.
4. On a phone, turn **Wi-Fi off** temporarily so it uses mobile data. Enter the exact public address. This checks access from outside your home/office network.
5. Sign in, select **Create log**, and allow browser location if requested. If the phone denies it, enable location for this browser/site in its settings, or enter the location manually.
6. Create a test log, add a test weapon/photo, save, reopen it, and download a report. You should see the same saved data from the host computer when signed in as the same verifier.
7. Share the HTTPS link with intended users and give each person their own verifier account. Anyone with the URL can reach the sign-in page; InTrac's existing login protects the records.

**HTTPS is already enabled.** Do not install a self-signed certificate, change router port forwarding, or use the local certificate guide for this option. The public browser connection uses Cloudflare's certificate; the connector has an encrypted connection to Cloudflare. Only the final connection between containers on your computer is HTTP.

### A3. Find the link later or stop sharing

To find the current link, rerun:

```text
docker compose -f compose.yaml -f compose.cloudflare-quick.yaml logs --tail=100 tunnel
```

If the tunnel has been running long enough that the startup box has scrolled out of the last 100 lines, omit `--tail=100` to see its full retained log.

To stop Internet access while keeping local InTrac running:

```text
docker compose -f compose.yaml -f compose.cloudflare-quick.yaml stop tunnel
```

To start sharing again:

```text
docker compose -f compose.yaml -f compose.cloudflare-quick.yaml up -d --wait
```

Read the logs again and share the **new** link. It can change whenever the connector restarts, including after a computer restart, Docker restart, or update. The database does not reset when the URL changes.

If you want to keep the same address, follow Option B. Otherwise skip to **Keep the application available**.

## Option B: a permanent address on a domain you own

### B1. Create a Cloudflare account

1. Open [the Cloudflare dashboard](https://dash.cloudflare.com/sign-up).
2. Select **Sign up** if you do not already have an account.
3. Enter your email and choose a password, or use an offered sign-in method.
4. Complete the email verification message if Cloudflare asks for it.
5. Sign in to the dashboard. This guide uses the **Free** website plan and a standard Tunnel. You do not need Workers Paid, paid Containers, paid Argo routing, or a paid load balancer.

If you do not own a domain, stop here and use Option A for a $0 trial. To continue with a permanent address, you must acquire a domain or ask the person who manages your organization's domain to add this application.

### B2. Add the domain to Cloudflare

If the domain already appears as **Active** in your Cloudflare account, skip to B3.

1. In Cloudflare, select **Add a domain** (sometimes under **Onboard a domain**).
2. Enter the domain you own, such as `yourdomain.com`. Enter only the domain, without `https://` and without `intrac.`.
3. Choose the option to scan/import existing DNS records and continue.
4. When asked for a plan, select **Free**, then continue. Do not select a paid plan for these steps.
5. Review the imported DNS records against those at your current domain provider. Preserve existing website and email records, including MX and TXT records. If another person manages this domain, have them review this step before changing its nameservers.
6. Cloudflare will display **two nameserver addresses** assigned to your domain. Copy them somewhere temporarily.
7. Open the website where you registered the domain in another tab and sign in. This could be a registrar such as Namecheap, GoDaddy, or another provider.
8. Open the domain's management page and find **Nameservers**. This is different from adding an individual A or CNAME record.
9. If DNSSEC is currently enabled at the registrar, follow its instructions to disable it before changing nameservers. You can re-enable it with Cloudflare's values after the move completes.
10. Choose **Custom nameservers**, replace the old nameservers with the **two exact addresses Cloudflare gave you**, and save. The addresses are different for different accounts; do not copy examples from someone else's guide.
11. Return to Cloudflare and complete its nameserver confirmation step.
12. Wait until the domain shows **Active**. This can take minutes or longer; follow the pending-status guidance shown by Cloudflare. Do not create random DNS records to try to force activation.

These steps move the domain's DNS management to Cloudflare; they do not transfer its registration or stop renewal charges. Cloudflare provides [domain onboarding instructions](https://developers.cloudflare.com/fundamentals/manage-domains/add-site/) and [nameserver/DNSSEC instructions](https://developers.cloudflare.com/dns/zone-setups/full-setup/setup/) with links for individual registrars.

### B3. Create the tunnel and copy its token

1. In the Cloudflare account dashboard, go to **Networking → Tunnels**.
2. Select **Create Tunnel**.
3. Name it **InTrac** and select **Create Tunnel**. If asked for connector type, choose **Cloudflared**.
4. In **Setup Environment**, select **Docker**. If Docker is shown under another operating-system tab, select that installation method.
5. Cloudflare displays a command containing `--token` followed by a long string usually starting with `eyJ`.
6. Copy **only that long token**. Do not copy `docker run`, `--token`, angle brackets, quotation marks, or other parts of the command. You will place the token in InTrac's configuration in the next section. Do not run Cloudflare's example `docker run` command; InTrac's Compose file starts the connector on the correct Docker network.
7. Leave this dashboard tab open while you start the connector.

If your dashboard still has the older navigation, look in **Zero Trust → Networks → Connectors** (or **Networks → Tunnels**) for the Cloudflared tunnel screen. Use the dashboard's search for **Tunnels** if needed. The current official flow is [Create a tunnel in the dashboard](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/).

The token is a credential that allows a connector to run your tunnel. Keep it private. If you lose the setup screen, select the tunnel and **Add a replica** to see a new installation command containing its token. [Cloudflare's token instructions](https://developers.cloudflare.com/tunnel/reference/tunnel-tokens/).

### B4. Save the token in InTrac

Setup has already created a file named **`.env`** in the InTrac folder. It may be hidden. Open it using the command for your computer.

**Windows**, in the same PowerShell window:

```powershell
Set-Location "$env:USERPROFILE\InTrac"
notepad .env
```

**Mac**, in Terminal:

```bash
cd "$HOME/InTrac"
open -e .env
```

1. Find the line `CLOUDFLARE_TUNNEL_TOKEN=` near the bottom of the file.
2. Paste the actual token immediately after `=`. Keep it all on **one line**, with no added quotes or spaces. The result will resemble `CLOUDFLARE_TUNNEL_TOKEN=eyJ...`, but use the complete token; `...` is not a valid token.
3. Keep these other values at their defaults for Cloudflare:

   ```dotenv
   INTRAC_BIND_ADDRESS=127.0.0.1
   INTRAC_SITE_ADDRESS=:80
   INTRAC_TLS_DIRECTIVE=
   INTRAC_COOKIE_SECURE=false
   ```

   Keep any alternate local HTTP/HTTPS port numbers you set to avoid a port conflict. The tunnel does not use those host ports. HTTPS requests already get Secure cookies automatically; the `false` setting permits local HTTP sign-in too.

4. Save with **Ctrl + S** on Windows or **Command + S** on Mac. Because you opened the existing file, its name should remain `.env`, not `.env.txt`. On Mac keep it plain text; do not convert it to a rich-text document.
5. Close the editor. Do not email this file or commit it to GitHub. It is excluded by `.gitignore` and the Docker build excludes it.

### B5. Start the permanent tunnel

If you used Option A, stop its connector first:

```text
docker compose -f compose.yaml -f compose.cloudflare-quick.yaml stop tunnel
```

Start the named connector:

```text
docker compose -f compose.yaml -f compose.cloudflare.yaml up -d --wait
```

Display its recent messages:

```text
docker compose -f compose.yaml -f compose.cloudflare.yaml logs --tail=50 tunnel
```

1. Look for a successful connection message such as **Registered tunnel connection**. It can take a short time.
2. Return to the Cloudflare tab. The connector should now be connected/healthy.
3. Select **Continue** when offered.
4. If it stays inactive, follow troubleshooting below. Do not replace the token with your Cloudflare account password; those are different credentials.

The two configurations use the same service name, **tunnel**, so switching replaces the connector instead of leaving two public entry points running.

### B6. Connect your web address to InTrac

1. In **Networking → Tunnels**, select **InTrac**.
2. Open **Routes**, select **Add route**, then **Published application**. In an older dashboard this may be **Public Hostnames → Add a public hostname**.
3. Enter these values:

   | Field | Enter |
   | --- | --- |
   | Subdomain | `intrac` |
   | Domain | Select your actual domain, such as `yourdomain.com` |
   | Path | Leave empty |
   | Service type | **HTTP** |
   | Service URL/address | **`web:8081`** if type is separate; **`http://web:8081`** if the field expects a full URL |

4. Leave extra origin settings at their defaults. In particular, leave **HTTP Host Header** blank; InTrac needs the visitor's original hostname for its sign-in protection.
5. Select **Add route** or **Save**.
6. Cloudflare creates the DNS route for the hostname. You should not need a public IP address, router port forwarding, or an A record pointing to your home computer.

Use **`web:8081` exactly**. Here `web` is the application container's name. `localhost` inside the tunnel container would mean the tunnel container itself and cause a **502** error. The private port 8081 preserves the browser's public HTTPS scheme so that login and Secure cookies work correctly. This is specific to the supplied InTrac package. The general dashboard process is documented in [Publish an application](https://developers.cloudflare.com/tunnel/get-started/#publish-an-application).

Use a single subdomain such as `intrac.yourdomain.com`. Cloudflare's default certificate coverage does not cover arbitrary extra levels such as `intrac.team.yourdomain.com`.

### B7. Confirm HTTPS and sign-in

1. Open **`https://intrac.yourdomain.com`**, replacing `yourdomain.com` with your domain.
2. If the domain was just activated, allow time for DNS and Cloudflare's certificate issuance. Check the domain's **SSL/TLS → Edge Certificates** page if its certificate is still pending.
3. Confirm that the browser loads InTrac without a certificate warning. The address should begin with **https://**.
4. Sign in with your verifier account. Create and reopen a test log and download a report.
5. On a phone, turn Wi-Fi off and repeat the test using mobile data. Permit location access when creating a log.
6. Share your permanent HTTPS address with your users and give each person a separate InTrac account.

No manual certificate install is needed on users' phones or computers. Do not enable local Caddy HTTPS for this Cloudflare path. The application container stays HTTP inside Docker; Cloudflare manages public HTTPS and the connector secures the Internet leg. The tunnel listener redirects public HTTP requests to HTTPS. Keep Cloudflare's normal caching behavior; do not create a **Cache Everything** rule for this application or override the API's `Cache-Control: no-store` responses.

## Keep the application available

1. Plug the host computer into power.
2. In **Docker Desktop → Settings → General**, enable **Start Docker Desktop when you sign in** (wording may differ slightly), then apply/save. Containers have a restart policy, so they resume when Docker's engine starts unless you explicitly stopped them.
3. On Windows, open **Settings → System → Power & battery → Screen, sleep & hibernate timeouts** (or **Power & sleep**). While plugged in, set the computer's sleep timeout to **Never**. The display can turn off.
4. On Mac, check **System Settings → Battery → Options** for **Prevent automatic sleeping on power adapter when the display is off**. Desktop Macs may put this in **Energy**. Keep a laptop's lid open unless you have configured a supported external-display setup.
5. After a computer restart, sign in to the operating system and let Docker Desktop start. This desktop installation is not an unattended server that starts before anyone signs in.
6. Reopen the public address and verify it works. For Option A, retrieve the new address from the tunnel log. Option B keeps its hostname.
7. Back up the database regularly using [the backup instructions](OPERATIONS.md#back-up-your-data). Photos and reports' source records live on the host computer, not in GitHub or Cloudflare. Tunnel certificates are not a database backup.

For ongoing use, follow [start/stop/update/recovery instructions](OPERATIONS.md). Turning off your monitor is fine; sleeping, shutting down, quitting Docker, or losing Internet takes the site offline.

## Troubleshooting

Run commands from the InTrac folder. The examples below use Option B; for Option A replace `compose.cloudflare.yaml` with `compose.cloudflare-quick.yaml`.

**Show all services and recent errors:**

```text
docker compose -f compose.yaml -f compose.cloudflare.yaml ps
docker compose -f compose.yaml -f compose.cloudflare.yaml logs --tail=60 api web tunnel
```

| Symptom | Steps to take |
| --- | --- |
| `CLOUDFLARE_TUNNEL_TOKEN` is required | Open `.env`, put the complete actual token after `=`, save, and rerun B5. Confirm the file is not `.env.txt`. |
| Cloudflare says tunnel is inactive or shows error 1033 | Wake the host, open Docker Desktop, run the `up -d --wait` command for your option, and read tunnel logs. Confirm the token belongs to this tunnel. |
| Cloudflare shows 502 Bad Gateway | In the published route set the service to **HTTP `web:8081`**, leave Host Header empty, then run `docker compose ps`. Both api and web must be healthy. |
| Sign-in says cross-origin requests are not allowed | Correct the route to `http://web:8081`, clear any HTTP Host Header override, use the HTTPS public address, then sign in again. Do not disable InTrac's origin protection. |
| The page appears but sign-in does not persist | Use the HTTPS URL. Check browser cookie settings and route port 8081. Localhost and the public hostname have separate sessions. |
| Domain cannot be selected | Wait for it to be Active in this Cloudflare account; confirm it is the same account used for the tunnel. |
| DNS record already exists for `intrac` | In the domain's DNS page, inspect the existing record. Use a different unused subdomain if it belongs to another service. Only replace a record you know is no longer needed. |
| Certificate warning or SSL error | Check the exact hostname and Edge Certificate status. Use one subdomain level. Do not ask users to bypass the browser warning. |
| Quick Tunnel URL stopped working | Fetch the latest link from its logs; restarts change it. If the host is asleep, wake it and start Docker. |
| Tunnel repeatedly fails to connect | Verify Internet access. The connector needs outbound port **7844 TCP/UDP**; a restrictive network may block it. Ask that network's administrator to allow Cloudflare Tunnel. No inbound router ports are needed. |
| Photo fails to upload | Use JPEG, PNG, or WebP up to 8 MB and 20 megapixels; check free Docker disk space. Read the application's validation message. |
| GPS/location fails | Use HTTPS, permit location in the browser and device settings, and retry. Manual location entry remains available. |

Cloudflare documents [tunnel connection troubleshooting](https://developers.cloudflare.com/tunnel/troubleshooting/). Share error messages with the person helping you, but remove tokens, cookies, passwords, and real operation data from anything you send.

## Completion check

You are finished when the public HTTPS address opens from a phone on mobile data, you can sign in as a verifier, save and reopen a log with a photo, and download a report. Keep the host running and make your first backup. For the permanent option, restart Docker once and confirm the same hostname works afterward; for the Quick Tunnel option, expect a new URL.
