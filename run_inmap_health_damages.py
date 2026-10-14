"""
Run InMAP (ISRM) for all years, scenarios, and vehicle types, then compute health damages.

This script replaces the NOx-scaling approach with direct InMAP ISRM runs for each
calendar year (2019-2045), scenario, and vehicle type. It uses the local ISRM matrix
via sr_util.run_sr() — the same interface used for previous InMAP runs.

Pipeline:
  1. Load county VMT fractions to spatially distribute emissions
  2. For each (scenario, year, vehicle_type):
     a. Build county-level emission GeoDataFrame from model CSV
     b. Run InMAP ISRM via run_sr() to get PM2.5 concentrations and deaths
     c. Save results
  3. Aggregate yearly mortality across scenarios

Setup:
  - sr_util.py and the ISRM .ncf file must be accessible (added to sys.path below)
  - Model CSVs must exist in model_dir (e.g., 'Feb 17 2025/model_BAU.csv')

Usage from notebook:
    %run run_inmap_health_damages.py

  Or import and call:
    from run_inmap_health_damages import run_all
    run_all()
"""

import gc
import os
import sys
import time
import numpy as np
import pandas as pd
import geopandas as gpd

# ---------------------------------------------------------------------------
# Paths — adjust these to your local setup
# ---------------------------------------------------------------------------

# Base directory: Stock-and-Flow-main/ (parent of fleetturnover/)
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

# Where sr_util.py and the ISRM .ncf live
ISRM_DIR = os.path.expanduser(
    '~/Library/CloudStorage/GoogleDrive-madalsa@stanford.edu/'
    'My Drive/BoxMigration/ISRM '
)

# Model output CSVs
MODEL_DIR = os.path.join(BASE, 'Feb 17 2025')

# County data for spatial distribution
COUNTY_VMT_PATH = os.path.join(BASE, 'EMFAC 2020-Countywide.csv')
COUNTY_SHP_PATH = os.path.join(BASE,
    'nhgis0019_shapefile_tl2020_us_county_2020', 'US_county_2020.shp')

# Output directories
OUTPUT_DIR = os.path.join(BASE, 'inmap_results')
MORTALITY_DIR = os.path.join(BASE, 'health_damages_output')

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCENARIOS = (
    'BAU',
    '2040', '2035',
    '2100-10-2040', '2100-10-2035', '2100-10-2030',
    '2100-15-2040', '2100-15-2035', '2100-15-2030',
    '2040-10-2040', '2040-10-2035', '2040-10-2030',
    '2035-15-2040', '2035-15-2035', '2035-15-2030',
)

VEH_TYPES = ['PC', 'LDT1', 'LDT2', 'T3']

VEH_TO_EMFAC = {
    'PC':   'LDA',
    'LDT1': 'LDT1',
    'LDT2': 'LDT2',
    'T3':   'MDV',
}

YEARS = range(2019, 2046)

# Columns in model CSV → shapefile column names
POLLUTANT_MAP = {
    'nox_emissions': 'NOx',
    'pm_emissions':  'PM2_5',
    'sox_emissions': 'SOx',
    'nh3_emisisons': 'NH3',
}

