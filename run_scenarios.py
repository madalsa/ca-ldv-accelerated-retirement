"""
Run the fleet turnover and retirement scenarios.

Extracted from LDV_Scenarios CARB BAU.ipynb (cells 1-4). Writes one CSV per
scenario to OUTPUT_DIR, named model_<zevtargetyear>_<retirementage>_<retirementyear>.csv,
plus model_BAU.csv and model_2040.csv. These are the inputs to
run_inmap_health_damages.py.

Usage:  python run_scenarios.py
"""

from stock_flow import *
import os
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# --- shared settings (as in the notebook) ---
start_year = 2019
end_year = 2045
veh_types = ["PC", "LDT1", "LDT2", "T3"]
fuel_types = ["Diesel", "Gasoline", "Natural Gas", "Electricity", "Hydrogen", "Hybrid"]
input_file = "Inputs_CARB.xlsx"
vmt_mode = "prof"
stock_prof = True

OUTPUT_DIR = 'Feb 17 2025'
os.makedirs(OUTPUT_DIR, exist_ok=True)


def by_veh(value):
    """Same value for every vehicle type."""
    return {v: value for v in veh_types}


def retirement_profile_for(ret_age, ret_year):
    ret_profile = {}
    ret_profile["ret_age"] = ret_age
    ret_profile["ret_year"] = ret_year
    ret_profile["phase_in"] = 0
    return by_veh(ret_profile)


# =========================== 1. Business as usual ===========================
# (notebook cells 1-2)
model_BAU = stock_and_flow_baseline(start_year, end_year, veh_types, fuel_types,
                                    input_file, vmt_mode)
model_BAU.to_csv(os.path.join(OUTPUT_DIR, 'model_BAU.csv'))
print('wrote model_BAU.csv')


# ====================== 2. 2040 ZEV mandate, no retirement ==================
# (notebook cell 3)
target_year = by_veh(2040)
frac_elec = by_veh(1)
retirement_profile = retirement_profile_for(1100, 2100)   # no retirement
retirement_mode = by_veh(["uniform"])

model_2040 = stock_and_flow_sales_ret(start_year, end_year, veh_types, fuel_types,
                                      input_file, stock_prof, vmt_mode, target_year,
                                      frac_elec, [retirement_profile],
                                      retirement_mode, sales_mode="linear",
                                      replacement_mode="ZEV_only")
model_2040.to_csv(os.path.join(OUTPUT_DIR, 'model_2040.csv'))
print('wrote model_2040.csv')


# ================= 3. Retirement x ZEV mandate scenario grid ================
# (notebook cell 4).  zevtargetyear 2100 = no ZEV mandate.
retirementyear = [2030, 2035, 2040]
retirementages = [10, 15, 20]
zevtargetyear = [2030, 2035, 2040, 2100]

for i in retirementyear:
    for j in retirementages:
        for k in zevtargetyear:
            target_year = by_veh(k)
            frac_elec = by_veh(1)
            retirement_profile = retirement_profile_for(j, i)
            retirement_mode = by_veh(["uniform"])

            model = stock_and_flow_sales_ret(start_year, end_year, veh_types,
                                             fuel_types, input_file, stock_prof,
                                             vmt_mode, target_year, frac_elec,
                                             [retirement_profile], retirement_mode,
                                             sales_mode="linear",
                                             replacement_mode="ZEV_only")
            name = f'model_{k}_{j}_{i}.csv'
            model.to_csv(os.path.join(OUTPUT_DIR, name))
            print('wrote', name)
