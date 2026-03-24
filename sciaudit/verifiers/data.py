"""Data claim verifier — checks quantitative claims against primary data sources.

Verifies claims like:
- "US GDP growth was 3.2% in Q3 2023" → FRED API
- "Chile's inflation was 7.8% in 2022" → World Bank API
- "Global oil demand is 104.5 mb/d" → cross-reference multiple sources
"""

from __future__ import annotations

import os
import re

import httpx

from sciaudit.models import (
    Claim,
    ClaimType,
    Severity,
    VerificationEvidence,
    VerificationResult,
    VerificationStatus,
)
from sciaudit.verifiers.base import BaseVerifier

TIMEOUT = httpx.Timeout(15.0, connect=10.0)

# FRED series mapping for common economic indicators
FRED_SERIES_MAP: dict[str, dict[str, str]] = {
    "gdp_growth": {
        "series_id": "A191RL1Q225SBEA",
        "description": "Real GDP growth (quarterly, annualized)",
        "units": "percent",
    },
    "gdp_level": {
        "series_id": "GDP",
        "description": "Gross Domestic Product (nominal)",
        "units": "billions_usd",
    },
    "unemployment": {
        "series_id": "UNRATE",
        "description": "Unemployment Rate",
        "units": "percent",
    },
    "cpi": {
        "series_id": "CPIAUCSL",
        "description": "Consumer Price Index for All Urban Consumers",
        "units": "index_1982_84_100",
    },
    "cpi_inflation": {
        "series_id": "CPIAUCSL",
        "description": "CPI-based inflation (YoY change)",
        "units": "percent_change_yoy",
    },
    "fed_funds": {
        "series_id": "FEDFUNDS",
        "description": "Federal Funds Effective Rate",
        "units": "percent",
    },
    "oil_price_wti": {
        "series_id": "DCOILWTICO",
        "description": "Crude Oil Prices: WTI",
        "units": "usd_per_barrel",
    },
    "oil_price_brent": {
        "series_id": "DCOILBRENTEU",
        "description": "Crude Oil Prices: Brent",
        "units": "usd_per_barrel",
    },
    "10y_treasury": {
        "series_id": "DGS10",
        "description": "10-Year Treasury Constant Maturity Rate",
        "units": "percent",
    },
    "sp500": {
        "series_id": "SP500",
        "description": "S&P 500 Index",
        "units": "index",
    },
    "vix": {
        "series_id": "VIXCLS",
        "description": "CBOE Volatility Index",
        "units": "index",
    },
    "trade_balance": {
        "series_id": "BOPGSTB",
        "description": "Trade Balance: Goods and Services",
        "units": "millions_usd",
    },
    "industrial_production": {
        "series_id": "INDPRO",
        "description": "Industrial Production Index",
        "units": "index_2017_100",
    },
}

# World Bank indicator mapping
WORLD_BANK_MAP: dict[str, dict[str, str]] = {
    "gdp_growth": {"indicator": "NY.GDP.MKTP.KD.ZG", "description": "GDP growth (annual %)"},
    "gdp_current": {"indicator": "NY.GDP.MKTP.CD", "description": "GDP (current US$)"},
    "gdp_per_capita": {"indicator": "NY.GDP.PCAP.CD", "description": "GDP per capita (current US$)"},
    "inflation": {"indicator": "FP.CPI.TOTL.ZG", "description": "Inflation, CPI (annual %)"},
    "unemployment": {"indicator": "SL.UEM.TOTL.ZS", "description": "Unemployment (% of labor force)"},
    "population": {"indicator": "SP.POP.TOTL", "description": "Population, total"},
    "poverty": {"indicator": "SI.POV.DDAY", "description": "Poverty headcount ratio at $2.15/day"},
    "life_expectancy": {"indicator": "SP.DYN.LE00.IN", "description": "Life expectancy at birth"},
    "current_account": {"indicator": "BN.CAB.XOKA.GD.ZS", "description": "Current account balance (% of GDP)"},
}

