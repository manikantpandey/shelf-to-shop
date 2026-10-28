# Runbook

How to deploy Shelf-to-Shop, operate it, rotate keys and handle an incident.

Production shape: one EC2 machine in `ap-south-1` (Mumbai) running Docker Compose (`deploy/compose.prod.yml`):
Caddy (HTTPS, web app, security headers) → API → Postgres, plus a worker that runs the AI pipeline.
Secrets live in AWS Systems Manager Parameter Store; the machine reads them at boot. No SSH port is open;
you get a shell through Session Manager in the AWS console.

## 1. First deploy

### 1.1 Secrets (once, about 5 minutes)
AWS console → region **Asia Pacific (Mumbai)** → **Systems Manager → Parameter Store → Create parameter**.
Create each of these as type **SecureString** (default KMS key):

| Name | Value |
|---|---|
| `/shelf-to-shop/META_API_KEY` | your Meta Model API key (`LLM_…`) |
| `/shelf-to-shop/SECRET_KEY` | 48+ random characters, e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `/shelf-to-shop/POSTGRES_PASSWORD` | another random string made the same way |
| `/shelf-to-shop/BASETEN_API_KEY` | optional |

Never paste these anywhere else (chat, tickets, the repo).

### 1.2 The stack (about 5-10 minutes)
1. AWS console → **CloudFormation → Create stack → With new resources**.
2. **Upload a template file**: `deploy/cloudformation.yml`.
3. Stack name `shelf-to-shop`. Parameters: set **AcmeEmail** (Let's Encrypt notices); keep the
   defaults (`shop.shankhyaai.com`, `t3.medium`, 30 GiB, `/shelf-to-shop`).
4. Tick **I acknowledge that AWS CloudFormation might create IAM resources** (the machine's role) and create.
5. When the stack shows `CREATE_COMPLETE`, open **Outputs** and copy **ElasticIp**.

The template needs the account's default VPC in Mumbai (present unless someone deleted it).

### 1.3 DNS (2 minutes)
GoDaddy → **My Products → shankhyaai.com → DNS → Add New Record**: type **A**, name **shop**, value =
the ElasticIp, TTL 600 seconds. Do not touch the `@` A record or the `www` CNAME (they serve the Vercel site).
Check with `nslookup shop.shankhyaai.com 1.1.1.1`. Caddy obtains the HTTPS certificate on its own once DNS
points at the machine (it retries until then). Then open https://shop.shankhyaai.com.

The machine needs 3-5 minutes after creation to install Docker and build the images.

### 1.4 The sample shop for demo sign-in (optional, about 10 minutes)
"Try the sample shop" on the sign-in page gives each visitor a private copy of a shop built from real
shelf videos. Build it once on the server, from videos you own:

1. S3 console (any bucket you own) → upload the clips → select each → **Actions → Share with a presigned
   URL** (1 hour).
2. In the Session Manager shell, download them and run the seed script inside the API container. It runs
   every clip through the real models (about $0.10 per 30-second clip), publishes the first two and
   leaves the last one waiting for review, so the demo can show "Fix prices":
   ```sh
   cd /opt/shelf/deploy
   sudo mkdir -p /opt/seed && cd /opt/seed
   sudo curl -o a.mp4 "PRESIGNED_URL_1"   # repeat for b.mp4, c.mp4
   cd /opt/shelf/deploy
   for f in a b c; do sudo docker compose -f compose.prod.yml cp /opt/seed/$f.mp4 api:/tmp/$f.mp4; done
   sudo docker compose -f compose.prod.yml exec api python scripts/seed_demo.py      --name "Sharma General Store" --whatsapp "YOUR NUMBER" --publish 2      --hours "8 am to 10 pm" --delivery both --delivery-note "Free home delivery within 2 km"      --min-order 100 --about "Your neighbourhood kirana for snacks, cold drinks and daily needs."      --notice "Diwali offer: Haldiram's packs at ₹4" /tmp/a.mp4 /tmp/b.mp4 /tmp/c.mp4
   ```
3. Delete the clips from S3 and `/opt/seed` afterwards. Rerun with `--reset` to rebuild the sample shop.

The WhatsApp number is where "Order on WhatsApp" taps in every copy of the sample shop go, so use a
number you are happy to receive test orders on. The sample shop itself is never public; only copies are.

## 2. Day-to-day

Open a shell: CloudFormation **Outputs → SessionManager** link (or EC2 → instance → Connect → Session Manager).

| Task | Command (in the Session Manager shell) |
|---|---|
| Deploy the latest `main` | `sudo /opt/shelf/deploy/update.sh` |
| Deploy a tag or commit | `sudo /opt/shelf/deploy/update.sh v0.2.0` |
| See what is running | `cd /opt/shelf/deploy && sudo docker compose -f compose.prod.yml ps` |
| Follow logs | `sudo docker compose -f compose.prod.yml logs -f --tail 100 api worker` |
| Health | `curl -s https://shop.shankhyaai.com/api/v1/health/ready` |
| Postgres shell | `sudo docker compose -f compose.prod.yml exec db psql -U shelf shelf` |

Logs are JSON with a `request_id` on every line; the same id is in the `x-request-id` response header and
in error responses, so a seller's error message can be traced to its log lines.

Spend: each job's model cost is stored on the job (`jobs.cost_usd`) and every model call is in the job's
`runlog.jsonl`. The per-job cap (`SPEND_CAP_PER_JOB_USD`, default $0.50) stops a job before the call that
would cross it. The daily caps per shop (`SPEND_CAP_PER_WORKSPACE_DAY_USD`, default $3) and for the whole
service (`SPEND_CAP_PER_INSTANCE_DAY_USD`, default $25) hold across jobs and workers: totals live in the
`spend_days` table and roll over at midnight India time. A job that hits one stops with "Try again
tomorrow"; its finished stages are kept, so the retry costs only what was left. Today's totals, in the
Postgres shell (amounts in millionths of a dollar):
`select scope, day, micros / 1e6 as usd from spend_days where day = current_date order by micros desc;`
To change a cap, create or update `/shelf-to-shop/SPEND_CAP_PER_WORKSPACE_DAY_USD` (or the other two)
in Parameter Store as a String and rerun bootstrap ([section 3](#3-rotating-keys)); locally, set it in `.env`.

## 3. Rotating keys

| Secret | How | Effect |
|---|---|---|
| Meta key | Create a new key in the Model API dashboard, update `/shelf-to-shop/META_API_KEY`, rerun bootstrap (below), then delete the old key in the dashboard | Running jobs finish or fail; failed jobs can be retried from the app |
| `SECRET_KEY` | Update the parameter, rerun bootstrap | All sessions end; sellers sign in again |
| Postgres password | Change it inside Postgres first (`ALTER USER shelf PASSWORD '…'`), then update the parameter and rerun bootstrap | Brief API restart |

Rerun bootstrap (rewrites `deploy/.env` from Parameter Store and restarts):
```sh
sudo /opt/shelf/deploy/bootstrap.sh shop.shankhyaai.com YOUR_ACME_EMAIL /shelf-to-shop/ ap-south-1
```

## 4. Incidents

**A key leaked** (seen in a log, repo, chat or screenshot): rotate it immediately (section 3), then check
the Meta dashboard usage for spikes, and search the repo history with `gitleaks git --redact .`.

**The site is down**: `docker compose ps`; restart one service with
`sudo docker compose -f compose.prod.yml restart api`. If the disk is full: `df -h`, then
`sudo docker system prune -f` (images only; volumes keep data).

**Jobs stuck in "running"**: the worker's lease expires after 15 minutes and another attempt starts; a
job that failed shows "Try again" to the seller (it resumes from the last finished stage). Check the
worker logs first.

**Personal data incident** (DPDP Act 2023 / Rules 2025): contain it, record what data and which sellers
were affected, inform the affected sellers and the Data Protection Board without delay, and send the
detailed report to the Board within 72 hours. Audit events (`audit_events` table) show who did what.

**AI misuse report about a published catalog**: the seller approved every published item; unpublish by
removing the catalog version (`catalogs` row and `public/<slug>/v<n>` media) and contact the seller.

## 5. Tear down
CloudFormation → `shelf-to-shop` → **Delete**. This deletes the machine, its disk (all data), the
Elastic IP and the role. Remove the GoDaddy `shop` record and the Parameter Store parameters too.

## 6. Local development
`make dev` runs Postgres, the API (worker inline, fake providers by default) and the web app in Docker:
open http://localhost:5173. To use real models locally: `PROVIDERS=meta META_API_KEY=… make dev`.
Without Docker: `make api` (SQLite) and `make web` in two terminals, with `WORKER_INLINE=true`.
