# Accelerated vehicle retirement and clean vehicle mandates in California

Model code and data for *"Accelerated vehicle retirement combined with clean vehicle
mandates contribute significantly to health and climate benefits in California"*
(Singh, Hennessy, Saltzer, Berson and Azevedo).

## Contents

| File | Description |
|---|---|
| `stock_flow.py` | Fleet turnover and retirement model |
| `Inputs_CARB.xlsx` | Model inputs: vehicle vintages, survival profiles, sales, VMT degradation, fuel economy and emission factors, derived from CARB EMFAC2021 |
| `run_scenarios.py` | Runs the business-as-usual, ZEV mandate and accelerated retirement scenarios; writes one CSV per scenario |
| `run_inmap_health_damages.py` | Builds county-level emissions inputs from the scenario outputs and runs the InMAP source-receptor matrix to obtain PM2.5 concentrations and premature mortality |
| `sr_util.py` | Helper that calls the InMAP ISRM (required by `run_inmap_health_damages.py`) |
| `annual_streams.csv` | Source data for the figures: annual premature mortality, CO2 emissions and policy-driven retirement counts for each of the fifteen scenarios, 2025–2045, under declining and constant grid assumptions |

## Reproducing the results

```
python run_scenarios.py              # scenario outputs
python run_inmap_health_damages.py   # InMAP runs -> concentrations and mortality
```

`run_inmap_health_damages.py` requires the InMAP Source-Receptor Matrix
(version 1.2.1, https://doi.org/10.5281/zenodo.2589760), which is not
redistributed here.

## Data sources

- Vehicle stock, activity, fuel economy and emission factors: CARB EMFAC2021,
  https://arb.ca.gov/emfac/
- PM2.5 concentrations: InMAP, https://inmap.run/