# Country code mapping (common names to ISO2)
COUNTRY_CODES: dict[str, str] = {
    "us": "US", "usa": "US", "united states": "US", "america": "US",
    "uk": "GB", "united kingdom": "GB", "britain": "GB",
    "china": "CN", "japan": "JP", "germany": "DE", "france": "FR",
    "chile": "CL", "brazil": "BR", "mexico": "MX", "argentina": "AR",
    "india": "IN", "australia": "AU", "canada": "CA", "south korea": "KR",
    "italy": "IT", "spain": "ES", "netherlands": "NL", "switzerland": "CH",
    "saudi arabia": "SA", "iran": "IR", "russia": "RU", "turkey": "TR",
    "south africa": "ZA", "nigeria": "NG", "egypt": "EG", "indonesia": "ID",
    "colombia": "CO", "peru": "PE", "venezuela": "VE", "ecuador": "EC",
}


def _match_indicator(entity: str, unit: str) -> str | None:
    """Match a claim's entity/unit to a known indicator key."""
    entity_lower = entity.lower()
    unit_lower = unit.lower()

    # GDP
    if "gdp" in entity_lower:
        if "growth" in entity_lower or "%" in unit_lower or "percent" in unit_lower:
            return "gdp_growth"
        if "per capita" in entity_lower:
            return "gdp_per_capita"
        return "gdp_current"

    # Unemployment
    if "unemploy" in entity_lower:
        return "unemployment"

    # Inflation / CPI
    if "inflation" in entity_lower or "cpi" in entity_lower:
        return "inflation" if "cpi" not in entity_lower else "cpi_inflation"

    # Oil
    if "oil" in entity_lower or "crude" in entity_lower or "wti" in entity_lower:
        if "brent" in entity_lower:
            return "oil_price_brent"
        return "oil_price_wti"

    # Interest rates
    if "fed fund" in entity_lower or "federal fund" in entity_lower:
        return "fed_funds"
    if "treasury" in entity_lower or "10-year" in entity_lower or "10y" in entity_lower:
        return "10y_treasury"

    # Market indices
    if "s&p" in entity_lower or "sp500" in entity_lower or "s&p 500" in entity_lower:
        return "sp500"
    if "vix" in entity_lower or "volatility index" in entity_lower:
        return "vix"

    # Trade
    if "trade balance" in entity_lower or "trade deficit" in entity_lower:
        return "trade_balance"

    # Population
    if "population" in entity_lower:
        return "population"

    # Poverty
    if "poverty" in entity_lower:
        return "poverty"

    # Life expectancy
    if "life expectancy" in entity_lower:
        return "life_expectancy"

    # Current account
    if "current account" in entity_lower:
        return "current_account"

    return None


def _match_country(geography: str) -> str | None:
    """Match a geography string to an ISO2 country code."""
    geo_lower = geography.lower().strip()
    return COUNTRY_CODES.get(geo_lower)


def _parse_year_quarter(time_ref: str) -> tuple[str | None, str | None]:
    """Extract year and quarter from a time reference string.

    Returns (year, quarter) where quarter is None or "Q1"-"Q4".
    """
    # Match "Q3 2023", "2023 Q3", "2023Q3"
    m = re.search(r"[Qq](\d)\s*(\d{4})", time_ref)
    if m:
        return m.group(2), f"Q{m.group(1)}"
    m = re.search(r"(\d{4})\s*[Qq](\d)", time_ref)
    if m:
        return m.group(1), f"Q{m.group(2)}"

    # Match plain year
    m = re.search(r"(\d{4})", time_ref)
    if m:
        return m.group(1), None

    return None, None


