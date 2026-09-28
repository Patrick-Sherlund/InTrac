# Start, stop, back up, and update InTrac

Open PowerShell on Windows or Terminal on Mac. Open Docker Desktop and wait for its engine to start.

Windows:

```powershell
Set-Location "$env:USERPROFILE\InTrac"
```

Mac:

```bash
cd "$HOME/InTrac"
```

Run the following commands from this folder. They work on both systems unless indicated otherwise.

## Start and stop

Use the row matching your setup. Stopping preserves your records.

| Setup | Start | Stop |
| --- | --- | --- |
| Local only / direct HTTPS | `docker compose up -d --wait` | `docker compose stop` |
| Cloudflare Quick Tunnel | `docker compose -f compose.yaml -f compose.cloudflare-quick.yaml up -d --wait` | `docker compose -f compose.yaml -f compose.cloudflare-quick.yaml stop` |
| Cloudflare named tunnel | `docker compose -f compose.yaml -f compose.cloudflare.yaml up -d --wait` | `docker compose -f compose.yaml -f compose.cloudflare.yaml stop` |

`docker compose ps` shows the application containers. Add the same `-f` options to include the tunnel. `docker compose logs --tail=80 api web` shows application errors. The database is in Docker's `intrac_intrac_data` volume, not in the extracted source folder.

Do not run `docker compose down -v`, delete these volumes in Docker Desktop, or factory-reset Docker unless you intentionally want to erase this installation and have a verified backup. Docker's ordinary container recreation and application updates preserve the volumes.

The Compose project is deliberately named `intrac` so a differently named ZIP folder does not silently create an empty second database. Run one InTrac deployment per computer with the beginner instructions. Advanced deployments can set `docker compose -p <different-name>` for separate installations and must also use different host ports.

## Back up your data

All users, sessions, operation logs, weapons, and photos are stored in one SQLite database. This command uses SQLite's backup API, which makes a consistent copy while the app is running.

1. Open Docker Desktop and start InTrac if necessary.
2. In File Explorer/Finder, create a folder called **backups** inside the InTrac folder if it does not already exist.
3. If `backups/intrac-backup.db` already exists from an earlier backup, rename it first to include its date, such as `intrac-backup-2026-09-28.db`.
4. Run:

   ```text
   docker compose exec -T api python -c "import sqlite3; src=sqlite3.connect('/data/intrac.db'); dst=sqlite3.connect('/tmp/intrac-backup.db'); src.backup(dst); dst.close(); src.close()"
   docker compose exec -T api python -c "import sqlite3; db=sqlite3.connect('/tmp/intrac-backup.db'); result=db.execute('PRAGMA integrity_check').fetchone()[0]; print(result); assert result == 'ok'"
   docker compose cp api:/tmp/intrac-backup.db ./backups/intrac-backup.db
   ```

5. The check must print **ok**. Confirm the copied file exists in your backups folder and is not zero bytes.
6. Copy that file to a private, secure backup location separate from the host computer. The file contains your application data, password hashes, and photos. It is not an encrypted backup.
7. Keep `.env` in a separate private backup if you use a tunnel token or customized hosting settings. It is not included in the database. Do not put it in a public repository.

Do this before updating and regularly while using the app. Cloudflare and GitHub do not back up this database. The generated PDF report is useful for sharing records, but cannot restore users or the application database.

## Restore a backup

**Restoring replaces the current database with the saved version.** Records created after the backup will be lost. First make a backup of the current database if you may need to return to it.

1. Put the backup you want to restore at `InTrac/backups/intrac-backup.db`.
2. Stop **all** services using the correct **Stop** command in the table above. Do not restore while the application is accepting requests.
3. Run this single command. It verifies the source database before copying it into the application volume:

   ```text
   docker compose run --rm --no-deps -v "./backups:/backup:ro" api python -c "import sqlite3; src=sqlite3.connect('file:/backup/intrac-backup.db?mode=ro', uri=True); assert src.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Invalid backup'; dst=sqlite3.connect('/data/intrac.db'); src.backup(dst); dst.close(); src.close(); print('Database restored')"
   ```

4. Wait for **Database restored**. If it reports an error, resolve that error before starting the app.
5. Start the application with the correct **Start** command above.
6. Sign in with credentials that existed at the time of the backup. Confirm your logs and photos are present.

To move to a different computer, install InTrac there first, copy the backup to its backups folder, and follow these restore steps. Restore your private `.env` settings if appropriate. For a named tunnel, stop the old computer's connector before starting the new one; running both against separate databases would split traffic between inconsistent copies. Local HTTPS on a new Caddy volume requires trusting its newly generated authority again.

## Update from GitHub without installing Git

1. Make a database backup using the steps above.
2. Stop the stack using the matching **Stop** command.
3. Download a fresh ZIP from [the repository](https://github.com/Patrick-Sherlund/InTrac) using **Code → Download ZIP**, and extract it.
4. Copy the contents of the new extracted project folder into your existing **InTrac** folder. Replace the source files when asked. Keep your existing **`.env`**, **backups**, and **`.local`** folders. The download contains `.env.example`, which is different from your live `.env`.
5. Rebuild and start with the command matching your setup:

Local/direct HTTPS:

```text
docker compose build --pull
docker compose up -d --wait
```

Cloudflare Quick Tunnel:

```text
docker compose build --pull
docker compose -f compose.yaml -f compose.cloudflare-quick.yaml pull tunnel
docker compose -f compose.yaml -f compose.cloudflare-quick.yaml up -d --wait
```

Cloudflare named tunnel:

```text
docker compose build --pull
docker compose -f compose.yaml -f compose.cloudflare.yaml pull tunnel
docker compose -f compose.yaml -f compose.cloudflare.yaml up -d --wait
```

6. Wait for healthy containers, reload the browser, sign in, and open an existing log/photo. Quick Tunnel users must retrieve and share the new link from its logs.

Installed from a Git clone instead of ZIP? Back up first, use `git pull --ff-only`, then the same rebuild/start commands. Never commit `.env`, database files, or generated certificates.

## Recover administrator access

If you forget the first administrator password, create a **different administrator account** from the host computer. This preserves existing users and records:

```text
docker compose exec api python -m app.create_admin --first-name System --last-name Recovery --username recovery-admin
```

Choose and confirm a new 12–128 character password, then sign in as `recovery-admin`. If that username already exists, choose another unused name. The current app has user creation but no password-reset screen; rerunning setup does not reset passwords.

## Existing development data

The development database at `backend/data/intrac.db` is deliberately not shipped or copied automatically. To migrate it, stop the development backend, make a separate copy of that database at `backups/intrac-backup.db`, and follow the restore procedure. Keep the original file until you have verified the migrated logs and photos.
