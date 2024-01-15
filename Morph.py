from netCDF4 import Dataset
import pandas as pd
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

import os, sys
import pickle as pkl
import scipy as sp


class Morph():
    
    
    
    def __init__(self, R, Z, Xpoint, Btot, Bpol, S, Spol):
        self.R = R
        self.Z = Z
        self.Xpoint = Xpoint
        
        # Split into leg up to and incl. xpoint
        self.R_leg = R[:Xpoint+1]
        self.Z_leg = Z[:Xpoint+1]
        
        self.Btot = Btot
        self.Bpol = Bpol
        self.S = S
        self.Spol = Spol
        


    def set_start_profile(self, offsets):
        self.start = self._set_profile(offsets)
        self.start["R_leg"] = self.R_leg
        self.start["Z_leg"] = self.Z_leg
        self.start["R"] = self.R
        self.start["Z"] = self.Z
        self.start["S"] = self.S
        self.start["Spol"] = self.Spol
        self.start["Btot"] = self.Btot
        self.start["Bpol"] = self.Bpol
        self.start["Xpoint"] = self.Xpoint
        
        
        
    def set_end_profile(self, offsets):
        self.end = self._set_profile(offsets)
        self.end = self._populate_profile(self.end)
        
        
        
    def generate_profiles(self, factors):
        """ 
        Make a series of profiles according to provided factors
        where factor = 0 corresponds to start, factor = 1
        corresponds to end and factor = 0.5 corresponds to halfway.
        """
        profiles = {}
        for i in factors:
            profiles[i] = self.morph_between(i)
        
        self.profiles = profiles
        
        
        
    def morph_between(self, factor):
        
        prof = {}
        prof["x"] = self.start["x"] + factor*(self.end["x"] - self.start["x"])
        prof["y"] = self.start["y"] + factor*(self.end["y"] - self.start["y"])
        prof["xs"], prof["ys"] = cord_spline(prof["x"],prof["y"])   # Interpolate
        prof = self._populate_profile(prof)
        
        return prof
        
        
        
    def _set_profile(self, offsets):
        prof = {}
        prof["x"], prof["y"] = shift_points(self.R_leg, self.Z_leg, offsets)    # Points defining profile
        prof["xs"], prof["ys"] = cord_spline(prof["x"],prof["y"])   # Interpolate
        
        return prof
    
    
    
    def _populate_profile(self, prof):
        """ 
        Add the rest of the profile to the leg above the X-point
        Add Bpol and Btot along entire leg
        Returns new modified profile
        """
        
        start = self.start
        prof["Xpoint"] = start["Xpoint"]
        
        ## Add leg above X-point
        # xs and ys are backwards
        dist = get_cord_distance(start["R_leg"], start["Z_leg"])   # Distances along old leg
        spl = cord_spline(prof["xs"][::-1], prof["ys"][::-1], return_spline = True)   # Spline interp for new leg
        R_leg_new, Z_leg_new = spl(dist)     # New leg interpolated onto same points as old leg

        prof["R"] = np.concatenate([
            R_leg_new,
            start["R"][start["Xpoint"]+1:], 
            ])
        
        prof["Z"] = np.concatenate([
            Z_leg_new,
            start["Z"][start["Xpoint"]+1:], 
            ])

        ## Poloidal dist and field
        prof["Spol"] = returnll(prof["R"], prof["Z"])
        prof["Bpol"] = start["Bpol"].copy()    # Assume same poloidal field as start
        
        ## Total field 
        Btor = np.sqrt(start["Btot"]**2 - start["Bpol"]**2)   # Toroidal field
        Btor_leg = Btor[:start["Xpoint"]+1]
        Btor_leg_new = Btor_leg * (start["R_leg"] / R_leg_new)

        Bpol_leg = start["Bpol"][:start["Xpoint"]+1]
        Btot_leg_new = np.sqrt(Btor_leg_new**2 + Bpol_leg**2)
        
        prof["Btot"] = np.concatenate([
            Btot_leg_new,
            start["Btot"][start["Xpoint"]+1:], 
            ])
        
        prof["S"] = returnS(prof["R"], prof["Z"], prof["Btot"], prof["Bpol"])
        
        return prof
    
    
    
    def get_connection_length(self, prof):
        """ 
        Return connection length of profile
        """
        return prof["S"][-1] - prof["S"][0]
    
    
    
    def get_total_flux_expansion(self, prof):
        """
        Return total flux expansion of profile
        """
        return prof["Btot"][prof["Xpoint"]] / prof["Btot"][0]
    
    
    
    def get_average_frac_gradB(self, prof):
        """
        Return the average fractional Btot gradient
        below the X-point
        """
        return ((np.gradient(prof["Btot"], prof["Spol"]) / prof["Btot"])[:prof["Xpoint"]]).mean()
    
    def get_average_B_ratio(self, prof):
        """
        Return the average Btot below X-point
        """
        return prof["Btot"][prof["Xpoint"]] / (prof["Btot"][:prof["Xpoint"]]).mean()
    
    
    def get_sensitivity(self, crel_trim, SpolPlot, fluctuation=1.1, location=0, verbose = False):
        """
        Get detachment sensitivity at a certain location
        Sensitivity defined the location of front after a given fluctuation
        as a fraction of the total poloidal leg length.
        
        Inputs
        ------
        crel_trim: 1D array
            Crel values of detachment front with unstable regions trimmed (from DLS)
        SpolPlot: 1D array
            Poloidal distance from the DLS result
        fluctuation: float
            Fluctuation to calculate sensitivity as fraction of distance to X-point
            Default: 1.1
        location: float
            Location to calculate sensitivity as fraction of distance to X-point
            Default: target (0)
        verbose: bool
            Print results
            
        Returns
        -------
        sensitivity: float
            Sensitivity: position of front as fraction of distance towards X-point
            
        """
        # Drop NaNs for points in unstable region
        xy = pd.DataFrame()
        xy["crel"] = crel_trim
        xy["spol"] = SpolPlot
        xy = xy.dropna()

        Spol_from_crel = sp.interpolate.InterpolatedUnivariateSpline(xy["crel"], xy["spol"])
        Crel_from_spol = sp.interpolate.InterpolatedUnivariateSpline(xy["spol"], xy["crel"])

        Spol_at_loc = xy["spol"].iloc[-1] * location
        Crel_at_loc = Crel_from_spol(Spol_at_loc)
        Spol_total = xy["spol"].iloc[-1]


        if (Crel_at_loc - xy["crel"].iloc[0]) < -1e-6:
            sensitivity = 1   # Front in unstable region
        else:
            sensitivity = Spol_from_crel(Crel_at_loc*fluctuation) / Spol_total

        if verbose is True:
            print(f"Spol at location: {Spol_at_loc:.3f}")
            print(f"Crel at location: {Crel_at_loc:.3f}")
            print(f"Sensitivity: {sensitivity:.3f}")
            
        return sensitivity
    
    
    
    def plot_profile(self, prof, dpi=100, ylim=(None,None), xlim=(None,None)):
        
        fig, ax = plt.subplots(dpi = dpi)
        
        s = self.start
        p = prof

        ax.plot(s["xs"], s["ys"], c = "forestgreen", zorder = 100, alpha = 1)
        ax.scatter(s["x"], s["y"], c = "limegreen", zorder = 100, marker = "+", linewidth = 15, s = 3)
        ax.plot(p["xs"], p["ys"], c = "deeppink", zorder = 100, alpha = 0.4)
        ax.scatter(p["x"], p["y"], c = "red", zorder = 100, marker = "x")

        ax.plot(s["R"], s["Z"], linewidth = 3, marker = "o", markersize = 0, color = "black", alpha = 1)
        
        # ax.plot(d_outer["R"], d_outer["Z"], linewidth = 3, marker = "o", markersize = 0, color = "black", alpha = 1)
        ax.set_xlabel("$R\ (m)$", fontsize = 15)
        ax.set_ylabel("$Z\ (m)$")
        
        if ylim != (None,None):
            ax.set_ylim(ylim)
        if xlim != (None,None):
            ax.set_xlim(xlim)

        alpha = 0.5
        ax.set_title("RZ Space")
        ax.grid(alpha = 0.3, color = "k")
        ax.set_aspect("equal")
        
        
        
    def plot_profile_topology(self, base_profile, profiles):

        d = base_profile
        
        fig, axes = plt.subplots(2,2, figsize = (8,8))
        markers = ["o", "v"]

        profstyle = dict(alpha = 0.3)
        

        basestyle = dict(c = "black")
        xstyle = dict(marker = "+", linewidth = 2, s = 150, c = "r", zorder = 100)

        S_xpoint_max = max([p["S"][p["Xpoint"]] for p in profiles])
        S_pol_xpoint_max = max([p["Spol"][p["Xpoint"]] for p in profiles])

        Spol_shift_base = S_pol_xpoint_max - d["Spol"][d["Xpoint"]] 



        ax = axes[0,0]
        ax.set_title("Fractional $B_{tot}$ gradient")

        ax.plot(d["Spol"] + Spol_shift_base, np.gradient(d["Btot"], d["Spol"]) / d["Btot"], **basestyle)
        ax.scatter(d["Spol"][d["Xpoint"]] + Spol_shift_base, (np.gradient(d["Btot"], d["Spol"]) / d["Btot"])[d["Xpoint"]], **xstyle)
        for i, p in enumerate(profiles): 
            Spol_shift = S_pol_xpoint_max  - p["Spol"][p["Xpoint"]]
            ax.plot(p["Spol"] + Spol_shift, np.gradient(p["Btot"], p["Spol"]) / p["Btot"], **profstyle, marker = markers[i])
            # ax.scatter(p["Spol"][p["Xpoint"]]+ Spol_shift, (np.gradient(p["Btot"], p["Spol"]) / p["Btot"])[p["Xpoint"]], **xstyle)
            ax.set_xlabel(r"$S_{\theta} \   [m]$");   
            ax.set_ylabel("$B_{tot}$ $[T]$")


        ax = axes[1,0]
        ax.set_title("$B_{tot}$")

        ax.plot(d["Spol"] + Spol_shift_base, d["Btot"], **basestyle)
        ax.scatter(d["Spol"][d["Xpoint"]] + Spol_shift_base, d["Btot"][d["Xpoint"]], **xstyle)
        for i, p in enumerate(profiles): 
            Spol_shift = S_pol_xpoint_max  - p["Spol"][p["Xpoint"]]
            ax.plot(p["Spol"] + Spol_shift, p["Btot"], **profstyle, marker = markers[i])
            ax.set_xlabel(r"$S_{\theta} \   [m]$")
            ax.set_ylabel("$B_{tot}$ $[T]$")


        ax = axes[0,1]

        ax.set_title(r"Field line pitch $B_{pol}/B_{tot}$")
        ax.plot(d["Spol"] + Spol_shift_base, d["Bpol"]/d["Btot"], **basestyle)
        ax.scatter(d["Spol"][d["Xpoint"]]+ Spol_shift_base, (d["Bpol"]/d["Btot"])[d["Xpoint"]], **xstyle)
        for i, p in enumerate(profiles): 
            Spol_shift = S_pol_xpoint_max  - p["Spol"][p["Xpoint"]]
            ax.plot(p["Spol"] + Spol_shift, p["Bpol"]/p["Btot"], **profstyle, marker = markers[i])
        ax.set_xlabel(r"$S_{\theta} \   [m]$")
        ax.set_ylabel(r"$B_{pol} \ / B_{tot}$ ")

        ax = axes[1,1]
        ax.set_title("$B_{pol}$")

        ax.plot(d["Spol"] + Spol_shift_base, d["Bpol"], **basestyle)
        ax.scatter(d["Spol"][d["Xpoint"]] + Spol_shift_base,  (d["Bpol"])[d["Xpoint"]], **xstyle)
        for i, p in enumerate(profiles): 
            Spol_shift = S_pol_xpoint_max  - p["Spol"][p["Xpoint"]]
            ax.plot(p["Spol"] + Spol_shift, p["Bpol"], **profstyle, marker = markers[i])
            ax.scatter(p["Spol"][p["Xpoint"]] + Spol_shift,  (p["Bpol"])[p["Xpoint"]], **xstyle)
        ax.set_xlabel(r"$S_{\theta} \   [m]$")
        ax.set_ylabel(r"$B_{\theta}$ $[T]$")


        fig.tight_layout()
    
    
    
