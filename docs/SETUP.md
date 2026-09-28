# InTrac: install on a new Windows PC or Mac

This guide assumes you have never used Docker or a command line. Finish this page first, then open the [Cloudflare guide](CLOUDFLARE.md) to make the app accessible over the Internet with HTTPS.

Docker is the program that runs the application's packaged software. The installer adds Docker Desktop; Docker downloads Python, Node.js, the web server, and all application dependencies into containers. You do not need to install those separately, or install Git, Homebrew, or an editor.

## 1. What you need

- A computer you can install programs on, an Internet connection, and its administrator password.
- A supported Windows 10/11 computer with WSL 2 and hardware virtualization support, or an Intel/Apple silicon Mac running one of Docker's supported macOS releases. Allow several GB of free disk space for Docker and images, plus space for your photos.
- Plan for a Windows restart and about 15–30 minutes for downloads; connection speed varies.
- Keep the host computer awake and connected whenever other people need the application.

The scripts install the software prerequisites. They cannot upgrade an unsupported operating system, turn on a BIOS/UEFI setting, or bypass your organization's device restrictions. Docker's current [Windows requirements](https://docs.docker.com/desktop/setup/install/windows-install/) and [Mac requirements](https://docs.docker.com/desktop/setup/install/mac-install/) are the source of truth.

Docker Desktop is free for eligible personal, educational, non-commercial open-source, and small-business use. **Government entities and some commercial organizations require a paid Docker Desktop subscription.** Check [Docker's subscription terms](https://docs.docker.com/subscription/desktop-license/) before describing this installation as free for your organization. The scripts leave agreement acceptance to you in Docker's screens. Linux Docker Engine is another deployment option, but these desktop installers target Windows and Mac.

## 2. Download InTrac

1. Open a browser on the computer that will run the application.
2. Visit [Patrick-Sherlund/InTrac on GitHub](https://github.com/Patrick-Sherlund/InTrac).
3. If you see a sign-in screen, sign in to the GitHub account that has access. If you see **404**, ask the repository owner to give that account access; this may be a private repository.
4. On the repository's **Code** page, select the green **Code** button.
5. Select **Download ZIP**.
6. Wait for `InTrac-main.zip` to finish downloading. Do not run anything inside the ZIP viewer.
7. Follow the section for your operating system below.

## 3A. Windows: extract and install

1. Open **File Explorer → Downloads**.
2. Right-click `InTrac-main.zip`, select **Extract All**, and select **Extract**.
3. Open the extracted folder. Find the folder containing `README.md`, `compose.yaml`, and `setup-windows.ps1`. Sometimes there is one extra `InTrac-main` folder inside the extracted folder.
4. Copy that whole folder. In File Explorer's address bar type `%USERPROFILE%` and press **Enter**. This opens your user folder, such as `C:\Users\Alex`.
5. Paste the folder there and rename it **InTrac**. You should now have `C:\Users\Alex\InTrac\setup-windows.ps1`. This guide uses that location; avoid a OneDrive-synchronized folder.
6. Press the Windows key, type **Windows PowerShell**, right-click **Windows PowerShell**, and select **Run as administrator**. Select **Yes** in the permission prompt. Use the standard 64-bit version, not **Windows PowerShell (x86)** or the ISE editor.
7. Copy this line, paste it into the PowerShell window, and press **Enter**:

   ```powershell
   Set-Location "$env:USERPROFILE\InTrac"
   ```

8. Copy, paste, and run this line:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup-windows.ps1
   ```

   This permits this one PowerShell process to run the setup script; it does not permanently change your execution policy. If an organization blocks scripts, its administrator must resolve that policy.

9. The script enables Windows' WSL/container prerequisites. If it says **Windows needs a restart**, save your work, choose **Start → Power → Restart**, and sign in again. Repeat steps 6–8. Do not wait in the old window for installation to continue automatically.
10. Allow the WSL and Docker downloads to complete. Follow the Docker installer prompts if they appear. If Windows requests another restart, restart and run the same command again.
11. When **Docker Desktop** opens, read its terms and accept them if you agree. Use its recommended settings. You can skip the Docker account sign-in screen. An account is not required to run InTrac.
12. Keep PowerShell open. It waits up to ten minutes for Docker. If that time expires while you are finishing the screens, finish them and rerun step 8.
13. The script downloads the application dependencies and builds two containers. Wait until it asks for **Administrator password**.
14. Enter a password of **12–128 characters**. Save it in your password manager. Nothing appears as you type; this is normal. Press **Enter**, type the identical password again, and press **Enter**.
15. Wait for **InTrac is ready**. If password validation failed, rerun step 8 and choose a valid password. Rerunning preserves your data and an existing administrator's password.
16. Continue to **First sign-in** below.

If Windows says virtualization is disabled, open **Task Manager → Performance → CPU** and check **Virtualization**. Enabling it requires your PC manufacturer's BIOS/UEFI instructions. After enabling it and restarting, rerun setup. Docker uses Linux containers; if its tray menu offers **Switch to Linux containers**, select that option.

If you elevated with a different administrator account, `$env:USERPROFILE` refers to that account. Use the actual path to the folder you extracted in step 7 and use the intended Windows account to run Docker Desktop after installation.

## 3B. Mac: extract and install

1. Open **Finder → Downloads**.
2. Double-click `InTrac-main.zip` to extract it.
3. Locate the extracted folder containing `README.md`, `compose.yaml`, and `setup-macos.sh`.
4. In Finder, choose **Go → Home**. Move the extracted folder into this Home folder and rename it **InTrac**. You should now have `/Users/your-name/InTrac/setup-macos.sh`.
5. Press **Command + Space**, type **Terminal**, and press **Return**.
6. Paste this command and press **Return**:

   ```bash
   cd "$HOME/InTrac"
   ```

7. Paste this command and press **Return**:

   ```bash
   bash setup-macos.sh
   ```

8. The script automatically selects the Intel or Apple silicon Docker download. Wait for the download to complete.
9. When asked for your Mac password, enter the password you use to log into the Mac and press **Return**. Nothing appears while you type. Do not put `sudo` before the setup command; it requests administrator access only for installation.
10. Docker Desktop opens. Review and accept its terms if you agree, choose the recommended settings, and allow its requested system configuration. You can skip Docker account sign-in.
11. Return to Terminal. The script waits for Docker and then builds the application. If its ten-minute wait expired, finish the Docker screens and rerun step 7.
12. At **Administrator password**, choose a new **12–128 character** password for InTrac, save it in your password manager, and press **Return**. Retype it at the confirmation prompt. Typing is hidden. This is an InTrac password, separate from your Mac password.
13. Wait for **InTrac is ready**. If the password was rejected, rerun step 7. Existing accounts and data are preserved.
14. Continue below.

If macOS blocks Docker, check **System Settings → Privacy & Security** and Docker's displayed error. Install current macOS updates if the installer says your OS is unsupported. Use the official Docker download; do not disable system-wide security settings.

## 4. First sign-in and first user

1. Keep Docker Desktop running.
2. Open your browser and enter **http://localhost** in the address bar. `localhost` means this computer; this address does not work from someone else's phone or computer.
3. Sign in with username **admin** and the InTrac password you just chose.
4. You should see the administrator's user-creation form.
5. Fill in a person's **First name**, **Last name**, **Username**, and **Password**. Use at least 12 characters for their password.
6. Choose role **Verifier**, then select **Create user**. Give the person their own credentials securely.
7. Select **Sign out**.
8. Sign in as the new verifier. You should now see the operation-log workspace. Administrators manage users; verifiers enter operation logs.
9. Create a sample log with a recognizable test operation name and a manually entered location. Add a sample weapon, open the log again, and confirm it saved. Use test data while learning; the app has no delete-record workflow.
10. To allow phones and other computers to use it, continue to the [Cloudflare guide](CLOUDFLARE.md). That guide also enables trusted HTTPS and browser location without manually installing certificates.

The default installation is reachable only from the host computer. Cloudflare Tunnel can publish it without changing that setting. For a private Wi-Fi-only installation, follow the separate [HTTPS guide](HTTPS.md).

## 5. If a setup step fails

Read the last error in the window, resolve it, and run the same setup command again. Never delete Docker volumes as an installation troubleshooting step; they hold the database.

| What you see | What to do |
| --- | --- |
| Cannot find `setup-...` or `compose.yaml` | Open the actual extracted folder containing those files; the ZIP may have an extra outer folder. |
| Docker engine not running | Open Docker Desktop, complete its welcome screens, wait until its engine runs, then rerun setup. |
| WSL error or restart required | Restart Windows, open Administrator PowerShell, and run setup again. If it persists, run `wsl --status` and read its error. |
| Port 80 or 443 is already allocated | Open `.env` as described in the Cloudflare guide. Change `INTRAC_HTTP_PORT=8080` and `INTRAC_HTTPS_PORT=8443`, save, and rerun setup. Open `http://localhost:8080`. Tunnel settings stay the same. |
| Cannot download an image or dependency | Confirm Internet access and that your network permits Docker Hub, Docker downloads, npm, and PyPI. Rerun setup. |
| Passwords do not match | Rerun setup and enter the same 12–128 character password twice. |
| Existing admin message | Setup finished previously. Use the password you originally chose; rerunning does not reset it. |

See [Operations](OPERATIONS.md) for recovery, logs, backups, and updates.
