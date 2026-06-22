# Security

## The Claude usage panel uses an undocumented API

The Session/Week/Sonnet panel calls `https://api.anthropic.com/api/oauth/usage` with an OAuth bearer token, and refreshes that token against `https://api.anthropic.com/v1/oauth/token`. **Neither endpoint is a documented, supported API.** They can change or vanish without notice, and using them may be subject to Anthropic's terms. This panel is **opt-in** — leave `CLAUDE_REFRESH_TOKEN` blank and none of it runs.

If the endpoints move, override `CLAUDE_TOKEN_URL` / `CLAUDE_USAGE_URL` (no rebuild needed).

## Give the dashboard its OWN login — don't share your workstation's

Claude refresh tokens **rotate**: each refresh invalidates the previous token and issues a new one. If the renderer and your laptop's Claude Code share one token lineage, whichever refreshes second gets rejected — and you'll find your laptop **logged out**.

So mint a dedicated session into a separate config dir (your `~/.claude` stays untouched):

```bash
mkdir -p ~/dash-claude-auth
env CLAUDE_CONFIG_DIR=$HOME/dash-claude-auth claude   # then /login, /exit
jq -r .claudeAiOauth.refreshToken ~/dash-claude-auth/.credentials.json
```

Put that refresh token in `CLAUDE_REFRESH_TOKEN`. The renderer then owns that lineage end to end and persists rotations to `/data/claude_tokens.json`.

## Token handling

- The refresh token is a credential. Keep `renderer/.env` out of git (it's in `.gitignore`) and off shared storage; use your platform's secret mechanism if you have one.
- Tokens persist to the `/data` volume at mode of the container user. Treat that volume as sensitive.
- The usage limits are **account-wide**, so the renderer reports the same numbers regardless of which machine asks.

## Network exposure

The renderer serves **plain HTTP** with **no authentication** — because the Kindle can't do TLS. Keep it on a trusted LAN. The reverse-proxy example restricts the vhost to private ranges (`allow`/`deny`); adjust to your network. Don't expose `/dash.png` to the internet — it may reveal your calendar, location (via weather), and usage.

## Reporting

Found something? Open an issue (or a private report if it's sensitive). This is a hobby project with no warranty (see [LICENSE](LICENSE)); fixes are best-effort.
