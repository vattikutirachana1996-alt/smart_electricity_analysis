import pandas as pd

file = "cea_monthly_energy_jul_aug_2026.csv"
df = pd.read_csv(file)

print("Total rows:", len(df))
print("Columns:", df.columns.tolist())
print("\nRows per month:")
print(df.groupby("period_month").size())
print("\nDate range:")
print(df["period_month"].min(), "to", df["period_month"].max())