#!/usr/bin/env python

"""
For each of the OzFlux/FLUXNET2015 sites, figure out the TXx and save the
Qle and bowen ratio for that day and the previous 4 days.

That's all folks.
"""

__author__ = "Martin De Kauwe"
__version__ = "1.0 (20.04.2017)"
__email__ = "mdekauwe@gmail.com"

import os
import sys
import glob
import netCDF4 as nc
import numpy as np
import xarray as xr
import pandas as pd

import constants as c

def main(flux_dir, cable_dir, ofname, oz_flux=True):

    if oz_flux:
        flux_files = sorted(glob.glob(os.path.join(flux_dir, "*_flux.nc")))
        met_files = sorted(glob.glob(os.path.join(flux_dir, "*_met.nc")))
        cable_files = sorted(glob.glob(os.path.join(cable_dir, "*_out.nc")))
    else:
        flux_files = sorted(glob.glob(os.path.join(flux_dir, "*_Flux.nc")))
        met_files = sorted(glob.glob(os.path.join(flux_dir, "*_Met.nc")))
        cable_files = sorted(glob.glob(os.path.join(cable_dir, "*_out.nc")))

    output_dir = "outputs"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    if oz_flux:
        d = get_ozflux_pfts()

    cols = ['site','pft','temp','Qle','B','GPP']
    df = pd.DataFrame(columns=cols)
    for cable_fn, flux_fn, met_fn in zip(cable_files, flux_files, met_files):
        (site, df_mod,
         df_flx, df_met) = open_file(cable_fn, flux_fn, met_fn, oz_flux=oz_flux)


        if d[site] == "EBF" or d[site] == "SAV" or d[site] == "TRF":
            print(site, np.unique(df_met.index.year))
            # daylight hours
            df_flx = df_flx.between_time("06:00", "20:00")
            df_met = df_met.between_time("06:00", "20:00")
            df_mod = df_mod.between_time("06:00", "20:00")

            (df_mod, df_flx, df_met) = mask_crap_days(df_mod, df_flx, df_met)
            df_met.Tair -= c.DEG_2_KELVIN

            (Tairs, Qles, B, GPPs) = get_all_events(df_mod, df_met)

            if oz_flux:
                pft = d[site]

            lst = []
            for i in range(len(Tairs)):
                lst.append([site,d[site],Tairs[i],Qles[i],B[i],GPPs[i]])
            dfx = pd.DataFrame(lst, columns=cols)
            dfx = dfx.reindex(index=dfx.index[::-1]) # reverse the order hot to cool
            df = df.append(dfx)

    df.to_csv(os.path.join(output_dir, ofname), index=False)



