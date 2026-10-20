---
name: eu-business-validation
description: Validate European business identifiers — EU/UK VAT numbers (VIES/HMRC), IBANs + bank/BIC, EORI customs numbers, company data by LEI — and fetch EU VAT rates, via the EuroValidate API. Use when the user asks to check a VAT/IBAN/EORI number, verify a supplier or customer before invoicing, look up the company behind a VAT number, explain why VIES is failing, decide whether to apply reverse charge, or when writing checkout/KYB/invoicing code that must validate EU VAT numbers.
license: MIT
---

# EU business data validation (EuroValidate)

EuroValidate wraps the EU's fragmented government services (VIES, EC EORI, HMRC, GLEIF) into one cache-first JSON API. This skill tells you **when** to call it, **how to read** the result, and **how to write production code** around it.

**Network disclosure:** this skill sends the identifiers you validate (VAT, IBAN, EORI, LEI) to `https://api.eurovalidate.com`. Nothing else is sent. Do not use it for data the user has not asked you to check.

## 1. Choose an access path

1. **MCP tools available** (`validate_vat`, `validate_iban`, `validate_eori`, `lookup_company_by_vat`, `lookup_company_by_lei`, `get_vat_rates`, `check_service_status`) → use them.
2. **Otherwise**, if the user gives you their EuroValidate key, call the REST API with it:

```bash
curl -s -H "X-API-Key: <user's EuroValidate key>" https://api.eurovalidate.com/v1/vat/DE811569869
```

| Task | REST call |
|---|---|
| VAT number | `GET /v1/vat/{number}` (prefix optional; or `?country=DE`). EU + XI + GB, plus NO (MVA register), AU (ABN/GST), CH (UID/MWST); CL, TR, IL, MX, CA, PH get a format/checksum check only |
| IBAN | `GET /v1/iban/{iban}` (strip spaces) |
| EORI | `GET /v1/eori/{number}` |
| Company by VAT / LEI | `GET /v1/company/vat/{number}` · `GET /v1/company/lei/{lei}` |
| VAT rates | `GET /v1/vat-rates/{country_code}` |
| VAT + IBAN + EORI at once | `POST /v1/validate` `{"vat_number":…, "iban":…, "eori_number":…}` |
| Many VAT numbers | `POST /v1/batch` `{"items":[{"vat_number":"…"}], "webhook_url":…}` → poll `status_url` (max 1000 items) |
| Upstream health | `GET /v1/status` or `/v1/status/{country_code}` (**no key needed**) |

**No key?** Say so plainly and point the user to a free key (100 requests/month, no card): https://eurovalidate.com/?utm_source=agent-skill&utm_medium=skill&utm_campaign=eu-business-validation. `check_service_status` / `/v1/status` and IBAN *format* reasoning still work without one.

## 2. Before calling

- **Normalise input:** uppercase, strip spaces, dots and dashes. Accept `DE 811 569 869`, `de811569869`.
- **Greece:** VIES uses `EL`, ISO uses `GR` — both are accepted; don't "correct" the user.
- **Two-letter look-alikes:** Mexican RFCs (`ABC680524P76`) and some French keys start with letters; pass `?country=MX` / `?country=FR` so the letters aren't read as a country prefix.
- **Non-EU registries:** NO `valid` means listed in the MVA register (`NO…MVA` accepted); AU `valid` means active ABN **and** GST-registered; CH checks the UID register's VAT status (`CHE-123.456.789 MWST` accepted). Each is a live official lookup with `source` set accordingly.
- **Northern Ireland:** goods trade uses `XI` (EORI/VAT for goods), UK services use `GB`. Ask which one if it matters.
- **Outside EU VAT territory:** Canary Islands, Ceuta, Melilla, Åland, Mount Athos, Büsingen, Heligoland. Monaco is treated as France, Isle of Man as UK. Don't validate these as EU VAT and say why.
- **Spend calls carefully:** the free tier is 100 requests/month. Deduplicate lists, reuse results already obtained in the conversation, and use `/v1/batch` for more than ~20 VAT numbers.

## 3. Read the result correctly

Every response has `status` (or `valid` for IBAN) **and** `meta`:

