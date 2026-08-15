# Undertow MCP | Market liquidity and exit-cost tools

**Endpoint:** `https://api.seiche.info/undertow/mcp` (streamable HTTP, no install)

**Try it live:** [liquilens-undertow.com/developers](https://liquilens-undertow.com/developers/) ·
**API catalog:** [api.seiche.info/undertow](https://api.seiche.info/undertow/)

Undertow exposes estimated exit cost by position size and venue, the concentration of
quoted depth, realized depth-collapse episodes, and liquidity tiers across market segments.
This MCP 1.9.0 endpoint exposes 17 read-only tools, split into 9 public and 8 subscriber
tools, plus 3 guided prompts. Its capability inventory is pinned to signed core commit
`79b3f6bc40b2917795954ad5a7119a8a95ce5b74`.

## Add it

Claude Code:

    claude mcp add --transport http undertow https://api.seiche.info/undertow/mcp

Claude.ai / ChatGPT / Cursor: add a custom connector or MCP server with the URL above.
No key and no wallet for the free surface.

This repository is the discovery and documentation mirror. The official registry serves
[`io.github.beepboop2025/undertow` version 1.9.0](https://registry.modelcontextprotocol.io/v0.1/servers/io.github.beepboop2025%2Fundertow/versions/latest).

## Protocol compatibility

- `2026-07-28`: stateless requests use `server/discover`, per-request `_meta`,
  `MCP-Protocol-Version`, and mirrored `Mcp-Method` / `Mcp-Name` routing headers.
- `2025-11-25`, `2025-06-18`, and `2025-03-26`: retained legacy initialization,
  tools, prompts, notifications, batching, and ping behavior.
- Discovery identifies all nine public and eight subscriber tools. Anonymous
  `tools/list` returns only the public inventory; entitlement is checked fresh on every
  subscriber request.
- `resources/list` and `resources/templates/list` return explicit empty catalogs.
  `resources/read` returns a not-found error and never invents a resource.

## Example

In the snapshot generated at **2026-08-08T15:01:22Z**, selling $1,000,000 of BTC
at the selected **$1,000,000 published size rung** cost **2.386 bp on Binance and
13.623 bp on Bitfinex**: about $238.60 against $1,362.30. Gemini was the dearest
observed venue in that same snapshot at 25.852 bp, or about $2,585.20.

Venue rankings can change during the day, and those differences are not visible in a
single consolidated price. Undertow publishes the observation time and venue inputs with
the estimate.

## Tools

| Tool | What it serves | Surface |
|---|---|---|
| `agent_access_status` | Your current tier, daily meter, grants, and the exact route to Agent or Desk access | free |
| `board_full` | Every measure with its stress percentile or ACCRUING label, limits and analyst note | subscriber |
| `corporate_transmission` | Whether funding stress is reaching nonfinancial firms | subscriber |
| `depth_episodes` | Realized depth-collapse episodes with onset, trough, drawdown and recovery, against thresholds declared before any episode accrued | free |
| `divergence_status` | Compact comparison of corporate and household transmission regimes | subscriber |
| `exit_cost` | Per-venue sell cost in basis points at the nearest published size rung, cheapest and dearest venue with approximate dollar cost, and the venue spread | free |
| `exit_desk_full` | BTC and ETH at every published rung, plus the venue-failure withdrawal scenario | subscriber |
| `exit_schedule` | Position-sized hour-by-hour liquidation schedule beside immediate and TWAP baselines | subscriber |
| `household_credit` | Whether funding stress is reaching household balance sheets | subscriber |
| `latest_article` | The exact reviewed daily market-liquidity editorial with its evidence clock and publication authority | free |
| `liquidity_tiers` | A liquidity tier per market segment (UST, IG, HY, equities, ETF, FX, China basin, crypto) with the funding-stress overlay | free |
| `sealed_record` | The sealed forward-calls record, hash-chained and signed before outcomes, misses kept | free |
| `tide_clock` | Clock-phase liquidity map and exit-cost-by-phase for BTC or ETH perpetuals | subscriber |
| `unwind_stress` | Full institutional unwind and forced-sale stress pack | subscriber |
| `unwind_watch` | Banded public watch over institutional unwind time and forced-sale pressure, with exact sensitive quantities withheld | free |
| `venue_concentration` | The BTC depth backbone: top venue share of aggregate depth, HHI, effective venue count, per-venue depth in USD | free |
| `venue_price_reconciliation` | A consensus mark weighted by resting depth over squared half-spread, plus the gap between the deepest venue and consensus | free |

## Prompts

| Prompt | Guided playbook |
|---|---|
| `can_this_book_exit` | Compare watched-book door width, unwind horizon, margin clock, venue concentration, and realized depth collapses |
| `exit_cost_check` | Price a position-sized exit across venues and identify the observed depth limitations |
| `market_liquidity_briefing` | Read the market-level liquidity board, funding overlay, concentration, and current exit-cost evidence together |

Commodity futures are intentionally absent from that table. Undertow has no
licensed point-in-time depth by contract month, venue and session, so
executable commodity exit cost is `CANNOT_ASSESS_EXECUTABLE_EXIT_COST`; open
interest or daily volume is never substituted. For aggregate WTI/Henry Hub
cash pressure, Cushing and benchmark structure, call Seiche's public
`oil_funding_context` or use `/oil` in
[`@seiche_desk_bot`](https://t.me/seiche_desk_bot).

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
- **Commodity execution is a declared coverage gap.** Ballast is useful upstream
  context from Seiche, not a depth ladder and not an Undertow exit-cost estimate.

Research and market data, not investment advice.

## Subscriber tier

The Agent and Desk tiers unlock the eight subscriber tools. Send `/agent` to the
[Telegram bot](https://t.me/undertow_LiquiLens_bot) to mint a bearer token:

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
- [Palimpsest](https://api.seiche.info/palimpsest/mcp): live internet-censorship
  signals.

Human front door: [liquilens-undertow.com](https://liquilens-undertow.com) and the
[Telegram desk](https://t.me/undertow_LiquiLens_bot).