def cord_spline(x,y, return_spline = False):
    """ 
    Do cord interpolation of x and y. This parametrises them
    by the cord length and allows them to go back on themselves, 
    i.e. to have non-unique X values and non-monotonicity.
    I think you need to have at least 4 points.
    
    https://docs.scipy.org/doc/scipy/tutorial/interpolate/1D.html#parametric-spline-curves
    """
    p = np.stack((x,y))
    u_cord = get_cord_distance(x,y)

    spl = sp.interpolate.make_interp_spline(u_cord, p, axis=1)

    uu = np.linspace(u_cord[0], u_cord[-1], 200)
    R, Z = spl(uu)
    
    if return_spline:
        return spl
    else:
        return R,Z
    
    
    
def get_cord_distance(x,y):
    """ 
    Return array of distances along a curve defined by x and y.
    """
    p = np.stack((x,y))
    dp = p[:,1:] - p[:,:-1]        # 2-vector distances between points
    l = (dp**2).sum(axis=0)        # squares of lengths of 2-vectors between points
    u_cord = np.sqrt(l).cumsum()   # Cumulative sum of 2-norms
    u_cord /= u_cord[-1]           # normalize to interval [0,1]
    u_cord = np.r_[0, u_cord]      # the first point is parameterized at zero
    
    return u_cord



