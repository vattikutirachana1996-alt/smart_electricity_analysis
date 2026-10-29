import pandas as pd

file = "cea_monthly_energy_jul_aug_2026.csv"
df = pd.read_csv(file)

df["period_month"] = pd.to_datetime(
    df["period_month"], errors="coerce"
).dt.to_period("M").dt.to_timestamp()

print("Unique months:")
print(df["period_month"].dt.strftime("%Y-%m").unique())

print("\nRows per month:")
print(df.groupby("period_month").size())

print("\nDate range:")
print(df["period_month"].min(), "to", df["period_month"].max())

print("\nTotal rows:", len(df))
