# Mode 3 — Production VPS

Full stack on a single server behind Caddy with automatic HTTPS.

Recommended: **Hetzner CX21** (2 vCPU, 4 GB RAM, €5.83/mo) or equivalent.
All services run in Docker Compose — PostGIS, Martin, FastAPI, TiTiler, SvelteKit,
Caddy, and optional PgBouncer for connection pooling.

---

## Step 1 — Provision the server

On Hetzner Cloud: create CX21 with Ubuntu 22.04 LTS, add your SSH public key.
On DigitalOcean: 2 vCPU / 4 GB Droplet, Ubuntu 22.04.

```bash
ssh root@<server-ip>
```

---

## Step 2 — Install Docker

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER
newgrp docker

docker --version && docker compose version
```

---

## Step 3 — Clone and configure

```bash
git clone https://github.com/youruser/geo-stack /opt/geo-stack
cd /opt/geo-stack

cat > .env << 'EOF'
# Database
POSTGRES_DB=geodata
POSTGRES_USER=geouser
POSTGRES_PASSWORD=CHANGE_ME_STRONG_PASSWORD_MIN_16_CHARS

# API behaviour
ENV=production
LOG_LEVEL=info
SHOW_DOCS=false
CORS_ORIGINS=https://yourdomain.com
DB_POOL_SIZE=10

# Domain (Caddy uses these for Let's Encrypt)
DOMAIN=yourdomain.com
ACME_EMAIL=you@yourdomain.com

# Cloudflare R2
R2_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com
R2_ACCESS_KEY=your_access_key
R2_SECRET_KEY=your_secret_key
R2_BUCKET_NAME=geo-data
R2_PUBLIC_URL=https://pub-xxx.r2.dev

# Frontend base URLs (Caddy routes these)
PUBLIC_API_URL=https://yourdomain.com/api
PUBLIC_MARTIN_URL=https://yourdomain.com/tiles
PUBLIC_TITILER_URL=https://yourdomain.com/raster
EOF
```

---

## Step 4 — Open firewall ports

```bash
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (Let's Encrypt challenge + redirect)
ufw allow 443/tcp   # HTTPS
ufw --force enable

# PostGIS (5432) and Martin (3000) must NOT be exposed externally.
# Caddy proxies /tiles → Martin internally. PostGIS is Docker-network-only.
```

---

## Step 5 — Point DNS

In Cloudflare DNS or your registrar, add:

```
A   yourdomain.com     → <server-ip>
A   www.yourdomain.com → <server-ip>
```

Wait for propagation — typically instant on Cloudflare, up to 1 hour elsewhere.
Caddy cannot obtain a Let's Encrypt certificate until DNS resolves.

---

## Step 6 — Start the stack

```bash
cd /opt/geo-stack

docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  up -d

# Watch startup (Caddy will fetch TLS certs on first boot — takes ~30s)
docker compose -f docker-compose.yml -f docker-compose.production.yml logs -f caddy
```

---

## Step 7 — Verify

```bash
curl https://yourdomain.com/health
# → {"status":"ok","postgis":true,"duckdb":true}

curl https://yourdomain.com/tiles/catalog
# → Martin catalog JSON

# Check all containers
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  ps
# All containers should show (healthy)
```

---

## Loading data in production

Same as local, but use the internal PostGIS address (from the server itself):

```bash
# On the server — PostGIS is only on the Docker network
ogr2ogr \
  -f PostgreSQL \
  "PG:host=postgis port=5432 dbname=geodata user=geouser password=<password>" \
  input.shp \
  -nln geo.my_layer \
  -lco GEOMETRY_NAME=geom \
  -lco FID=id \
  -t_srs EPSG:4326 \
  -progress
```

### Restart Martin after loading new tables

Martin only discovers PostGIS tables at startup. After adding a new table, restart it:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  restart martin

# Verify
curl https://yourdomain.com/tiles/geo.my_layer | python3 -m json.tool | grep '"id"'
```

---

## Step 8 — Nightly backups to R2

```bash
# Test the backup manually first
docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  --profile backup run --rm backup

# Schedule nightly at 02:00 server time
(crontab -l 2>/dev/null; echo "0 2 * * * cd /opt/geo-stack && \
  docker compose -f docker-compose.yml -f docker-compose.production.yml \
  --profile backup run --rm backup >> /var/log/geo-stack-backup.log 2>&1") | crontab -
```

---

## Step 9 — GitHub Actions auto-deploy (optional)

Add these secrets in GitHub → Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `PRODUCTION_HOST` | Server IP |
| `PRODUCTION_USER` | `root` or your deploy user |
| `PRODUCTION_SSH_KEY` | Contents of your private SSH key |

Create a `production` environment (Settings → Environments) for branch protection.

Every push to `main` will then SSH into the server, pull, and rebuild the changed
services.

---

## Manual upgrade

```bash
cd /opt/geo-stack
git pull origin main

docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  up -d --build api frontend
```

Only `api` and `frontend` need a rebuild — PostGIS, Martin, and Caddy use upstream
images that change independently.

## Rollback

```bash
git log --oneline -10
git checkout <commit-hash>

docker compose \
  -f docker-compose.yml \
  -f docker-compose.production.yml \
  up -d --build api frontend
```

---

## Troubleshooting

**Caddy fails to get TLS certificate**
- DNS must resolve to the server IP before Caddy can complete the ACME challenge.
- Port 80 must be open (`ufw allow 80/tcp`).
- Check logs: `docker compose logs caddy`

**PostGIS not healthy after deploy**
First boot takes 60–90 seconds to run SQL init scripts. Watch:
```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml logs postgis
```

**Martin returns 404 for a new table**
Martin discovers tables at startup only — restart it after loading new data.

**Out of disk space**
```bash
df -h
docker system prune -f   # removes stopped containers, unused images, build cache
```

**OOM killed (out of memory)**
DuckDB analytics queries can use significant RAM on CX21 (4 GB). Tune:
```bash
DUCKDB_MEMORY=1GB   # in .env — default is 512 MB
DB_POOL_SIZE=5      # reduce if asyncpg connections spike
```
Upgrade to CX31 (8 GB) if DuckDB regularly processes country-scale datasets.
