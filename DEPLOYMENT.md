# Deployment

Documentation is split by deployment mode. Pick the one that applies:

| Mode | Where it runs | Cost | Guide |
|------|-------------|------|-------|
| **Mode 1** — Local dev | Your laptop (Docker Compose) | $0 | [docs/local-dev.md](docs/local-dev.md) |
| **Mode 2** — Cloud-free | Supabase + Render + R2 + Vercel | $0 | [HOSTING.md](HOSTING.md) |
| **Mode 3** — Production VPS | Single Hetzner/DigitalOcean server | ~€6/mo | [docs/production-vps.md](docs/production-vps.md) |

## Which mode should I use?

- **Building or testing locally** → Mode 1
- **Sharing with a client or running a demo** → Mode 2 (free, no VPS to manage)
- **Production with custom domain, backups, always-on** → Mode 3
