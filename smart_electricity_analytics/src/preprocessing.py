"""Cleaning of uploaded CEA tables into the canonical monthly state-level schema."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from .config import ENERGY_TO_MU, POWER_TO_MW

# Canonical state/UT names -> region (CEA-style regional grouping; islands are stand-alone systems)
STATE_REGION = {
    "Chandigarh": "Northern", "Delhi": "Northern", "Haryana": "Northern",
    "Himachal Pradesh": "Northern", "Jammu & Kashmir": "Northern", "Ladakh": "Northern",
    "Punjab": "Northern", "Rajasthan": "Northern", "Uttar Pradesh": "Northern",
    "Uttarakhand": "Northern",
    "Chhattisgarh": "Western", "Goa": "Western", "Gujarat": "Western",
    "Madhya Pradesh": "Western", "Maharashtra": "Western",
    "Dadra & Nagar Haveli": "Western", "Daman & Diu": "Western",
    "Dadra & Nagar Haveli and Daman & Diu": "Western",
    "Andhra Pradesh": "Southern", "Karnataka": "Southern", "Kerala": "Southern",
    "Puducherry": "Southern", "Tamil Nadu": "Southern", "Telangana": "Southern",
    "Bihar": "Eastern", "Jharkhand": "Eastern", "Odisha": "Eastern",
    "Sikkim": "Eastern", "West Bengal": "Eastern",
    "Arunachal Pradesh": "North-Eastern", "Assam": "North-Eastern", "Manipur": "North-Eastern",
    "Meghalaya": "North-Eastern", "Mizoram": "North-Eastern", "Nagaland": "North-Eastern",
    "Tripura": "North-Eastern",
    "Andaman & Nicobar Islands": "Islands", "Lakshadweep": "Islands",
}
_ALIASES = {
    "jammu and kashmir": "Jammu & Kashmir", "j k": "Jammu & Kashmir", "jk": "Jammu & Kashmir",
    "orissa": "Odisha", "uttaranchal": "Uttarakhand", "pondicherry": "Puducherry",
    "nct of delhi": "Delhi", "new delhi": "Delhi", "a n islands": "Andaman & Nicobar Islands",
    "andaman and nicobar": "Andaman & Nicobar Islands", "a and n islands": "Andaman & Nicobar Islands",
    "dnh": "Dadra & Nagar Haveli", "dd": "Daman & Diu", "daman and diu": "Daman & Diu",
    "dadra and nagar haveli": "Dadra & Nagar Haveli", "dnhdd": "Dadra & Nagar Haveli and Daman & Diu",
    "dadra and nagar haveli and daman and diu": "Dadra & Nagar Haveli and Daman & Diu",
    "chhatisgarh": "Chhattisgarh", "chattisgarh": "Chhattisgarh", "tamilnadu": "Tamil Nadu",
}
# Rows that are aggregates (regions / country totals). Importing them next to states would double count.
_AGGREGATE_KEYS = {
    "all india", "india", "total", "grand total", "northern", "western", "southern", "eastern",
    "north eastern", "northeastern", "northern region", "western region", "southern region",
    "eastern region", "north eastern region", "nr", "wr", "sr", "er", "ner", "central sector",
}


def _key(name) -> str:
    s = str(name).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_CANON = {_key(k): k for k in STATE_REGION}
_CANON.update({_key(a): c for a, c in _ALIASES.items()})


def is_aggregate(name) -> bool:
    k = _key(name)
    return k in _AGGREGATE_KEYS or k.startswith("total ") or k.endswith(" region")


def standardize_states(raw: pd.Series) -> pd.DataFrame:
    """Return a mapping table raw -> standard name with status (ok / aggregate / unknown)."""
    rows = []
    for r in pd.unique(raw.dropna().astype(str).str.strip()):
        if is_aggregate(r):
            rows.append((r, None, "aggregate"))
        elif _key(r) in _CANON:
            rows.append((r, _CANON[_key(r)], "ok"))
        else:
            rows.append((r, None, "unknown"))
    return pd.DataFrame(rows, columns=["raw_name", "standard_name", "status"])


def parse_month(series: pd.Series) -> pd.Series:
    """Parse to the first day of the month. Unparseable values become NaT (reported, not dropped silently).

    ISO dates (2022-04-01, 2022-04) are read unambiguously first. Everything else (01/04/2022, Apr-2022,
    April 2022) is read day-first, the Indian convention. Real Excel dates pass through unchanged.
    """
    iso = pd.to_datetime(series, errors="coerce", format="ISO8601")
    rest = iso.isna() & series.notna()
    if rest.any():
        fallback = pd.to_datetime(series.where(rest), errors="coerce", format="mixed", dayfirst=True)
        iso = iso.fillna(fallback)
    return iso.dt.to_period("M").dt.to_timestamp()


def to_number(series: pd.Series) -> pd.Series:
    cleaned = series.astype(str).str.replace(",", "", regex=False).str.strip()
    cleaned = cleaned.replace({"": np.nan, "nan": np.nan, "None": np.nan, "-": np.nan, "NA": np.nan})
    return pd.to_numeric(cleaned, errors="coerce")


@dataclass
class CleanResult:
    data: pd.DataFrame
    issues: list = field(default_factory=list)       # dicts: level, message
    state_map: pd.DataFrame = None
    excluded: pd.DataFrame = None                    # rows NOT imported, with reason

    @property
    def has_errors(self) -> bool:
        return any(i["level"] == "error" for i in self.issues)


def build_clean(df: pd.DataFrame, mapping: dict, energy_unit: str = "MU", power_unit: str = "MW") -> CleanResult:
    """mapping: canonical field -> source column (or None). Fields: state, period and metric names."""
    issues, excluded_parts = [], []

    def add(level, msg):
        issues.append({"level": level, "message": msg})

    if energy_unit not in ENERGY_TO_MU or power_unit not in POWER_TO_MW:
        add("error", "Unknown unit selected.")
        return CleanResult(pd.DataFrame(), issues)
    for req in ("state", "period"):
        if not mapping.get(req):
            add("error", f"Required field '{req}' is not mapped.")
    metric_fields = [f for f in ("energy_requirement_mu", "energy_availability_mu", "peak_demand_mw", "peak_met_mw")
                     if mapping.get(f)]
    if not metric_fields:
        add("error", "Map at least one metric column.")
    if issues:
        return CleanResult(pd.DataFrame(), issues)

    work = pd.DataFrame({"row_in_file": np.arange(2, len(df) + 2)})  # +2: header line + 1-based
    work["raw_state"] = df[mapping["state"]].astype(str).str.strip().values
    work["period"] = parse_month(df[mapping["period"]]).values
    for f in metric_fields:
        raw = df[mapping[f]]
        num = to_number(raw)
        bad = int((raw.notna() & num.isna() & (raw.astype(str).str.strip().replace({"-": "", "NA": ""}) != "")).sum())
        if bad:
            add("warning", f"{bad} non-numeric value(s) in '{mapping[f]}' were set to missing (NULL).")
        factor = ENERGY_TO_MU[energy_unit] if f.endswith("_mu") else POWER_TO_MW[power_unit]
        work[f] = (num * factor).round(4).values
    if energy_unit != "MU" and any(f.endswith("_mu") for f in metric_fields):
        add("info", f"Energy values converted from {energy_unit} to MU (x{ENERGY_TO_MU[energy_unit]}).")
    if power_unit != "MW" and any(f.endswith("_mw") for f in metric_fields):
        add("info", f"Power values converted from {power_unit} to MW (x{POWER_TO_MW[power_unit]}).")

    smap = standardize_states(work["raw_state"])
    work = work.merge(smap.rename(columns={"raw_name": "raw_state"}), on="raw_state", how="left")

    nat = work["period"].isna()
    if nat.any():
        add("warning", f"{int(nat.sum())} row(s) have an unreadable date and were excluded (see excluded rows).")
        excluded_parts.append(work[nat].assign(reason="Unreadable date"))
    agg = work["status"].eq("aggregate")
    if agg.any():
        add("info", f"{int(agg.sum())} aggregate row(s) (region/All-India totals) excluded to avoid double counting.")
        excluded_parts.append(work[agg & ~nat].assign(reason="Aggregate row"))
    unk = work["status"].eq("unknown")
    if unk.any():
        add("warning", f"{int(unk.sum())} row(s) have unrecognised state names ({', '.join(sorted(work.loc[unk,'raw_state'].unique())[:8])}). "
                       "They are excluded until you fix the file.")
        excluded_parts.append(work[unk & ~nat].assign(reason="Unrecognised state name"))
    ok = work[work["status"].eq("ok") & ~nat].copy()
    ok["state"] = ok["standard_name"]
    ok["region"] = ok["state"].map(STATE_REGION)
    keep = ["row_in_file", "state", "region", "period"] + metric_fields
    excluded = pd.concat(excluded_parts, ignore_index=True) if excluded_parts else pd.DataFrame(
        columns=["row_in_file", "raw_state", "period", "reason"])
    return CleanResult(ok[keep].reset_index(drop=True), issues, smap, excluded)


def guess_mapping(columns) -> dict:
    """Guess common CEA upload columns, including names with underscores or unit suffixes."""
    hints = {
        "state": ["state", "ut", "state or system", "name"],
        "period": ["month", "date", "period", "financial year"],
        "energy_requirement_mu": ["energy requirement", "requirement", "required", "energy req"],
        "energy_availability_mu": ["energy availability", "energy supplied", "availability", "available", "energy avail"],
        "peak_demand_mw": ["peak demand", "peak dem"],
        "peak_met_mw": ["peak met", "demand met"],
    }

    def normalise(value):
        value = re.sub(r"[_-]+", " ", str(value).lower())
        return re.sub(r"\s+", " ", value).strip()

    normalised = [(column, normalise(column)) for column in columns]
    out = {}
    for field, field_hints in hints.items():
        matches = []
        for hint in field_hints:
            h = normalise(hint)
            matches.extend(column for column, name in normalised if h in name)
        # Avoid mapping the same source column to multiple metrics.
        out[field] = next((c for c in matches if c not in out.values()), None)
    return out
