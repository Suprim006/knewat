# FalkorDB hosting decision doc (Graph Hacks, submissions close 2026-10-18 23:59 IST)

Legend: **[inf]** = my inference, not stated by a source. **[unk]** = could not find a statement. Prices read on 2026-10-14.

## 0. Constraints that drive everything
- FalkorDB 6.0 is a Redis module (`GRAPH.*` commands); Docker tags `latest`/`6.0.0` are amd64 + arm64, and `falkordb/falkordb` bundles the Browser on :3000 ([v6.0.0 release](https://github.com/FalkorDB/FalkorDB/releases/tag/v6.0.0)). Module `.so` files exist for Linux x64/arm64 only (same page) -> Windows needs Linux (WSL2/Docker/remote).
- Data dir in the image is `/var/lib/falkordb/data`; persistence = mount a volume there ([persistence docs](https://docs.falkordb.com/operations/durability/persistence)); AOF can be enabled with `REDIS_ARGS="--appendonly yes"` ([ACL/persistence docs](http://docs.falkordb.com/operations/durability/acl-persistence)).
- This machine (read-only checks): `wsl --version` -> WSL 2.1.5.0, kernel 5.15.146.1-2; `wsl -l -o` lists installable Ubuntu, Debian, kali-linux, openSUSE etc. So WSL is present; only a working distro is missing. Docker Desktop's backend lives in the `docker-desktop` WSL distro, which currently is the default distro (`wsl --status`).

## A. Local dev on this Windows machine

> **UPDATE 2026-10-14 (after this doc was written):** Docker Desktop works again (engine 26.0.0), so A1–A3 are moot.
> Dev DB = container `falkordb-dev` (FalkorDB 6.0.2, `127.0.0.1:6379` + Browser `:3000`, volume `falkordb_dev_data`). Data survives a restart (verified).
> Windows→container round-trips cost ~10 ms through Docker Desktop's port forward (~0.3 ms inside the container), so run load tests inside the compose network.
> The WSL Ubuntu install was not done.

### A1. Ubuntu WSL2 distro + FalkorDB (recommended dev path)
Changes the machine (needs your OK; I did not run any of this).
```
wsl --install -d Ubuntu          # admin PowerShell; may need reboot  (https://learn.microsoft.com/en-us/windows/wsl/install)
wsl -s Ubuntu                    # make it default instead of docker-desktop (suggested in https://stackoverflow.com/questions/77548924/)
```
Inside Ubuntu, pick one:
1. **Docker Engine inside WSL** (independent of Docker Desktop): install Docker Engine for Ubuntu (e.g. `curl -fsSL https://get.docker.com | sh` — standard method, **[inf]** not read here), then the official quick-start:
   `docker run -p 6379:6379 -p 3000:3000 -it --rm -v ./data:/var/lib/falkordb/data falkordb/falkordb` ([FalkorDB README](https://github.com/FalkorDB/FalkorDB)). Server-only image: `falkordb/falkordb-server` ([Docker Hub](https://hub.docker.com/r/falkordb/falkordb-server)). Browser UI then at `localhost:3000`.
2. **FalkorDBLite** (embedded, no Docker): `python3 -m venv .venv && . .venv/bin/activate && pip install falkordblite`. Linux x64/macOS arm64 only, so Windows must use WSL2 ([TROUBLESHOOTING](https://github.com/FalkorDB/falkordblite-ts/blob/main/TROUBLESHOOTING.md) — that is the TS sibling package; the Python package's platform list is from the task brief, not re-verified). It disables TCP by default (same page), so it only suits in-process tests, not a shared dev DB.
- Reaching the DB from Windows tools via `localhost` generally works with WSL2 **[inf]**; verify with `redis-cli -p 6379 ping`.
- Effort: ~20-40 min. Risk: broken `NVIDIA-Workbench` distro keeps erroring in `wsl -l -v` (harmless unless it is made default); don't `--unregister` it without asking, it may hold user data.

### A2. Repair Docker Desktop (list only; not applied)
Observed error: `Failed to attach disk ...ext4.vhdx ... ERROR_PATH_NOT_FOUND`. Reported causes/fixes:
- The vhdx path was moved/deleted/cleaned while the distro stays registered. Reported fix: install a real distro with `wsl --install`, set it default with `wsl -s Ubuntu`; or `wsl --unregister <broken distro>` then reinstall ([Stack Overflow 77548924](https://stackoverflow.com/questions/77548924/can-run-wsl-command-anymore-failed-to-attach-disk-c-users-aib-appdata-local-d)).
- Docker's own `docker-desktop` distro disk missing at `...\AppData\Local\Docker\wsl\main\ext4.vhdx` — same error class reported in [Docker forum](https://forums.docker.com/t/docker-desktop-unexpected-wsl-error-win11/142298/5) and [SO 79444614](https://stackoverflow.com/questions/79444614/starting-dockerdesktop-on-windows-10-failed-with-wsl-error).
- Likely generic steps **[inf]**: quit Docker Desktop, `wsl --shutdown`, `wsl --unregister docker-desktop` (and `docker-desktop-data`), relaunch so it recreates them (loses local images/volumes), or Docker Desktop -> Troubleshoot -> Reset to factory defaults, or `wsl --update` (WSL 2.1.5.0 is not current **[inf]**).
- Effort: unpredictable (30 min – hours). Risk: destroys local Docker data; needs Docker license acceptance, etc. Prefer A1.

### A3. FalkorDB Cloud Free as dev DB (works today, no install)
Free: 100MB RAM, no TLS, no persistence, no backups, AWS/GCP; "Free instances that aren't utilized for 1 day will be stopped, and deleted after 7 days" ([free tier](https://docs.falkordb.com/cloud/tiers/free)). Sign-up needs no credit card (same page FAQ). Connect with the host/port/password shown in the console, e.g. `redis-cli -h <host> -p <port> -a <pw>` (**[inf]** from Redis protocol; no TLS, so credentials go over plaintext). Fine as a stop-gap dev DB if graph is reseeded from a script; not for anything you can't rebuild.

## B. Live hosting for judges (must survive >= 2-4 weeks after Oct 18)

| Option | Cost | RAM | Persistence | App runs | Effort | Main risk |
|---|---|---|---|---|---|---|
| B1 FalkorDB Cloud Free | $0 | 100MB | none | elsewhere (needs a 2nd host) | low | idle stop/delete; no TLS |
| B2 Railway (FalkorDB template) | Hobby $5/mo (incl. $5 usage) | up to 8GB/service on Hobby | volume | same Railway project | **lowest** | small recurring bill; must keep paying |
| B3 Oracle Always Free VM | $0 | A1: 2 OCPU/12GB total; E2.1 Micro | boot/block volume | same VM (docker compose) | high | idle reclamation, capacity, signup friction |
| B4 GCP e2-micro | $0 (within free limits) | 1GB | persistent disk 30GB | same VM | medium-high | tiny RAM, card required |
| B5 Fly.io | no free tier; ~$6-9/mo | 512MB-1GB | volume $0.15/GB | 2nd machine or same | medium | cost, not free |
| B6 Render free / Koyeb free | $0 | Koyeb 512MB | Render: none | n/a | – | not suitable |

**B1 FalkorDB Cloud Free.** Stopped after 1 day without "utilization", deleted after 7 ([source](https://docs.falkordb.com/cloud/tiers/free)); no snapshots/backups, deleted data "cannot be recovered". Whether a periodic keep-alive query counts as "utilized": **[unk]** — the docs don't define "utilized" and I found no statement either way (also searched the FAQ and docs search results). The docs offer extensions via sales. Even if a cron ping works, 100MB and no persistence means an outage = total data loss, and the app needs a separate host. Judges after Oct 18 for 2-4 weeks: too risky as sole store. Usable as a *fallback* if the app auto-reseeds an empty graph on start (design note, not code).

**B2 Railway.** FalkorDB publishes a verified template: single instance, server + Browser, persistent Railway volume, auto-generated vars `FALKORDB_PRIVATE_URL`, `FALKORDB_PUBLIC_URL`, `FALKORDB_PASSWORD`, image `falkordb/falkordb` ([template](https://railway.com/deploy/falkordb-1.md); [FalkorDB docs](https://docs.falkordb.com/operations/railway.md) call it suitable for "development, testing, demos"). Pricing ([plans](https://docs.railway.com/reference/pricing/plans)): Hobby $5/mo with $5 usage credit (not free — "you always pay the $5 subscription fee"); usage RAM $10/GB/mo, CPU $20/vCPU/mo, egress $0.05/GB, volume $0.15/GB/mo; Hobby limits 8GB RAM / 5GB volume. Trial: one-time $5 credit for up to 30 days, then a Free plan with $1/month credit, trial limited to 1GB RAM and (if unverified) restricted network ([free trial](https://docs.railway.com/reference/pricing/free-trial)). Rough bill **[inf]**: FalkorDB ~0.5GB (~$5) + FastAPI ~0.25GB (~$2.5) + volume pennies, so ~$5-10/mo for Hobby; a trial credit of $5 likely won't cover 4+ weeks of two services. Python app deploys in the same project and reaches DB via private URL (template's Python example uses `FalkorDB.from_url(os.environ["FALKORDB_PRIVATE_URL"])`). Auto-restart/persistence is platform-managed; the only risk is the account lapsing. Cluster template exists but unnecessary.

**B3 Oracle Cloud Always Free.** Up to two AMD Micro VMs, or Ampere A1 (first 1,500 OCPU-hours/9,000 GB-hours monthly = 2 OCPUs + 12GB) ([Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)). Caveats: "out of host capacity" errors can block creation (same page); idle instances may be reclaimed if over 7 days 95th-percentile CPU < 20% AND network < 20% (and memory < 20% for A1) ([resource ref](https://docs.oracle.com/iaas/Content/FreeTier/resourceref.htm)) — a quiet demo VM is exactly that profile. FalkorDB arm64 image exists ([v6.0.0](https://github.com/FalkorDB/FalkorDB/releases/tag/v6.0.0)). Plan: docker compose with `falkordb/falkordb-server` + FastAPI, bind-mount `/var/lib/falkordb/data`, `restart: unless-stopped`, Caddy/nginx for HTTPS **[inf]**. Best resources for $0; highest effort/risk. Card/identity verification at sign-up: **[unk]** (not read).

**B4 Google Cloud e2-micro.** Always Free: one e2-micro in us-west1/us-central1/us-east1, 30GB standard disk, 1GB/mo NA egress ([SO quoting GCP docs](https://stackoverflow.com/questions/63186893/google-cloud-platform-free-tier-limits-from-compute-engine?rq=3); secondary summary: [dev.to](https://dev.to/desirichdev/how-to-deploy-n8n-on-google-cloud-for-free-forever-ddk), 1GB RAM; I could not retrieve the e2-micro line from the official [free-features page](https://cloud.google.com/free/docs/free-cloud-features) text). $300 / 90-day trial credit for new accounts (official page). 1GB RAM shared by OS + FalkorDB + FastAPI is tight **[inf]** — OK only for a small demo graph; add swap. Card required per [whichdevtool](https://whichdevtool.com/tools/google-compute-engine) (secondary).

**B5 Fly.io.** No free tier ([temps.sh](https://temps.sh/blog/fly-io-pricing-2026)); shared-cpu-1x 512MB $3.32/mo, 1GB $5.92/mo, 256MB $2.02/mo; volumes $0.15/GB/mo ([Fly pricing](https://fly.io/docs/about/pricing/), [docs.fly.io](https://docs.fly.io/about/pricing)). Reasonable (~$6-9/mo with app) but costlier and more CLI-heavy than Railway.

**B6 Not suitable.** Render free web services spin down after 15 minutes idle, take ~1 min to wake, and cannot attach persistent disks ([Render free](https://render.com/docs/free)); its free Key Value is 25MB RAM ([pricing](https://render.com/pricing)) and is not FalkorDB. Koyeb: one free web service with 512MB RAM, 0.1 vCPU, 2GB SSD, scales to zero, card required ([FAQ](https://www.koyeb.com/docs/faqs/pricing), [scale-to-zero](https://www.koyeb.com/docs/run-and-scale/scale-to-zero)); only one free service, so DB + app can't both be free, and TCP/volume support on the free instance is **[unk]**.

## C. Recommendation

**Dev (now):** use FalkorDB Cloud Free as a stop-gap today (zero install, but reseed from script; stops after 1 day idle). In parallel, with your approval, do A1: `wsl --install -d Ubuntu` -> `wsl -s Ubuntu` -> Docker Engine in Ubuntu -> the official `docker run ... falkordb/falkordb` command. Skip A2 (Docker Desktop repair) unless A1 fails; skip FalkorDBLite for the shared dev DB.

**Demo hosting:** **Railway Hobby** with the verified FalkorDB template (persistent volume) and the FastAPI app as a second service in the same project over `FALKORDB_PRIVATE_URL`. Expected cost ~$5-10/mo **[inf]**, set a billing alert; keep the subscription active through at least mid-November. Deploy by ~Oct 16 so there is time to check restarts/persistence, and set the FalkorDB password (template generates one) and don't expose the public URL unless needed **[inf]**.

**Fallback (if Railway budget/verification fails):** (1) Oracle Always Free A1 or GCP e2-micro VM running docker compose (free, higher effort; mitigate Oracle idle reclamation by checking the VM weekly) — the app should reseed an empty graph at startup; (2) FalkorDB Cloud Free as emergency DB (reseed at start, accept stop/delete risk); and in every case submit the complete local setup instructions + demo video, which the hackathon accepts in lieu of a live deployment.

## Open items to check before committing
- Railway: confirm trial type (Full vs Limited) shows full network access at sign-up; confirm actual RAM of idle FalkorDB 6.0 on the dashboard.
- FalkorDB Cloud: if a keep-alive is wanted, ask support@falkordb.com whether queries count as "utilized" ([contact on free tier page](https://docs.falkordb.com/cloud/tiers/free)).
