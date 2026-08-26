# EuroValidate MCP Server

MCP ([Model Context Protocol](https://modelcontextprotocol.io)) server for [EuroValidate](https://eurovalidate.com) — lets Claude, ChatGPT and any MCP-capable agent **validate EU VAT numbers (VIES), IBANs and EORI customs numbers, look up company data, and fetch VAT rates** through one reliable REST API.

## Why

Validating European business data normally means juggling five fragmented government services: the VIES SOAP API (which times out constantly — Germany alone generates 95% of its errors), the EC EORI endpoint, HMRC, GLEIF, and national registries. EuroValidate wraps them into one cache-first JSON API with per-country circuit breakers and graceful degradation — and this MCP server exposes it to LLM agents as ready-to-use tools.

## Tools

| Tool | What it does |
|---|---|
| `validate_vat` | Validate an EU/UK VAT number via VIES/HMRC — returns validity + registered company name & address (where the member state exposes it) + confidence level |
| `validate_iban` | Validate an IBAN (offline MOD-97) and resolve bank name + BIC |
| `validate_eori` | Validate an EORI customs number (EU / GB / XI Northern Ireland) |
| `lookup_company_by_lei` | Company data by Legal Entity Identifier (GLEIF) |
| `lookup_company_by_vat` | Company data by VAT number — fallback for DE/ES where VIES hides names |
| `get_vat_rates` | Current VAT rates for an EU country |
| `check_service_status` | Live health of VIES (per country), EORI, HMRC, GLEIF — no API key needed |

## Setup

1. Get a **free API key** (100 requests/month, no credit card) at [eurovalidate.com](https://eurovalidate.com).
2. Add the server to your MCP client:

### Claude Desktop / Claude Code

```json
{
  "mcpServers": {
    "eurovalidate": {
      "command": "uvx",
      "args": ["eurovalidate-mcp"],
      "env": { "EUROVALIDATE_API_KEY": "your_api_key" }
    }
  }
}
```

Claude Code one-liner:

```bash
claude mcp add eurovalidate -e EUROVALIDATE_API_KEY=your_api_key -- uvx eurovalidate-mcp
```

### Any other MCP client

Run over stdio:

```bash
EUROVALIDATE_API_KEY=your_api_key uvx eurovalidate-mcp
```

Or install permanently: `pip install eurovalidate-mcp` → `eurovalidate-mcp`.

## Example prompts

- *"Validate VAT number DE811569869 and tell me the company behind it"*
- *"Check if this IBAN is valid and which bank it belongs to: DE89 3704 0044 0532 0130 00"*
- *"Is VIES down for Germany right now?"*
- *"What's the VAT rate in Portugal?"*
- *"Validate the VAT numbers of these 5 suppliers before I invoice them"*

## Notes for agents (and humans)

- **Germany and Spain never return company name/address** over VIES (data-protection law) — use `lookup_company_by_vat` as a fallback.
- **Greece** is `EL` in VIES but `GR` in ISO 3166 — both are accepted.
- Every response carries `confidence: HIGH|MEDIUM|LOW|UNKNOWN` and the upstream `source`, so agents can reason about data freshness when a government service is down.
- Free tier: 100 requests/month. Paid plans from €19/mo (500,000 requests/month) at [eurovalidate.com](https://eurovalidate.com).

## Environment variables

| Variable | Required | Default |
|---|---|---|
| `EUROVALIDATE_API_KEY` | yes (except `check_service_status`) | — |
| `EUROVALIDATE_BASE_URL` | no | `https://api.eurovalidate.com` |

## License

MIT

---
mcp-name: io.github.nitrych/eurovalidate-mcp