class DataVerifier(BaseVerifier):
    """Verify quantitative data claims against FRED and World Bank."""

    name = "data"

    def __init__(self, fred_api_key: str | None = None):
        self.fred_api_key = fred_api_key or os.environ.get("FRED_API_KEY", "")

    def can_verify(self, claim: Claim) -> bool:
        if claim.claim_type not in (ClaimType.QUANTITATIVE, ClaimType.TEMPORAL, ClaimType.DEFINITIONAL):
            return False
        # Need at least an entity and value
        return bool(claim.entity and claim.value is not None)

    async def verify(self, claim: Claim) -> VerificationResult:
        """Verify a quantitative claim against data APIs."""
        indicator_key = _match_indicator(claim.entity, claim.unit)
        if not indicator_key:
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.UNVERIFIABLE,
                severity=Severity.INFO,
                explanation=f"Could not map entity '{claim.entity}' to a known data series",
                verified_by=self.name,
            )

        evidence = []
        country = _match_country(claim.geography) if claim.geography else None
        year, quarter = _parse_year_quarter(claim.time_reference) if claim.time_reference else (None, None)

        # Try FRED for US data (or if no country specified)
        is_us = country in ("US", None) or not claim.geography
        if is_us and indicator_key in FRED_SERIES_MAP and self.fred_api_key:
            fred_ev = await self._check_fred(claim, indicator_key, year, quarter)
            if fred_ev:
                evidence.append(fred_ev)

        # Try World Bank for international data
        if country and indicator_key in WORLD_BANK_MAP:
            wb_ev = await self._check_world_bank(claim, indicator_key, country, year)
            if wb_ev:
                evidence.append(wb_ev)

        return self._synthesize(claim, evidence)

    async def _check_fred(
        self, claim: Claim, indicator_key: str, year: str | None, quarter: str | None
    ) -> VerificationEvidence | None:
        """Check a claim against FRED."""
        series_info = FRED_SERIES_MAP[indicator_key]
        series_id = series_info["series_id"]
        url = "https://api.stlouisfed.org/fred/series/observations"
        params: dict[str, str | int] = {
            "series_id": series_id,
            "api_key": self.fred_api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 20,
        }

        if year:
            params["observation_start"] = f"{year}-01-01"
            params["observation_end"] = f"{year}-12-31"

        # For YoY percent change
        if series_info.get("units") == "percent_change_yoy" or "inflation" in indicator_key:
            params["units"] = "pc1"

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    observations = resp.json().get("observations", [])
                    if observations:
                        # Find the closest observation to the claimed time
                        obs = observations[0]  # most recent within range
                        if quarter and year:
                            # Match to specific quarter
                            quarter_months = {"Q1": ("01", "03"), "Q2": ("04", "06"),
                                              "Q3": ("07", "09"), "Q4": ("10", "12")}
                            if quarter in quarter_months:
                                start_m, end_m = quarter_months[quarter]
                                for o in observations:
                                    date = o.get("date", "")
                                    month = date[5:7] if len(date) >= 7 else ""
                                    if start_m <= month <= end_m:
                                        obs = o
                                        break

                        value = obs.get("value", ".")
                        if value != ".":
                            return VerificationEvidence(
                                source_name="FRED",
                                source_url=f"https://fred.stlouisfed.org/series/{series_id}",
                                retrieved_value=float(value),
                                retrieved_metadata={
                                    "series_id": series_id,
                                    "date": obs.get("date", ""),
                                    "description": series_info["description"],
                                },
                                match_score=1.0,
                                notes=f"FRED {series_id} on {obs.get('date', 'N/A')}: {value}",
                            )
        except Exception as e:
            return VerificationEvidence(
                source_name="FRED", match_score=0.0, notes=f"FRED lookup failed: {e}"
            )
        return None

    async def _check_world_bank(
        self, claim: Claim, indicator_key: str, country: str, year: str | None
    ) -> VerificationEvidence | None:
        """Check a claim against World Bank API."""
        wb_info = WORLD_BANK_MAP[indicator_key]
        indicator = wb_info["indicator"]
        url = f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
        params: dict[str, str | int] = {"format": "json", "per_page": 10}
        if year:
            params["date"] = year

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 1:
                        records = data[1]
                        if records:
                            # Find non-null value
                            for rec in records:
                                if rec.get("value") is not None:
                                    return VerificationEvidence(
                                        source_name="World Bank",
                                        source_url=f"https://data.worldbank.org/indicator/{indicator}?locations={country}",
                                        retrieved_value=rec["value"],
                                        retrieved_metadata={
                                            "indicator": indicator,
                                            "country": rec.get("country", {}).get("value", ""),
                                            "date": rec.get("date", ""),
                                            "description": wb_info["description"],
                                        },
                                        match_score=1.0,
                                        notes=f"World Bank {indicator} for {country} in {rec.get('date', 'N/A')}: {rec['value']}",
                                    )
        except Exception as e:
            return VerificationEvidence(
                source_name="World Bank", match_score=0.0, notes=f"World Bank lookup failed: {e}"
            )
        return None

    def _synthesize(
        self, claim: Claim, evidence: list[VerificationEvidence]
    ) -> VerificationResult:
        """Compare claimed value against retrieved data."""
        if not evidence:
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.UNVERIFIABLE,
                severity=Severity.INFO,
                explanation="No data source returned results for this claim",
                verified_by=self.name,
            )

        # Use best evidence source
        best = max(evidence, key=lambda e: e.match_score)
        if best.retrieved_value is None or best.match_score == 0.0:
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.UNVERIFIABLE,
                severity=Severity.INFO,
                evidence=evidence,
                explanation=f"Data source returned no value: {best.notes}",
                verified_by=self.name,
            )

        claimed = claim.value
        actual = best.retrieved_value

        # Compare values
        try:
            claimed_f = float(str(claimed))
            actual_f = float(actual)
        except (ValueError, TypeError):
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.UNVERIFIABLE,
                severity=Severity.INFO,
                evidence=evidence,
                explanation=f"Cannot compare: claimed={claimed}, retrieved={actual}",
                verified_by=self.name,
            )

        # Compute relative error
        if actual_f != 0:
            rel_error = abs(claimed_f - actual_f) / abs(actual_f)
        else:
            rel_error = abs(claimed_f - actual_f)

        if rel_error < 0.01:  # <1% error
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.VERIFIED,
                severity=Severity.INFO,
                evidence=evidence,
                explanation=(
                    f"Claimed {claimed} matches {best.source_name} value {actual_f:.4g} "
                    f"(error: {rel_error:.1%})"
                ),
                verified_by=self.name,
            )
        elif rel_error < 0.05:  # 1-5% error
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.IMPRECISE,
                severity=Severity.MINOR,
                evidence=evidence,
                explanation=(
                    f"Claimed {claimed} is close to {best.source_name} value {actual_f:.4g} "
                    f"but imprecise (error: {rel_error:.1%})"
                ),
                suggested_correction=f"{actual_f:.4g}",
                verified_by=self.name,
            )
        elif rel_error < 0.20:  # 5-20% error
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.IMPRECISE,
                severity=Severity.MAJOR,
                evidence=evidence,
                explanation=(
                    f"Claimed {claimed} differs significantly from {best.source_name} "
                    f"value {actual_f:.4g} (error: {rel_error:.1%})"
                ),
                suggested_correction=f"{actual_f:.4g}",
                verified_by=self.name,
            )
        else:  # >20% error
            return VerificationResult(
                claim=claim,
                status=VerificationStatus.INCORRECT,
                severity=Severity.CRITICAL,
                evidence=evidence,
                explanation=(
                    f"Claimed {claimed} is WRONG. {best.source_name} reports {actual_f:.4g} "
                    f"(error: {rel_error:.1%})"
                ),
                suggested_correction=f"{actual_f:.4g}",
                verified_by=self.name,
            )