def get_all_events(df_flx, df_met):

    # We need to figure out if it rained during our hot extreme as this
    # would change the Qle in the way we're searching for!
    diff = df_flx.index.minute[1] - df_flx.index.minute[0]
    # Change GPP units
    if diff == 0:
        # hour gap i.e. Tumba
        df_flx["GPP"] *= 12. * 0.000001 * 3600.0
    else:
        # 30 min gap
        df_flx["GPP"] *= 12. * 0.000001 * 1800.0


    df_dm = df_met.resample("D").max()
    df_ds = df_met.resample("D").sum()
    df_df = df_flx.resample("D").mean()
    df_dfs = df_flx.resample("D").sum()

    # We need to figure out if it rained during our hot extreme as this
    # would change the Qle in the way we're searching for!
    diff = df_met.index.minute[1] - df_met.index.minute[0]
    if diff == 0:
        # hour gap i.e. Tumba
        rain = df_met.Rainf * 3600.0
    else:
        # 30 min gap
        rain = df_met.Rainf * 1800.0
    rain = rain.fillna(0.0)
    rain = rain.resample("D").sum()

    #
    ## Get the TXx event
    #
    TXx = df_dm.sort_values("Tair", ascending=False)[:1].Tair.values[0]
    TXx_idx = df_dm.sort_values("Tair", ascending=False)[:1].index.values[0]
    TXx_idx_minus_four = TXx_idx - pd.Timedelta(3, unit='d')

    (Tairs, Qles,
     Qhs, B, GPP) = get_values(df_dm, df_df, df_dfs, TXx_idx, TXx_idx_minus_four)

    (Tairs, Qles, B, GPP,
     df_dm, df_df) = is_event_long_enough(df_dm, df_df, df_dfs, TXx_idx,
                                           TXx_idx_minus_four, Tairs, Qles, B,
                                           GPP, rain)

    if len(Tairs) < 4:
        Tairs = np.array([np.nan,np.nan,np.nan,np.nan])
        Qles = np.array([np.nan,np.nan,np.nan,np.nan])
        B = np.array([np.nan,np.nan,np.nan,np.nan])


    #
    ## Get all the events other than the TXx that are > Tthresh
    #

    # Drop the hottest event as we've already got it
    df_dm = df_dm[(df_dm.index < TXx_idx_minus_four) |
                   (df_dm.index > TXx_idx)]
    df_df = df_df[(df_df.index < TXx_idx_minus_four) |
                   (df_df.index > TXx_idx)]
    # Then get next TXx
    TXx = df_dm.sort_values("Tair", ascending=False)[:1].Tair.values[0]

    while TXx > 37.0:

        # Then get next TXx
        TXx = df_dm.sort_values("Tair", ascending=False)[:1].Tair.values[0]
        TXx_idx = df_dm.sort_values("Tair", ascending=False)[:1].index.values[0]
        TXx_idx_minus_four= TXx_idx - pd.Timedelta(3, unit='d')

        (Tairsx, Qlesx,
         Qhsx, Bx, GPPx) = get_values(df_dm, df_df, df_dfs, TXx_idx, TXx_idx_minus_four)

        (Tairsx, Qlesx,
         Bx, GPPx, df_dm, df_df) = is_event_long_enough(df_dm, df_df, df_dfs, TXx_idx,
                                                  TXx_idx_minus_four,
                                                  Tairsx, Qlesx, Bx, GPPx, rain)

        Tairsx = Tairsx[~np.isnan(Tairsx)]
        Qlesx = Qlesx[~np.isnan(Qlesx)]
        Bx = Bx[~np.isnan(Bx)]
        GPPx = GPPx[~np.isnan(GPPx)]

        if len(Tairsx) == 4:
            Tairs = np.append(Tairs, Tairsx)
            Qles = np.append(Qles, Qlesx)
            B = np.append(B, Bx)
            GPP = np.append(GPP, GPPx)

        # Drop this event
        df_dm = df_dm[(df_dm.index < TXx_idx_minus_four) |
                       (df_dm.index > TXx_idx)]
        df_df = df_df[(df_df.index < TXx_idx_minus_four) |
                       (df_df.index > TXx_idx)]
        # Then get next TXx
        TXx = df_dm.sort_values("Tair",
                                ascending=False)[:1].Tair.values[0]

    Tairs = Tairs[~np.isnan(Tairs)]
    Qles = Qles[~np.isnan(Qles)]
    B = B[~np.isnan(B)]
    GPP = GPP[~np.isnan(GPP)]

    if len(Tairs) < 4:
        Tairs = np.array([np.nan,np.nan,np.nan,np.nan])
        Qles = np.array([np.nan,np.nan,np.nan,np.nan])
        B = np.array([np.nan,np.nan,np.nan,np.nan])
        GPP = np.array([np.nan,np.nan,np.nan,np.nan])

    return(Tairs, Qles, B, GPP)

