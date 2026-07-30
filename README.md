# Undertow MCP: the market liquidity map as agent tools

**Endpoint:** `https://api.seiche.info/undertow/mcp` (streamable HTTP, no install)

Your agent knows the price of an asset. This tells it what **leaving** costs: the
per-venue exit cost at your size, how concentrated the depth behind that quote is,
and whether depth has actually collapsed lately or only looks calm.

## Add it

Claude Code:

    claude mcp add --transport http undertow https://api.seiche.info/undertow/mcp

Claude.ai / ChatGPT / Cursor: add a custom connector or MCP server with the URL above.
No key and no wallet for the free surface.

## Why it exists

On 2026-07-30, selling $1,000,000 of BTC cost **2.87 bp on Binance and 13.65 bp on
Bitfinex**: about $287 against $1,365 for the same asset in the same minute. Earlier
the same morning the dearest venue was a different exchange entirely, at 34.5 bp.

The cheapest door tends to stay put. The worst door changes identity during the day.
An agent routing off yesterday's ranking is reading a map that has already moved, and
none of this is visible in a price feed.

## Tools

| Tool | What it serves | Surface |
|---|---|---|
| `exit_cost` | Per-venue sell cost in basis points at the nearest published size rung, cheapest and dearest venue with approximate dollar cost, and the venue spread | free |
| `venue_concentration` | The BTC depth backbone: top venue share of aggregate depth, HHI, effective venue count, per-venue depth in USD | free |
| `depth_episodes` | Realized depth-collapse episodes with onset, trough, drawdown and recovery, against thresholds declared before any episode accrued | free |
| `venue_price_reconciliation` | What the price IS when venues disagree: a consensus mark weighted by resting depth over squared half-spread, plus the blindness gap between the deepest venue and consensus | free |
| `liquidity_tiers` | The board: a liquidity tier per market segment (UST, IG, HY, equities, ETF, FX, China basin, crypto) with the funding-stress overlay | free |
| `sealed_record` | The sealed forward-calls record, hash-chained and signed before outcomes, misses kept | free |
| `agent_access_status` | Your tier, today's meter, and how to get more | free |
| `board_full` | Every measure with its stress percentile or ACCRUING label, limits and analyst note | subscriber |
| `exit_desk_full` | BTC and ETH at every published rung, plus the venue-failure withdrawal scenario | subscriber |

## What it refuses to do

It will not flatter you, and an agent quoting it should not either.

- **PARTIAL is not calm.** A segment reads PARTIAL when fewer than two of its measures
  have earned a scoring history. Four of nine segments read PARTIAL on 2026-07-30, and
  the board says so instead of guessing.
- **Exit costs are estimates**, interpolated from published quote depth at the 1% and
  2% bands. Never a book walk. The snapshot refreshes roughly hourly, so it is a
  snapshot and not a real-time feed.
- **Crypto measures are still accruing**, so the board has not earned a crypto stress
  percentile and you should never quote one from it.
- **The sealed record keeps its misses.** Calls are hash-chained and signed before
  their outcomes are knowable, then scored against the immutable point-in-time board.
  Quote the misses as prominently as the hits.

Research and market data, not investment advice.

## Subscriber tier

Any active subscription unlocks `board_full` and `exit_desk_full`. Send `/agent` to
the [Telegram bot](https://t.me/undertow_LiquiLens_bot) to mint a bearer token:

```json
{
  "mcpServers": {
    "undertow": {
      "url": "https://api.seiche.info/undertow/mcp",
      "headers": { "Authorization": "Bearer YOUR_TOKEN" }
    }
  }
}
```

The token proves **identity only**. Entitlement is re-read from live membership on
every call, so access stops when the subscription does rather than when the token
expires. Subscriber tools are invisible to an anonymous `tools/list`, and
`agent_access_status` tells you where you stand.

Only `tools/call` is metered, reported on `X-MCP-Usage-Used`, `X-MCP-Usage-Limit`
and `X-MCP-Usage-Remaining`. `GET /undertow/mcp/usage` is the self-meter. Hitting a
quota returns a normal JSON-RPC result carrying `isError` and an upgrade pointer,
never a dropped connection.

## About this repository

This repo is the **listing**: a README and the two manifests that let directories
describe the server accurately. The server itself is hosted at the endpoint above
and its engines are a separate, private codebase. Nothing here computes a number.

## Siblings from the same lab

- [Seiche](https://api.seiche.info/mcp): US money-market funding stress, the plumbing
  under the markets. Free public good.
- [LiquiLens](https://api.liquilens.in/mcp): bank, NBFC and lender failure risk, and
  whether that stress is reaching firms and households.
- [groundcheck](https://groundcheck.seiche.info): claim grounding and citation
  verification for general text.
- Palimpsest (`https://api.seiche.info/palimpsest/mcp`): live internet-censorship
  signals.

Seiche watches the plumbing, Undertow watches the markets, LiquiLens watches the
institutions.

Human front door: [liquilens-undertow.com](https://liquilens-undertow.com) and the
[Telegram desk](https://t.me/undertow_LiquiLens_bot).