# InMAP output variables (same as your existing InMAP notebook)
OUTPUT_VARIABLES = {
    'TotalPM25': 'PrimaryPM25 + pNH4 + pSO4 + pNO3 + SOA',
    'deathsK': ('(exp(log(1.06)/10 * TotalPM25) - 1) * TotalPop * '
                '1.0465819687408728 * MortalityRate / 100000 * 1.025229357798165'),
    'Pop': 'TotalPop',
    'Mortality': 'MortalityRate',
    'Blackpop': 'Black',
    'Asianpop': 'Asian',
    'Latinopop': 'Latino',
    'Nativepop': 'Native',
    'WhiteNoLa': 'WhiteNoLat',
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def load_county_vmt_fractions():
    """Load county-level VMT fractions for distributing statewide emissions."""
    county_vmt = pd.read_csv(COUNTY_VMT_PATH)
    county_vmt['NAME'] = county_vmt['Region']
    county_vmt = county_vmt.groupby(
        ['Calendar Year', 'NAME', 'Vehicle Category']
    ).sum(numeric_only=True).reset_index()
    county_vmt_pivot = pd.pivot(
        county_vmt, index='NAME', columns='Vehicle Category', values='Total VMT'
    )

    for veh, emfac_cat in VEH_TO_EMFAC.items():
        col = f'{veh.lower()}_vmt_fraction'
        county_vmt_pivot[col] = (
            county_vmt_pivot[emfac_cat] / county_vmt_pivot[emfac_cat].sum()
        )

    county_shape = gpd.read_file(COUNTY_SHP_PATH)
    ca_county = pd.merge(county_shape, county_vmt_pivot, on='NAME', how='inner')
    ca_county = ca_county[ca_county['STATEFP'] == '06']
    return ca_county


def build_emissions_gdf(model_df, year, veh, ca_county):
    """Build a county-level emissions GeoDataFrame for one (year, veh_type)."""
    df_yv = model_df[(model_df['year'] == year) & (model_df['veh_type'] == veh)]
    if len(df_yv) == 0:
        return None

    vmt_frac_col = f'{veh.lower()}_vmt_fraction'
    gdf = gpd.GeoDataFrame(
        {'geometry': ca_county['geometry'].values},
        crs=ca_county.crs,
    )

    for model_col, shp_col in POLLUTANT_MAP.items():
        total = df_yv[model_col].sum() if model_col in df_yv.columns else 0.0
        gdf[shp_col] = total * ca_county[vmt_frac_col].values

    return gdf


def scenario_to_filename(scenario):
    return scenario.replace("-", "_")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_all():
    """Run InMAP ISRM for all scenarios, years, and vehicle types."""

    # Import the fixed sr_util from this repo (not the ISRM directory)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    from sr_util import run_sr

    # Change working directory to ISRM dir so inmap finds isrm_v1.2.1.ncf
    original_cwd = os.getcwd()
    os.chdir(ISRM_DIR)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(MORTALITY_DIR, exist_ok=True)

    print("Loading county VMT fractions...")
    ca_county = load_county_vmt_fractions()

    total_runs = len(SCENARIOS) * len(list(YEARS)) * len(VEH_TYPES)
    completed = 0
    failed = 0

    for scenario in SCENARIOS:
        fname = scenario_to_filename(scenario)
        model_path = os.path.join(MODEL_DIR, f'model_{fname}.csv')

        if not os.path.exists(model_path):
            print(f"  WARNING: {model_path} not found, skipping {scenario}")
            completed += len(list(YEARS)) * len(VEH_TYPES)
            continue

        print(f"\n{'='*60}")
        print(f"Scenario: {scenario}")
        print(f"{'='*60}")
        model_df = pd.read_csv(model_path)

        scenario_out_dir = os.path.join(OUTPUT_DIR, fname)
        os.makedirs(scenario_out_dir, exist_ok=True)

        yearly_records = []

        for year in YEARS:
            for veh in VEH_TYPES:
                completed += 1
                out_shp = os.path.join(scenario_out_dir, f'{veh}_{year}.shp')

                # Skip if already computed
                if os.path.exists(out_shp):
                    # Load existing results for mortality aggregation
                    result = gpd.read_file(out_shp)
                    yearly_records.append({
                        'year': year,
                        'veh_type': veh,
                        'K deaths': result['deathsK'].sum() if 'deathsK' in result.columns else 0,
                        'TotalPM25_max': result['TotalPM25'].max() if 'TotalPM25' in result.columns else 0,
                    })
                    continue

                # Build emissions GeoDataFrame
                emis_gdf = build_emissions_gdf(model_df, year, veh, ca_county)
                if emis_gdf is None:
                    continue

                # Skip if all emissions are zero (e.g., electricity-only fleet)
                if emis_gdf[['NOx', 'PM2_5', 'SOx', 'NH3']].sum().sum() < 1e-10:
                    yearly_records.append({
                        'year': year, 'veh_type': veh,
                        'K deaths': 0, 'TotalPM25_max': 0,
                    })
                    continue

                print(f"  [{completed}/{total_runs}] {veh} {year}...", end=' ')
                start = time.time()

                try:
                    result = run_sr(
                        emis_gdf,
                        model="isrm",
                        emis_units="tons/year",
                        output_variables=OUTPUT_VARIABLES,
                    )
                    result.to_file(out_shp)
                    deaths = result['deathsK'].sum()
                    elapsed = time.time() - start
                    print(f"deaths={deaths:.1f}  ({elapsed:.0f}s)")

                    yearly_records.append({
                        'year': year,
                        'veh_type': veh,
                        'K deaths': deaths,
                        'TotalPM25_max': result['TotalPM25'].max(),
                    })

                except Exception as e:
                    failed += 1
                    print(f"FAILED: {e}")

                finally:
                    # Free memory — each inmap srpredict loads the full ISRM
                    del emis_gdf
                    if 'result' in dir():
                        del result
                    gc.collect()

        # Save yearly mortality CSV for this scenario
        if yearly_records:
            mort_df = pd.DataFrame(yearly_records)
            mort_path = os.path.join(
                MORTALITY_DIR,
                f'model_yearly_mortality_{fname}_inmap.csv'
            )
            mort_df.to_csv(mort_path, index=False)
            print(f"\n  Saved: {mort_path}")
            cum_deaths = mort_df[mort_df['year'] > 2024]['K deaths'].sum()
            print(f"  Cumulative deaths (2025-2045): {cum_deaths:.1f}")

    # Restore working directory
    os.chdir(original_cwd)

    print(f"\n{'='*60}")
    print(f"Complete: {completed} runs, {failed} failures")
    print(f"Results in: {OUTPUT_DIR}")
    print(f"Mortality CSVs in: {MORTALITY_DIR}")
    print(f"{'='*60}")


if __name__ == '__main__':
    run_all()