def get_values(df_dm, df_df, df_dfs, TXx_idx, TXx_idx_minus_four):

    Tairs = df_dm[(df_dm.index >= TXx_idx_minus_four) &
                  (df_dm.index <= TXx_idx)].Tair.values
    Qles = df_df[(df_dm.index >= TXx_idx_minus_four) &
                 (df_dm.index <= TXx_idx)].Qle.values
    Qhs = df_df[(df_dm.index >= TXx_idx_minus_four) &
                (df_dm.index <= TXx_idx)].Qh.values
    B = Qhs / Qles
    GPPs = df_dfs[(df_dfs.index >= TXx_idx_minus_four) &
                  (df_dfs.index <= TXx_idx)].GPP.values

    return (Tairs, Qles, Qhs, B, GPPs)

def is_event_long_enough(df_dm, df_df, df_dfs, TXx_idx, TXx_idx_minus_four,
                         Tairs, Qles, B, GPPs, rain):

    while len(Tairs) != 4:

        # Drop this event as it wasn't long enough
        df_dm = df_dm[(df_dm.index < TXx_idx_minus_four) |
                       (df_dm.index > TXx_idx)]
        df_df = df_df[(df_df.index < TXx_idx_minus_four) |
                       (df_df.index > TXx_idx)]

        TXx = df_dm.sort_values("Tair", ascending=False)[:1].Tair.values[0]
        TXx_idx = df_dm.sort_values("Tair",
                                    ascending=False)[:1].index.values[0]
        TXx_idx_minus_four= TXx_idx - pd.Timedelta(3, unit='d')

        (Tairs, Qles,
         Qhs, B, GPPs) = get_values(df_dm, df_df, df_dfs, TXx_idx, TXx_idx_minus_four)

        (Tairs, Qles, B, GPPs,
         df_dm, df_df) = check_for_rain(rain, TXx_idx_minus_four,
                                        TXx_idx, df_dm, df_df, df_dfs,
                                        Tairs, Qles, Qhs, B, GPPs)

        if len(df_dm) <= 4:
            Tairs = np.array([np.nan,np.nan,np.nan,np.nan])
            Qles = np.array([np.nan,np.nan,np.nan,np.nan])
            B = np.array([np.nan,np.nan,np.nan,np.nan])
            GPP = np.array([np.nan,np.nan,np.nan,np.nan])
            break

    return (Tairs, Qles, B, GPPs, df_dm, df_df)



def check_for_rain(rain, TXx_idx_minus_four, TXx_idx, df_dm, df_df, df_dfs,
                   Tairs, Qles, Qhs, B, GPPs):

    threshold = 0.2 # mm d-1; arbitary, we can refine.
    total_rain = np.sum(rain[(rain.index >= TXx_idx_minus_four) &
                             (rain.index <= TXx_idx)].values)

    while total_rain > threshold or len(Tairs) != 4:

        # Drop this event as there was some rain or we didn't get 5 good QA days
        df_dm = df_dm[(df_dm.index < TXx_idx_minus_four) |
                       (df_dm.index > TXx_idx)]
        df_df = df_df[(df_df.index < TXx_idx_minus_four) |
                       (df_df.index > TXx_idx)]

        TXx = df_dm.sort_values("Tair", ascending=False)[:1].Tair.values[0]
        TXx_idx = df_dm.sort_values("Tair",
                                    ascending=False)[:1].index.values[0]
        TXx_idx_minus_four = TXx_idx - pd.Timedelta(3, unit='d')

        (Tairs, Qles,
         Qhs, B, GPPs) = get_values(df_dm, df_df, df_dfs, TXx_idx, TXx_idx_minus_four)

        total_rain = np.sum(rain[(rain.index >= TXx_idx_minus_four) &
                                 (rain.index <= TXx_idx)].values)

        if len(df_dm) <= 4:
            Tairs = np.array([np.nan,np.nan,np.nan,np.nan])
            Qles = np.array([np.nan,np.nan,np.nan,np.nan])
            B = np.array([np.nan,np.nan,np.nan,np.nan])
            GPPs = np.array([np.nan,np.nan,np.nan,np.nan])
            break

    return (Tairs, Qles, B, GPPs, df_dm, df_df)



