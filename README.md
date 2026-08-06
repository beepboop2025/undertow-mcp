# Undertow MCP | Market liquidity and exit-cost tools

**Endpoint:** `https://api.seiche.info/undertow/mcp` (streamable HTTP, no install)

**Try it live:** [liquilens-undertow.com/developers](https://liquilens-undertow.com/developers/) ·
**API catalog:** [api.seiche.info/undertow](https://api.seiche.info/undertow/)

Undertow exposes estimated exit cost by position size and venue, the concentration of
quoted depth, realized depth-collapse episodes, and liquidity tiers across market segments.

## Add it

Claude Code:

    claude mcp add --transport http undertow https://api.seiche.info/undertow/mcp

Claude.ai / ChatGPT / Cursor: add a custom connector or MCP server with the URL above.
No key and no wallet for the free surface.

## Example

On 2026-07-30, selling $1,000,000 of BTC cost **2.87 bp on Binance and 13.65 bp on
Bitfinex**: about $287 against $1,365 for the same asset in the same minute. Earlier
the same morning the dearest venue was a different exchange entirely, at 34.5 bp.

Venue rankings can change during the day, and those differences are not visible in a
single consolidated price. Undertow publishes the observation time and venue inputs with
the estimate.

## Tools

| Tool | What it serves | Surface |
|---|---|---|
| `exit_cost` | Per-venue sell cost in basis points at the nearest published size rung, cheapest and dearest venue with approximate dollar cost, and the venue spread | free |
| `venue_concentration` | The BTC depth backbone: top venue share of aggregate depth, HHI, effective venue count, per-venue depth in USD | free |
| `depth_episodes` | Realized depth-collapse episodes with onset, trough, drawdown and recovery, against thresholds declared before any episode accrued | free |
| `venue_price_reconciliation` | What the price IS when venues disagree: a consensus mark weighted by resting depth over squared half-spread, plus the blindness gap between the deepest venue and consensus | free |
| `liquidity_tiers` | The board: a liquidity tier per market segment (UST, IG, HY, equities, ETF, FX, China basin, crypto) with the funding-stress overlay | free |
| `sealed_record` | The sealed forward-calls record, hash-chained and signed before outcomes, misses kept | free |
| `unwind_watch` | Banded public watch over institutional unwind time and forced-sale pressure, with exact sensitive quantities withheld | free |
| `agent_access_status` | Your tier, today's meter, and how to get more | free |
| `board_full` | Every measure with its stress percentile or ACCRUING label, limits and analyst note | subscriber |
| `exit_desk_full` | BTC and ETH at every published rung, plus the venue-failure withdrawal scenario | subscriber |
| `exit_schedule` | Position-sized hour-by-hour liquidation schedule beside immediate and TWAP baselines | subscriber |
| `tide_clock` | Clock-phase liquidity map and exit-cost-by-phase for BTC or ETH perpetuals | subscriber |
| `corporate_transmission` | Whether funding stress is reaching nonfinancial firms | subscriber |
| `household_credit` | Whether funding stress is reaching household balance sheets | subscriber |
| `divergence_status` | Compact comparison of corporate and household transmission regimes | subscriber |
| `unwind_stress` | Full institutional unwind and forced-sale stress pack | subscriber |

## Limitations

- **PARTIAL is not calm.** A segment reads PARTIAL when fewer than two of its measures
  have earned a scoring history. Four of nine segments read PARTIAL on 2026-07-30, and
  the board says so instead of guessing.
- **Exit costs are estimates**, interpolated from published quote depth at the 1% and
  2% bands. Never a book walk. The snapshot refreshes roughly hourly, so it is a
  snapshot and not a real-time feed.
- **Crypto measures are still accruing**, so the board has not earned a crypto stress
  percentile and you should never quote one from it.
- **The sealed record includes misses.** Calls are hash-chained and signed before
  their outcomes are knowable, then scored against the point-in-time board.

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
describe the server accurately. The server itself is hosted at the endpoint above;
its source and verification tests live in the
[Undertow product repository](https://github.com/beepboop2025/liquilens-undertow).
Nothing in this listing repo computes a number.

## Siblings from the same lab

- [Seiche](https://api.seiche.info/mcp): US dollar funding stress.
- [LiquiLens](https://api.liquilens.in/mcp): bank, NBFC and lender failure risk, and
  whether that stress is reaching firms and households.
- [groundcheck](https://groundcheck.seiche.info): claim grounding and citation
  verification for general text.
- Palimpsest (`https://api.seiche.info/palimpsest/mcp`): live internet-censorship
  signals.

Human front door: [liquilens-undertow.com](https://liquilens-undertow.com) and the
[Telegram desk](https://t.me/undertow_LiquiLens_bot).