def shift_points(R, Z, offsets):
    """ 
    Make control points on a field line according to points of index in list i.
    
    Parameters
    ----------
    R, Z: 1D arrays
        R and Z coordinates of field line.
    i: list of ints
        Indices of points to shift. They are the control points of the spline.
    yoffset: list of floats
        Y offset to apply to each point in i.
    xoffset: list of floats
        X offset to apply to each point in i.
    """
    
    #        XPOINT ---------   TARGET
    spl = cord_spline(R,Z, return_spline=True)
    x, y = [], []
    
    
    
    for i, point in enumerate(offsets):
        
        position = point["pos"]
        offsetx = point["offsetx"] if "offsetx" in point else 0
        offsety = point["offsety"] if "offsety" in point else 0
        
        Rs, Zs = spl(position)
        x.append(Rs+offsetx)
        y.append(Zs+offsety)
        # x = [R[i[0]], R[i[1]], R[i[2]], R[i[3]]]
        # y = [Z[i[0]]+yoffset[0], Z[i[1]]+yoffset[1], Z[i[2]]+yoffset[2], Z[i[3]]+yoffset[3]]
    
    return np.array(x), np.array(y)
    
   
    
def returnll(R,Z):
    #return the poloidal distances from the target for a given configuration
    PrevR = R[0]
    ll = []
    currentl = 0
    PrevZ = Z[0]
    for i in range(len(R)):
        dl = np.sqrt((PrevR-R[i])**2 + (PrevZ-Z[i])**2)
        currentl = currentl+ dl
        ll.append(currentl)
        PrevR = R[i]
        PrevZ = Z[i]
    return ll



def returnS(R,Z,B,Bpol):
    #return the real total distances from the target for a given configuration
    PrevR = R[0]
    s = []
    currents = 0
    PrevZ = Z[0]
    for i in range(len(R)):
        dl = np.sqrt((PrevR-R[i])**2 + (PrevZ-Z[i])**2)
        ds = dl*np.abs(B[i])/np.abs(Bpol[i])
        currents = currents+ ds
        s.append(currents)
        PrevR = R[i]
        PrevZ = Z[i]
    return s