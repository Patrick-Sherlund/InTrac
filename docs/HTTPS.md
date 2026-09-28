# HTTPS without Cloudflare

If you are following the [Cloudflare guide](CLOUDFLARE.md), HTTPS is already handled there. This page is for a private Wi-Fi/LAN installation or a server reached directly through a domain. Complete [setup](SETUP.md) first.

## Private Wi-Fi/LAN HTTPS

1. Keep the hosting computer on the network. Find its local IPv4 address: run `ipconfig` in Windows PowerShell and read the active Wi-Fi/Ethernet adapter's **IPv4 Address**. On Mac, open **System Settings → Network → your active connection → Details → TCP/IP**. Suppose the address is `192.168.1.50`; replace that example below with your actual address.
2. Reserve that address for the computer in your router's DHCP settings if possible. Otherwise, when the IP changes you must update this configuration and users' bookmarks.
3. Open the command window and change into the InTrac folder, as in the setup guide.
4. Open `.env`: `notepad .env` on Windows or `open -e .env` on Mac.
5. Change these lines, save, and close the editor:

   ```dotenv
   INTRAC_BIND_ADDRESS=0.0.0.0
   INTRAC_HTTP_PORT=80
   INTRAC_HTTPS_PORT=443
   INTRAC_SITE_ADDRESS=https://192.168.1.50
   INTRAC_TLS_DIRECTIVE=tls internal
   INTRAC_COOKIE_SECURE=true
   ```

6. Apply the changes:

   ```text
   docker compose up -d --wait
   ```

7. Permit inbound TCP 80 and 443 through the host's firewall for your **private network**. On Windows, in Administrator PowerShell you can run:

   ```powershell
   New-NetFirewallRule -DisplayName "InTrac private network HTTPS" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80,443 -Profile Private
   ```

   The Wi-Fi/Ethernet connection must have the **Private** network profile. On Mac, use **System Settings → Network → Firewall → Options** and allow incoming connections for Docker when requested. Do not create Internet router forwarding rules for this private-network option.

8. Export **only the public CA certificate**. These commands work in PowerShell and Terminal. If `.local` already exists, skip `mkdir`:

   ```text
   mkdir .local
   docker compose cp web:/data/caddy/pki/authorities/local/root.crt .local/intrac-root.crt
   ```

9. Install that certificate on each device that will use the app, following the section below. Caddy runs in Docker, so its attempt to install trust inside the container does not install trust on your computer or phone. [Caddy local HTTPS documentation](https://caddyserver.com/docs/automatic-https#local-https).
10. Open **`https://192.168.1.50`** using your actual configured address. It must load without a certificate warning. Sign in again, create a log, and allow browser location. `localhost` is not covered unless you explicitly include it as another site address.

Use the public certificate only on devices you control or whose owners approve the trust installation. It allows the device to trust certificates issued by this local Caddy authority. Keep the Caddy data volume and its private keys private; never export or share the whole volume as a certificate download. Remove the CA from a device's trust store when it no longer uses this installation.

### Trust on Windows

1. Open PowerShell in the InTrac folder as your regular user.
2. Run:

   ```powershell
   Import-Certificate -FilePath .\.local\intrac-root.crt -CertStoreLocation Cert:\CurrentUser\Root
   ```

3. Accept the certificate trust prompt if shown.
4. Close and reopen your browser, then load your HTTPS address. Chrome/Edge use the Windows certificate store. If another browser manages its own authorities, import the same certificate there too.

### Trust on Mac

1. Open Terminal in the InTrac folder.
2. Run:

   ```bash
   sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain .local/intrac-root.crt
   ```

3. Enter your Mac password when asked.
4. Restart the browser and open your configured HTTPS address. If a browser uses a separate certificate store, import the public certificate into its authorities as well.

### Trust on iPhone/iPad

1. Transfer `.local/intrac-root.crt` from your host to the phone using AirDrop or an email attachment you send to yourself. Only transfer this public certificate.
2. Open the received certificate attachment and allow the profile download when prompted. If you receive it as a saved file, opening that file must produce the **Profile Downloaded** step before continuing.
3. Open **Settings → Profile Downloaded**, or **Settings → General → VPN & Device Management**.
4. Select the certificate profile for **Caddy Local Authority**, select **Install**, enter the device passcode if requested, and finish installation.
5. Open **Settings → General → About → Certificate Trust Settings**.
6. Enable full trust for **Caddy Local Authority** and confirm.
7. Open Safari and visit the exact configured HTTPS address. Permit location when creating a log. The phone must be on the same LAN/Wi-Fi network.

Apple documents [profile installation](https://support.apple.com/en-us/102400) and the separate [full-trust step](https://support.apple.com/en-us/102390). Installing a profile alone does not turn on trust for a manually installed CA. A managed device may restrict user-installed certificates; use the Cloudflare HTTPS option or ask its administrator in that case.

### Trust on Android

1. Transfer the public `intrac-root.crt` file to the phone.
2. Open device **Settings** and search for **Install a certificate** or **CA certificate**. Typical paths are **Security & privacy → More security settings → Encryption & credentials → Install a certificate → CA certificate**; manufacturers vary.
3. Choose the CA-certificate option, confirm the system's trust notice, unlock the device if asked, and select `intrac-root.crt`.
4. Restart Chrome and open your exact HTTPS address on the same network. Allow location when asked. If the browser or device does not permit this trust path, use Cloudflare's publicly trusted HTTPS address instead.

### Renewal and changed addresses

Caddy renews its server certificates automatically while it runs. Its authority and certificates persist in the `intrac_caddy_data` Docker volume. If the host IP changes, update `INTRAC_SITE_ADDRESS`, run `docker compose up -d --wait`, and use the new URL. Keeping the same Caddy volume preserves the authority already trusted by devices. Deleting that volume generates a new authority, requiring a new certificate import on every device.

## A public domain with direct HTTPS

Cloudflare Tunnel is easier on home/office networks because it needs no inbound ports. Use this direct option only if you have a domain and an Internet-reachable host.

1. Point the domain's DNS A record to the host/router's public IPv4 address. Only add an AAAA record if IPv6 reaches that host correctly.
2. Allow inbound TCP **80 and 443** in the host firewall and forward those ports through the router to the host if necessary. Carrier-grade NAT may make forwarding impossible; use a tunnel in that case.
3. In `.env`, set:

   ```dotenv
   INTRAC_BIND_ADDRESS=0.0.0.0
   INTRAC_HTTP_PORT=80
   INTRAC_HTTPS_PORT=443
   INTRAC_SITE_ADDRESS=https://intrac.yourdomain.com
   INTRAC_TLS_DIRECTIVE=
   INTRAC_COOKIE_SECURE=true
   ```

4. Replace the example domain with yours and run `docker compose up -d --wait`.
5. Run `docker compose logs --tail=100 web` and wait for certificate issuance. Caddy obtains and renews a publicly trusted certificate automatically when DNS and challenge reachability are correct. [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).
6. Open your domain over HTTPS from another network, verify there is no certificate warning, and test sign-in. No CA installation is required for publicly trusted certificates.

Use standard public ports for this direct setup so redirects and certificate challenges work. If you change to Cloudflare Tunnel later, restore the `.env` defaults shown in its guide and use the internal `web:8081` service URL.