def get_ozflux_pfts():

    sites = ["AdelaideRiver","Calperum","CapeTribulation","CowBay",\
             "CumberlandPlains","DalyPasture","DalyUncleared",\
             "DryRiver","Emerald","Gingin","GreatWesternWoodlands",\
             "HowardSprings","Otway","RedDirtMelonFarm","RiggsCreek",\
             "Samford","SturtPlains","Tumbarumba","Whroo",\
             "WombatStateForest","Yanco"]

    pfts = ["SAV","EBF","TRF","TRF","EBF","GRA","SAV",\
            "SAV","NA","EBF","EBF",\
            "SAV","GRA","NA","GRA",\
            "GRA","GRA","EBF","EBF",\
            "EBF","GRA"]

    d = dict(zip(sites, pfts))

    return d

def mask_crap_days(df_mod, df_flx, df_met):
    """ Mask bad QA, i.e. drop any data where Qle, Qa, Tair and Rain are flagged
    as being of poor quality"""

    thresh = 0.1 / 1800. # 0.1 mm/hlfhr -> mm/s
    df_flx.where(df_flx.Qle_qc == 1, inplace=True)
    df_flx.where(df_flx.Qh_qc == 1, inplace=True)
    df_flx.where(df_met.Tair_qc == 1, inplace=True)

    df_mod.where(df_flx.Qle_qc == 1, inplace=True)
    df_mod.where(df_flx.Qh_qc == 1, inplace=True)
    df_mod.where(df_met.Tair_qc == 1, inplace=True)

    df_met.where(df_flx.Qle_qc == 1, inplace=True)
    df_met.where(df_flx.Qh_qc == 1, inplace=True)
    df_met.where(df_met.Tair_qc == 1, inplace=True)

    # Mask dew
    df_met.where(df_flx.Qle > 0., inplace=True)
    df_mod.where(df_flx.Qle > 0., inplace=True)
    df_flx.where(df_flx.Qle > 0., inplace=True)

    df_met = df_met.reset_index()
    df_met = df_met.set_index('time')
    df_flx = df_flx.reset_index()
    df_flx = df_flx.set_index('time')
    df_mod = df_mod.reset_index()
    df_mod = df_mod.set_index('time')

    return df_mod, df_flx, df_met

def open_file(cable_fn, flux_fn, met_fn, oz_flux=True):
    site = os.path.basename(flux_fn).split("OzFlux")[0]

    ds = xr.open_dataset(flux_fn)
    #print(ds)
    df_flx = ds.squeeze(dim=["x","y"], drop=True).to_dataframe()
    df_flx = df_flx.reset_index()
    df_flx = df_flx.set_index('time')

    ds = xr.open_dataset(met_fn)
    df_met = ds.squeeze(dim=["x","y"], drop=True).to_dataframe()
    df_met = df_met.reset_index()
    df_met = df_met.set_index('time')

    ds = xr.open_dataset(cable_fn)
    time = pd.to_datetime(ds.time.values)
    df_mod = ds[['Qle','Qh', 'GPP']].squeeze(drop=True).to_dataframe()
    df_mod['time'] = time
    df_mod = df_mod.set_index('time')

    return (site, df_mod, df_flx, df_met)

if __name__ == "__main__":

    oz_flux = True
    if oz_flux:
        flux_dir = "/Users/mdekauwe/research/OzFlux"
        ofname = "ozflux_all_events_CABLE.csv"
        cable_dir = "/Users/mdekauwe/research/CABLE_runs/runs/ozflux/outputs"
    else:
        flux_dir = "/srv/ccrc/data04/z3509830/Fluxnet_data/Data_for_Jiafu/Daily/Nc_files"
        flux_dir = "/Users/mdekauwe/Desktop/test"
        ofname = "fluxnet2015_CABLE.csv"
        cable_dir = "/Users/mdekauwe/research/CABLE_runs/runs/ozflux/outputs"
    main(flux_dir, cable_dir, ofname, oz_flux=oz_flux)
