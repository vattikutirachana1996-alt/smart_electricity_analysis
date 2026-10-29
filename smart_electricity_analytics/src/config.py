"""Central constants: paths, unit conversion factors, canonical column names."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"

# 1 MU (million units) = 1 GWh = 1,000 MWh = 1,000,000 kWh
ENERGY_TO_MU = {"MU": 1.0, "GWh": 1.0, "TWh": 1000.0, "MWh": 0.001, "kWh": 1e-6}
# power (instantaneous demand) is a different physical quantity from energy
POWER_TO_MW = {"MW": 1.0, "GW": 1000.0, "kW": 0.001}

METRICS = {
    "energy_requirement_mu": "Energy requirement (MU)",
    "energy_availability_mu": "Energy availability (MU)",
    "peak_demand_mw": "Peak demand (MW)",
    "peak_met_mw": "Peak demand met (MW)",
}
ENERGY_METRICS = ["energy_requirement_mu", "energy_availability_mu"]
POWER_METRICS = ["peak_demand_mw", "peak_met_mw"]

AVAILABILITY_NOTE = (
    "CEA defines energy availability as the energy actually supplied, which it describes "
    "as net consumption including transmission losses. It is NOT metered end-consumer "
    "consumption, so this app uses it as a labelled proxy."
)
