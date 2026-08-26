"""EuroValidate MCP server — EU VAT, IBAN, EORI validation and company lookup.

Exposes the EuroValidate REST API (https://eurovalidate.com) as MCP tools so
LLM agents can validate European business data directly.

Auth: set the EUROVALIDATE_API_KEY environment variable.
Get a free key (100 requests/month, no card) at https://eurovalidate.com.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

BASE_URL = os.environ.get("EUROVALIDATE_BASE_URL", "https://api.eurovalidate.com")

server = MCPServer(
    name="eurovalidate",
    title="EuroValidate — EU business data validation",
    instructions=(
        "Validate European business data: EU/UK VAT numbers (via VIES, with "
        "registered company name & address), IBANs (MOD-97 + bank/BIC lookup), "
        "EORI customs numbers, company data by LEI, and current VAT rates per "
        "country. Every response includes a confidence level (HIGH/MEDIUM/LOW/"
        "UNKNOWN) and upstream source. Requires EUROVALIDATE_API_KEY (free key "
        "at https://eurovalidate.com, 100 requests/month, no credit card). "
        "Note: Germany and Spain never return company name/address (data "
        "protection law); Greece is 'EL' in VIES but both EL and GR are accepted."
    ),
    website_url="https://eurovalidate.com",
)


def _headers() -> dict[str, str]:
    key = os.environ.get("EUROVALIDATE_API_KEY", "")
    headers = {"User-Agent": "eurovalidate-mcp"}
    if key:
        headers["X-API-Key"] = key
    return headers


async def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(f"{BASE_URL}{path}", params=params, headers=_headers())
        try:
            body = resp.json()
        except ValueError:
            resp.raise_for_status()
            raise
        if resp.status_code == 401:
            return {
                "error": "Missing or invalid API key. Set the EUROVALIDATE_API_KEY "
                "environment variable — get a free key at https://eurovalidate.com "
                "(100 requests/month, no credit card required).",
                "details": body,
            }
        return body


@server.tool()
async def validate_vat(vat_number: str, country_code: str | None = None) -> dict[str, Any]:
    """Validate an EU or UK VAT number via VIES/HMRC.

    Returns validity, registered company name and address where the member
    state exposes them (Germany and Spain never do), a confidence level, and
    the upstream source. Accepts the number with or without country prefix
    (e.g. "DE123456789" or "123456789" + country_code="DE"). Greece: EL or GR
    both work.
    """
    params = {"country": country_code} if country_code else None
    return await _get(f"/v1/vat/{vat_number}", params)


@server.tool()
async def validate_iban(iban: str) -> dict[str, Any]:
    """Validate an IBAN (offline MOD-97 checksum) and resolve the bank name and BIC.

    Covers all SEPA countries. Accepts the IBAN with or without spaces.
    """
    return await _get(f"/v1/iban/{iban.replace(' ', '')}")


@server.tool()
async def validate_eori(eori_number: str) -> dict[str, Any]:
    """Validate an EORI customs number (EU via EC, GB via HMRC, XI for Northern Ireland)."""
    return await _get(f"/v1/eori/{eori_number}")


@server.tool()
async def lookup_company_by_lei(lei: str) -> dict[str, Any]:
    """Look up company data (legal name, address, status) by LEI via GLEIF."""
    return await _get(f"/v1/company/lei/{lei}")


@server.tool()
async def lookup_company_by_vat(vat_number: str) -> dict[str, Any]:
    """Look up company data by VAT number (GLEIF cross-reference).

    Useful as a fallback for German/Spanish VAT numbers where VIES returns no
    company name/address by law.
    """
    return await _get(f"/v1/company/vat/{vat_number}")


@server.tool()
async def get_vat_rates(country_code: str) -> dict[str, Any]:
    """Get current VAT rates (standard/reduced) for an EU country by ISO 3166-1 alpha-2 code."""
    return await _get(f"/v1/vat-rates/{country_code}")


@server.tool()
async def check_service_status() -> dict[str, Any]:
    """Check live health of upstream government services (VIES per-country, EORI, HMRC, GLEIF).

    Public endpoint — works without an API key. Use it to explain why a
    validation returned reduced confidence (e.g. Germany's VIES endpoint down).
    """
    return await _get("/v1/status")


def main() -> None:
    """Run the MCP server over stdio."""
    server.run("stdio")


if __name__ == "__main__":
    main()