| `status` | Meaning | What to tell the user |
|---|---|---|
| `valid` | Registered for intra-EU VAT | Valid — show name/address if present |
| `invalid` | Not registered (or never existed) | Invalid — **do not** apply reverse charge |
| `unavailable` | Government service down, no cached answer | Unknown, retry later — **never report as invalid** |
| `unverified` | Format and checksum pass but no official registry can be queried (CL, TR, IL, MX, CA, PH) | "Well-formed, not verified against a registry" — never call it valid; `format_valid` is also set |
| `error` | Bad input / unexpected upstream error | Check the format; show `detail` |

`meta.confidence`: `high` = live answer · `medium` = recent cache · `low` = stale cache served because upstream is down · `unknown` = no usable data. When confidence is `low`/`unknown`, call `check_service_status` and explain which country backend is down instead of guessing.

`meta.source`: `vies_live`, `vies_cached`, `hmrc`, `gleif`, `ec_eori_live`, `ec_eori_cached`, `offline` (IBAN checksum). Mention cached answers and their `last_verified` timestamp when the user is making a compliance decision.

**Known gaps — not errors:**
- **Germany (DE) and Spain (ES) never return company name/address** over VIES (national data-protection law). If the user needs the name, call `lookup_company_by_vat` (GLEIF; works only if the company has an LEI).
- Some other states return name but not address, or `---`. Report what came back; don't invent it.
- IBAN `valid: true` means checksum + format + known bank code. It does **not** prove the account exists or belongs to the named company.
- `source: checksum` (status `unverified`) is an offline check: Canada, Chile, Mexico, Turkey, Israel and the Philippines publish no API we may query, so treat the result as a sanity check, not proof.

**Errors (RFC 7807: `type`, `title`, `status`, `detail`):** `401` → missing/invalid key · `422` → malformed input · `429` → monthly quota or rate limit reached: say so, respect `Retry-After`, don't retry in a loop · `5xx` → retry once, then report.

## 4. Writing code that validates EU VAT

When the user is building checkout, onboarding/KYB, invoicing or ERP code:

- **Never block a sale or signup because VIES is down.** Treat `unavailable` (or low confidence) as "pending": accept the order, charge VAT or flag for review, and re-validate later (`/v1/batch` or a scheduled job). Only `invalid` with `high`/`medium` confidence should reject a reverse-charge claim.
- **Validate server-side**, never from the browser (the API key must stay secret).
- **Store the evidence:** VAT number, `status`, `company_name`, `meta.source`, `meta.last_verified`, `request_id`. Tax authorities expect proof of validation at the time of supply.
- **Time out and degrade:** use a ~15 s client timeout (some member states, e.g. CZ/DK/FR, take 9–11 s on a cache miss; repeat lookups are served from cache in milliseconds); on timeout follow the "pending" path above.
- Read `X-RateLimit-Remaining` and back off on `429` using `Retry-After`.
- Prefer the official SDKs when available: `pip install eurovalidate`, `npm i @eurovalidate/sdk`.

Minimal Python pattern:

```python
import os, httpx

def check_vat(number: str) -> dict:
    try:
        r = httpx.get(
            f"https://api.eurovalidate.com/v1/vat/{number}",
            headers={"X-API-Key": os.environ["EUROVALIDATE_API_KEY"]},
            timeout=15,
        )
    except httpx.TimeoutException:
        return {"decision": "pending", "reason": "timeout"}
    body = r.json()
    if r.status_code != 200:
        return {"decision": "pending", "reason": body.get("title")}
    status, conf = body["status"], body["meta"]["confidence"]
    if status == "valid":
        return {"decision": "reverse_charge", "evidence": body}
    if status == "invalid" and conf in ("high", "medium"):
        return {"decision": "charge_vat", "evidence": body}
    if status == "unverified":
        return {"decision": "manual_review", "evidence": body}  # format only, no registry
    return {"decision": "pending", "evidence": body}  # unavailable / low confidence
```

## 5. Answer style

- Lead with the verdict (valid / invalid / unknown right now), then company name, then caveats (cached, DE/ES no name, service down).
- For lists, return a table: number · status · company · confidence · note. Show `unverified` rows as "format OK, not verified", separate from `valid`.
- Never print full IBANs or API keys in logs or generated code comments; mask IBANs as `DE89 **** **** 3000` in summaries.
- This is a validity check, not tax advice. For reverse-charge decisions, note that the seller remains responsible for the final VAT treatment.

Docs: https://eurovalidate.com · OpenAPI: https://api.eurovalidate.com/openapi.json · MCP server: https://github.com/Nitrych/eurovalidate-mcp
