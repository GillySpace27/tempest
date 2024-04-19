#!/usr/bin/python
#TEMPEST: The Efficient Modified-Parker-Equation-Solving Tool
#   17 Sep 2014 - Documented version 1.3.7 for public use
#               Cite Woolsey & Cranmer (2014) ApJ 787, 2, 160

import numpy as np
from scipy import interpolate
from scipy import integrate
np.seterr(divide='raise',invalid='raise')

def main():
    """
    PURPOSE: To take a set of 1D open magnetic field profiles and
        determine the properties of the solar wind generated by
        such magnetic field geometries in the framework of Alfven
        wave-driven turbulent heating, calibrated by ZEPHYR code.
    INPUTS: None, reads from init() function:
        infile - a textfile containing N models defined at
            M heights. See read_bzin() documentation
            below for required format of this file.
        filename - prefix for outputted save files
    OUTPUT: Four .npz files in the directory where the code is run:
        1) filename_inputs.npz: contains heights, magnetic field
            and temperature profiles, transition region height
        2) filename_miranda.npz: contains initial outflow solution,
            critical point height, sound speed profile, and
            momentum equation RHS without wave terms
        3) filename_prospero.npz: contains steady-state solution
            for outflow speed profile and critical heights
        4) filename_fullRHS.npz: contains density profile,
            Alfven wave energy density and amplitude, critical
            speed profile, momentum equation full RHS and the
            calculated turbulent efficiency profile
    EXTERNAL PACKAGES: numpy, scipy
    """
    init()
    #read in heights and magnetic field models
    #   read_bzin: uses a zephyr_bz.in formatted file
    multiple=1
    nmods,nsteps,B,zx = read_bzin(infile,multiple)
    if zx[0] == 0:
        zx[0] = 10**-10
    rx = zx + 1.0
    zm = zx*Rsun
    rm = rx*Rsun

    dBdr = quickDeriv(B,rm,nmods,nsteps)
    T,dTdr,zTR = fitT(B,zx)
    np.savez(filename+'_inputs', zx=zx, B=B, T=T, zTR=zTR)
    #***************************************************************
    u1,zC1 = miranda(rm,nmods,nsteps,B,dBdr,T,dTdr,zTR)

    itexp=0.1
    changemodels = np.ones(nmods)
    change = 1
    allchange=np.zeros((nmods,nsteps))
    uout=np.zeros((nmods,nsteps))
    uin = u1.copy()

    #need to run models individually until each converges
    Bj = np.zeros((1,nsteps))
    dBdrj = np.zeros((1,nsteps))
    Tj = np.zeros((1,nsteps))
    dTdrj = np.zeros((1,nsteps))
    uinj = np.zeros((1,nsteps))
    for j in range(0,nmods):
        it = 0
        Bj[0,:] = B[j,:].copy()
        dBdrj[0,:] = dBdr[j,:].copy()
        Tj[0,:] = T[j,:].copy()
        dTdrj[0,:] = dTdr[j,:].copy()
        uinj[0,:] = uin[j,:].copy()
        while(((changemodels[j] > 0.005) and (it<300)) or (it<10)):
            uj,zCj = prospero(rm,1,nsteps,Bj,dBdrj,Tj,dTdrj,zTR[j],uinj)
            #allchange for model j based on a single model run
            allchange[j,:]=abs((uj[0,:]-uinj[0,:])/uinj[0,:])
            uinj[0,:]=((uinj[0,:]**(1.0-itexp))*(uj[0,:]**(itexp)))
            changemodels[j]=np.mean(allchange[j,:])
            it += 1
        uout[j,:] = uinj[0,:].copy()
        print (j,', # iterations:',it,', conv:',changemodels[j])

    u,zC = prospero(rm,nmods,nsteps,B,dBdr,T,dTdr,zTR,uout)
    np.savez(filename+'_prospero', u=u, zC=zC)

def init():
    """
    PURPOSE: To setup all required physical constants, including
        fundamental constants of nature, labeled heights used in
        the code, and constants that are adjustable if required
    INPUTS: none
    OUTPUT: defined global variables used throughout TEMPEST
    EXTERNAL PACKAGES: none
    """
    #fundamental constants of nature in cgs units:
    global G, Msun, boltzk, mH, Rsun
    G = 6.67e-8 #cm^3 g^-1 s^-2
    Msun = 1.988e33 #g
    boltzk = 1.381e-16 #erg/K = g cm^2 s^-2 K^-1
    mH = 1.674e-24 #g
    Rsun = 6.955e10 #cm

    #constants used in the code that can be adjusted if needed:
    global zSS, zAU, ztran, zlow
    zSS = 1.5     #Rsun, accepted standard
    zAU = 214.1   #Rsun, physical constant
    ztran = 0.006 #Rsun, typically between 0.005 and 0.025
    zlow = 0.04   #Rsun, used for calculating expansion factor
    global TTR, rhomin, ellbase, Sbase
    TTR = 1.2e4 #K
    #rhoTR = 7.e-15  #g/cm3, a better point for mass flux cons.
    rhomin = 1.0e-28 #minimum density used in rhofloor
    ellbase = 7.5e6 #cm, correlation length for turbulent eddies
    Sbase = 9.e4 #erg cm**-2 s**-1 G**-1
    global infile, filename
    infile="example_input_profile.in"
    filename='T'

def miranda(rm,nmods,nsteps,B,dBdr,T,dTdr,zTR):
    """
    PURPOSE: To find an initial solution for the solar wind outflow
        speed without the wave pressure term in the momentum equation.
        {u(r) - [uc(r)**2/u(r)]}*(du/dr) = RHS
        where uc(r)**2 = a(r)**2 = boltzk*T(r)/mH
        and RHS = (-G*Msun/r**2)-[ucr**2/B]*(dB/dr)-[boltzk/mh]*(dT/dr)
        such that du/dr = RHS / (u - [ucr**2/u])
    INPUTS:
        rm - array of radii where the profiles are defined
        nmods - number of models in the input arrays (>= 1)
        nsteps - number of height values in each model i.e. len(rm)
        B - magnetic field strength as a function of radius
        dBdr - derivative of B, also one dimensional for each model
        T - temperature profile as a function of radius for N models
        dTdr - derivative of T, also one dimensional for each model
        zTR - location of transition region in temperature profile
    OUTPUT:
        u - intial outflow solutions for all models
        zcrit - height of critical points for all models
    EXTERNAL PACKAGES: numpy
    """
    init()
    ucr = np.zeros((nmods,nsteps))
    rhs = np.zeros((nmods,nsteps))
    for j in range(0,nmods):
        for k in range(0,nsteps):
            if (rm[k]/Rsun) < zTR[j]+1:
                xion = 0
            if (rm[k]/Rsun) >= zTR[j]+1:
                xion = 1
            ucr[j,k] = np.sqrt((1+xion)*boltzk*T[j,k]/mH)
            gravterm = -G*Msun/rm[k]**2
            magterm = -ucr[j,k]**2*(dBdr[j,k]/B[j,k])
            tempterm = -ucr[j,k]**2*(dTdr[j,k]/T[j,k])
            rhs[j,k] = gravterm + magterm + tempterm

    u,zcrit = outflows(rm,nmods,nsteps,rhs,ucr)
    np.savez(filename+'_miranda', ucr=ucr, rhs=rhs, u=u, zcrit=zcrit)
    return u,zcrit

def prospero(rm,nmods,nsteps,B,dBdr,T,dTdr,zTR,u1):
    """
    PURPOSE: To find the solar wind outflow solution containing the
        effects of wave-driven heating AND wave pressure acceleration.
    INPUTS:
        rm - array of radii where the profiles are defined
        nmods - number of models in the input arrays (>= 1)
        nsteps - number of height values in each model i.e. len(rm)
        B - magnetic field strength as a function of radius
        dBdr - derivative of B, also one dimensional for each model
        T - temperature profile as a function of radius for N models
        dTdr - derivative of T, also one dimensional for each model
        zTR - location of transition region in temperature profile
        u1 - previous outflow solution used to determine density
    OUTPUT:
        u - outflow solutions for all model
        zcrit - height of critical points for all models
    EXTERNAL PACKAGES: numpy
    """
    a,ucr,rhs = fullRHS(rm,nmods,nsteps,B,dBdr,T,dTdr,zTR,u1)
    u,zcrit = outflows(rm,nmods,nsteps,rhs,ucr)
    return u,zcrit

def read_bzin(zephyrinfile,multiple):
    """
    PURPOSE: To read in a text file that contains the magnetic
        field profiles for all of the models for use in calculations.
    INPUTS:
        zephyrinfile - string containing full name of file
        multiple - factor to multiply number of points in profiles
    OUTPUT:
        nmods - number of models read in
        nsteps - number of heights where the magnetic field
        profile is defined for each model
        B - magnetic field strength profiles (in Gauss)
        zx - heights where B is defined (in solar radii)
    EXTERNAL PACKAGES: numpy
    """
    #read zephyr_bz.in formatted infile to get zx, B(r)
    infileopen = open(zephyrinfile, "r")
    line1 = infileopen.readline()
    nmods,nsteps = line1.split()
    nmods=int(nmods)
    nsteps=int(nsteps)
    oB = np.zeros((nmods,nsteps))

    #set of heights are next nsteps lines after line1
    ozx = np.fromfile(infileopen, count=nsteps, sep=" ", dtype=float)
    #loop over nmods to get magnetic field for each model
    for i in range(0,nmods):
        line2 = infileopen.readline() # model number, latitude
        Blist = np.fromfile(infileopen, count=nsteps,
                            sep=" ", dtype=float)
        oB[i,:] = Blist
    infileopen.close()

    #Interpolate more points based on input 'multiple'
    zx = np.zeros(nsteps*multiple)
    flag=0
    for i in range(0,nsteps-1):
        for l in range(0,multiple):
            delz = (ozx[i+1]-ozx[i])/float(multiple)
            zx[flag] = ozx[i]+(delz*l)
            flag+=1
    for l in range(0,multiple):
        delz = (ozx[nsteps-1]-ozx[nsteps-2])/float(multiple)
        zx[flag] = ozx[nsteps-1]+(delz*l)
        flag+=1
    nsteps = len(zx)
    B = np.zeros((nmods,nsteps))
    for j in range(0,nmods):
        for k in range(0,nsteps):
            B[j,k] = np.interp(zx[k],ozx,oB[j,:])
    return nmods,nsteps,B,zx

def quickDeriv(f,r,fsets,steps):
    """
    PURPOSE: To populate an array with numerical estimates of the
        derivative of an input array along one dimension.
    INPUTS:
        f - input array definied at all steps for all models
        r - dimension along which to find the derivative
        fsets - number of different models contained in f
        steps - number of steps along r i.e. len(r)
    OUTPUT:
        dfdr - value of the derivative of f w.r.t. r for each model.
    EXTERNAL PACKAGES: numpy
    """
    #Slope taken from centered difference, general use
    dfdr = np.zeros((fsets,steps))
    for j in range(0,fsets):
        # first height value's derivative is slope from pt 0 to pt 1
        dfdr[j,0] = (f[j,1]-f[j,0])/(r[1]-r[0])
        # middle points look at deltaB/deltah for pts above and below
        for k in range(1,steps-1):
            dfdr[j,k] = (f[j,k+1]-f[j,k-1])/(r[k+1]-r[k-1])
        # last height's derivative is slope from pt last-1 to pt last
        dfdr[j,steps-1] = ((f[j,steps-1]-f[j,steps-2])/
                            (r[steps-1]-r[steps-2]))
    return dfdr

def rk4(fi,ri,dr,r,dfdr=None):
    """
        PURPOSE: To integrate a function using fourth-order
        Runge-Kutta techniques from a starting point (ri,fi)

        INPUTS:
        fi - the starting value of the function
        ri - the starting radius from which to integrate out
        dr - the amount of distance over which to integrate
        r - the full array of radii where dfdr is defined
        dfdr - the derivative of f; alternately used to contain
        the arrays for specific TEMPEST use: ucr and rhs
        OUTPUT:
        ff - the ending value of the function at a point ri + dr
             (where dr may be in either direction)
        EXTERNAL PACKAGES: numpy
        """
    #General RK4 routine with adaptive stepping
    adaptiveconstant = 0.1
    #check if integrating up or down (sign of dr)
    sign = np.sign(dr) #result is -1, 1, or 0
    rstep=ri
    fstep=fi
    stepstotal = 0.0
    stepstaken = 0

    while np.abs(stepstotal) < np.abs(dr):
        r1 = rstep
        f1 = fstep


        dlnf = dfdrval(fstep,rstep,r,dfdr)/fstep
        deltar = sign*np.abs(adaptiveconstant/dlnf)
        #check to see if deltar is too large or too many steps have happened
        if ((np.abs(stepstotal)+np.abs(deltar)>np.abs(dr)) or (stepstaken>100)):
            deltar = sign*(np.abs(dr) - np.abs(stepstotal))

        r2 = r1 + 0.5*deltar
        r3 = r1 + deltar

        y1 = fstep
        pk1 = dr*dfdrval(y1,r1,r,dfdr)
        y2 = fstep + 0.5*pk1
        pk2 = dr*dfdrval(y2,r2,r,dfdr)
        y3 = fstep + 0.5*pk2
        pk3 = dr*dfdrval(y3,r2,r,dfdr)
        y4 = fstep + pk3
        pk4 = dr*dfdrval(y4,r3,r,dfdr)

        ff = fstep + (pk1+pk4)/6. + (pk2+pk3)/3.
        stepstotal += np.abs(deltar)
        stepstaken += 1
        rstep += deltar #increase OR decrease
        fstep = ff
    return ff

def dfdrval(uval,rval,rarray,dfdr=None):
    """
    PURPOSE: To interpolate the slope dfdr from a given
        point and the dfdr profile for a subset of models
    INPUTS:
        uval - the value of f at which to interpolate
        rval - the radius r at which to interpolate
        rarray - the radius array along which dfdr is defined
        dfdr - the array of dfdr values to interpolate from;
            alternately for specific TEMPEST use contains the
            elements needed to define dudr (ucr, rhs)
    OUTPUT:
        slope - the value of dfdr AT the point r=rval, f=uval
    EXTERNAL PACKAGES: numpy
    """
    if not isinstance(dfdr,np.ndarray):
        ucrval = np.interp(rval,rarray,dfdr[0][:])
        rhsval = np.interp(rval,rarray,dfdr[1][:])
        slope = rhsval/(uval - (ucrval**2/uval))
    else:
        slope = np.interp(rval,rarray,dfdr[:])
    return slope

def smooth(x,w_len):
    """
    PURPOSE: To take an array x and smooth it using a Bartlett
        window of length w_len to provide a smooth array yfixed
        ***Based on http://wiki.scipy.org/Cookbook/SignalSmooth
    INPUTS:
        x - original un-smoothed array
        w_len - the width of the Bartlett window
    OUTPUT:
        yfixed - resulting smoothed array
    EXTERNAL PACKAGES: numpy
    """
    if w_len < 3:
        return x
    s=np.r_[2*x[0]-x[w_len:1:-1], x, 2*x[-1]-x[-1:-w_len:-1]]
    w = np.ones(w_len,'d')
    window = 'bartlett'
    w = eval('np.'+window+'(w_len)')
    y=np.convolve(w/w.sum(),s,mode='valid')
    yfixed = y[(w_len/2):(len(y)-(w_len/2))]
    return yfixed

def fitT(B,zx):
    """
    PURPOSE: To estimate temperature profiles of models based only
        on the input magnetic field profiles based on fitting
        parameters taken from statistically significant correlations
        found by the code ZEPHYR (see Cranmer et al. 2007).
    INPUTS:
        B - magnetic field profiles for all models
        zx - the set of heights at which all B are defined
    OUTPUT:
        T - temperature profiles for all models
        dTdr - derivative of the temperature profiles
        z_TR - height of transition region for each model
    EXTERNAL PACKAGES: numpy
    """
    init()
    rm = (zx+1.0)*Rsun
    steps = len(zx)

    aucheck = abs(zx - zAU)
    iau = int(aucheck.argmin())
    lowcheck = abs(zx - zlow)
    ilow = int(lowcheck.argmin())
    sscheck = abs(zx - zSS)
    iss = int(sscheck.argmin())

    """The following fitting parameters are based on correlations
        between magnetic field strengths and ZEPHYR-determined
        temperature profiles. Latest update in version 1.2.1"""
    zset = (0.00314, 0.4206, 2.0, 3.0)
    iset = np.zeros(4)
    for i in range(4):
        iset[i] = int(abs(zx-zset[i]).argmin())
    models=len(B[:,0])
    Bsetfit = np.zeros((models,4))
    z_TR = np.zeros(models)
    for j in range(0,models):
        z_TR[j] = 0.0057+7.e-6/(B[j,iset[2]]**1.3)
        for k in range(4):
            Bsetfit[j,k] = B[j,iset[k]]

    zresid = (0.662,0.0144)
    iresid0 = int(np.abs(zx-zresid[0]).argmin())
    iresid1 = int(np.abs(zx-zresid[1]).argmin())
    Bresid = np.zeros((models,2))
    aTresid = np.zeros((models,2))
    for j in range(0,models):
        Bresid[j,0] = B[j,iresid0]
        Bresid[j,1] = B[j,iresid1]
        aTresid[j,0] = 0.0559 + 0.13985*np.log10(Bresid[j,0])
        aTresid[j,1] = -0.0424 + 0.09285*np.log10(Bresid[j,1])

    aTfit = np.zeros((models,5))
    Tsetfit = np.zeros((models,5))
    for j in range(0, models):
        aTfit[j,0] = 5.554 + 0.1646*np.log10(Bsetfit[j,0]) + aTresid[j,0]
        aTfit[j,1] = 5.967 + 0.2054*np.log10(Bsetfit[j,1]) + aTresid[j,1]
        aTfit[j,2] = 6.228 + 0.2660*np.log10(Bsetfit[j,2])
        aTfit[j,3] = 6.249 + 0.3121*np.log10(Bsetfit[j,3])
        aTfit[j,4] = 6.041 + 0.3547*np.log10(Bsetfit[j,3])
        for k in range(5):
            Tsetfit[j,k] = 10.**aTfit[j,k]

    zfit = (0.02, 0.2, 2.0, 20.0, 200.0)
    ifit = np.zeros(5)
    azfit = np.zeros(5)
    azx = np.zeros(steps)
    for k in range(steps):
        azx[k] = np.log10(zx[k])
    for i in range(5):
        ifit[i] = int(abs(zx-zfit[i]).argmin())
        azfit[i] = np.log10(zfit[i])

    Ttry = np.zeros((models,steps))
    for j in range(0, models):
        trcon = (Tsetfit[j,0]**3.5 - TTR**3.5)/(zfit[0]**2 - z_TR[j]**2)
        for k in range(steps):
            if (zx[k] <= z_TR[j]):
                Ttry[j,k] = TTR
            if (zx[k] > z_TR[j]) and (zx[k] <= zfit[0]):
                Ttry[j,k] = (TTR**3.5+trcon*(zx[k]**2-z_TR[j]**2))**(2./7.)
            if (zx[k] > zfit[0]) and (zx[k] <= zfit[1]):
                ay = aTfit[j,0] + ((aTfit[j,1]-aTfit[j,0])/
                                   (azfit[1]-azfit[0]))*(azx[k]-azfit[0])
                Ttry[j,k] = 10**ay
            if (zx[k] > zfit[1]) and (zx[k] <= zfit[2]):
                ay = aTfit[j,1] + ((aTfit[j,2]-aTfit[j,1])/
                                   (azfit[2]-azfit[1]))*(azx[k]-azfit[1])
                Ttry[j,k] = 10**ay
            if (zx[k] > zfit[2]) and (zx[k] <= zfit[3]):
                ay = aTfit[j,2] + ((aTfit[j,3]-aTfit[j,2])/
                                   (azfit[3]-azfit[2]))*(azx[k]-azfit[2])
                Ttry[j,k] = 10**ay
            if (zx[k] > zfit[3]):
                ay = aTfit[j,3] + ((aTfit[j,4]-aTfit[j,3])/
                                   (azfit[4]-azfit[3]))*(azx[k]-azfit[3])
                Ttry[j,k] = 10**ay

    smoothW = 15
    Tsmooth = np.zeros((models,steps))
    for j in range(0,models):
        Tsmooth[j,:] = smooth(Ttry[j,:],smoothW)
    T = Tsmooth.copy()
    dTdr = quickDeriv(T,rm,models,steps)

    return T,dTdr,z_TR

def fit_refl(B1,zTR1,rm):
    """
    PURPOSE: To determine the profile of the Alfven wave reflection
        coefficient from correlations found in ZEPHYR.
    INPUTS:
        rm - radius array in cm
        B1 - a single magnetic field profile
        zTR1 - the location of the transition region for that model
    OUTPUT:
        reflgood - smoothed reflection coefficient profile
    EXTERNAL PACKAGES: numpy
    """
    init()
    zx = (rm/Rsun)- 1.0
    steps = len(zx)

    aucheck = abs(zx - zAU)
    iau = int(aucheck.argmin())
    TRcheck = abs(zx - zTR1)
    iTR = int(TRcheck.argmin())
    lowcheck = abs(zx - zlow)
    ilow = int(lowcheck.argmin())
    sscheck = abs(zx - zSS)
    iss = int(sscheck.argmin())

    zset = (0.00975, 0.011, 0.573, 0.315, 3.0)
    iset = np.zeros(5)
    for i in range(5):
        iset[i] = int(abs(zx-zset[i]).argmin())
    Bfit = np.zeros(5)
    for k in range(5):
        Bfit[k] = B1[iset[k]]

    arefl = np.zeros(6)
    fitrefl = np.zeros(6)
    arefl[0] = np.log10(Bfit[0]/(0.7+Bfit[0]))
    arefl[1] = -1.081+0.3108*np.log10(Bfit[1])
    arefl[2] = -1.293+0.6476*np.log10(Bfit[2])
    arefl[3] = -2.238+0.6061*np.log10(Bfit[3])
    arefl[4] = -2.940-0.2576*np.log10(Bfit[4])
    arefl[5] = -3.404-0.4961*np.log10(Bfit[4])
    for i in range(6):
        fitrefl[i] = 10**arefl[i]

    zfit = (zTR1,0.02, 0.2, 2.0, 20.0, 200.0)
    ifit = np.zeros(6)
    azfit = np.zeros(6)
    azx = np.zeros(steps)
    for k in range(steps):
        azx[k] = np.log10(zx[k])
    for i in range(6):
        ifit[i] = int(abs(zx-zfit[i]).argmin())
        azfit[i] = np.log10(zfit[i])

    refl1=np.zeros(steps)
    for k in range(steps):
        if zx[k] <= zTR1:
            refl1[k] = fitrefl[0] #reflection coeff. constant in chromo.
        if (zx[k] > zfit[0]) and (zx[k] <= zfit[1]):
            ay = arefl[0] + ((arefl[1]-arefl[0])/(azfit[1]-azfit[0])*
                             (azx[k]-azfit[0]))
            refl1[k] = 10**ay

        if (zx[k] > zfit[1]) and (zx[k] <= zfit[2]):
            ay = arefl[1] + ((arefl[2]-arefl[1])/(azfit[2]-azfit[1])*
                                              (azx[k]-azfit[1]))
            refl1[k] = 10**ay
        if (zx[k] > zfit[2]) and (zx[k] <= zfit[3]):
            ay = arefl[2] + ((arefl[3]-arefl[2])/(azfit[3]-azfit[2])*
                             (azx[k]-azfit[2]))
            refl1[k] = 10**ay
        if (zx[k] > zfit[3]) and (zx[k] <= zfit[4]):
            ay = arefl[3] + ((arefl[4]-arefl[3])/(azfit[4]-azfit[3])*
                             (azx[k]-azfit[3]))
            refl1[k] = 10**ay
        if (zx[k] > zfit[4]) and (zx[k] <= zfit[5]):
            ay = arefl[4] + ((arefl[5]-arefl[4])/(azfit[5]-azfit[4])*
                             (azx[k]-azfit[4]))
            refl1[k] = 10**ay
        if (zx[k] > zfit[5]):
            refl1[k] = fitrefl[5]
    reflgood = smooth(refl1[:],15)
    return reflgood

def fullRHS(r,models,steps,B,dBdr,T,dTdr,zTR,u):
    """
    PURPOSE: To find the full RHS of the momentum equation, defined
        below, which includes wave pressure and damping effects.
        {u(r) - [uc(r)**2/u(r)]}*(du/dr) = RHS
        RHS = gravterm + magucterm + tempaterm + alfterm + soundterm
        for U_s << U_A (see Cranmer et al. 2007, eq. 58)
    INPUTS:
        r - radius array where profiles are defined
        models - number of models in the current set
        steps - number of radii where profiles are defined i.e. len(r)
        B - magnetic field strength as a function of radius
        dBdr - derivative of B, also one dimensional for each model
        T - temperature profile as a function of radius for N models
        dTdr - derivative of T, also one dimensional for each model
        zTR - location of transition region in temperature profile
        u - previous outflow solution, used to determine density
    OUTPUT:
        ucr - critical speed profiles for all models
        rhs - profiles of the RHS for all models
    EXTERNAL PACKAGES: numpy
    """
    init()

    zx = (r/Rsun)-1.0
    rho = np.zeros((models,steps))
    VA = np.zeros((models,steps))
    vperp = np.zeros((models,steps))
    UA = np.zeros((models,steps))
    QA = np.zeros((models,steps))
    a = np.zeros((models,steps))
    ucr = np.zeros((models,steps))
    rhs = np.zeros((models,steps))
    tref = np.zeros((models,steps))
    teddy = np.zeros((models,steps))
    eff = np.zeros((models,steps))
    #mass flux conservation: rho(r) = (rhoTR*uTR/BTR)*(B(r)/u(r))
    iTR = np.zeros(models)
    if models == 1:
        #convert scalar variable to numpy array
        zTR1 = np.zeros(1)
        zTR1[0] = zTR
        zTR = zTR1.copy()
    for j in range(0,models):
        chromosphere = np.where(T[j,:] < 1.1*TTR)
        iTR[j] = chromosphere[0][len(chromosphere[0][:])-1]
        rhoTRexp = -21.904 - (3.349*np.log10(zTR[j]))
        TRcheck = abs(zx - zTR[j])
        iTR[j] = int(TRcheck.argmin())
        rho[j,iTR[j]] = 10**rhoTRexp # * 1.4?
        rho[j,:] = ((rho[j,iTR[j]]*u[j,iTR[j]]/B[j,iTR[j]])*
                    (B[j,:]/u[j,:]))

    #wave action conservation (Cranmer 2010, eq. 29):
    #   (u(r)+VA)**2 UA / (VA*B(r)) = constant, Sbase in init()
    limit = 10.0

    VA = B/np.sqrt(4*np.pi*rho)
    UA,QA = waveaction(r,B,zTR,u,rho,VA,Sbase,np.ones((models,steps)))

    vperp1 = np.sqrt(UA/rho)
    tref = ((r+Rsun)*(r-Rsun))/(r*VA)
    BBase = B[:,0]
    ellperp = ellbase*np.sqrt(BBase[:,None]/B)
    teddy = ((ellperp*np.sqrt(3*np.pi))/((1+(u/VA))*vperp1))
    eff = 1/(1+(teddy/tref))
    UA,QA = waveaction(r,B,zTR,u,rho,VA,Sbase,eff)
    vperp = np.sqrt(UA/rho)

    for j in range(0,models):
        for k in range(0,steps):
            if (r[k]/Rsun) < zTR[j]+1:
                xion = 0
            if (r[k]/Rsun) >= zTR[j]+1:
                xion = 1
            a[j,k] = np.sqrt((1+xion)*boltzk*T[j,k]/mH)
            MA = u[j,k]/VA[j,k]
            ucr[j,k] = np.sqrt(a[j,k]**2 + (UA[j,k]/(4*rho[j,k]))*
                            ((1+(3*MA))/(1+MA)))
            gravterm = -G*Msun/r[k]**2
            magucterm = -ucr[j,k]**2*(dBdr[j,k]/B[j,k])
            tempaterm = -a[j,k]**2*(dTdr[j,k]/T[j,k])
            alfterm = QA[j,k]/(2*rho[j,k]*(u[j,k]+VA[j,k]))
            soundterm = 0
            rhs[j,k] = (gravterm + magucterm + tempaterm
                        + alfterm + soundterm)

    np.savez(filename + '_fullRHS', rho=rho, UA=UA, vperp=vperp,
             ucr=ucr, rhs=rhs, eff=eff)
    return a,ucr,rhs

def waveaction(r,B,zTR,u,rho,VA,S0,eff):
    """
    PURPOSE: To determined the Alfven wave energy density and
        heating rate including wave action conservation with damping;
        For more on Alfven wave action conservation equation,
        see eq. 43 of Cranmer et al. (2007); see also Jacques (1977),
        Isenberg and Hollweg (1982), Tu & Marsch (1995)
    INPUTS:
        r - radius array where all profiles are defined
        B - magnetic field profiles for all models
        zTR - location of transition region for all models
        u - previous outflow solutions, consistent with density
        rho - mass density profiles (g cm^-3)
        VA - Alfven speed at all heights (cm s^-1)
        S0 - wave action conservation constant at base of photosphere
        eff - turbulent efficiency as a function of height
    OUTPUT:
        UAdamped - energy density of Alfven waves with damping effects
        QA - Alfven wave heating rate
    EXTERNAL PACKAGES: numpy
    """
    init()
    steps = len(r)
    zx = (r/Rsun)-1.0
    zm = r-Rsun
    fivecheck = abs(zx - 5)
    ifive = int(fivecheck.argmin())

    models = len(B[:,0])

    refl = np.zeros((models,steps))
    ell_perp = np.zeros((models,steps))
    for j in range(models):
        #Can only send one model through to fit_refl at a time.
        refl[j,:] = fit_refl(B[j,:],zTR[j],r)
    for i in range(steps):
        ell_perp[:,i] = ellbase*np.sqrt(B[:,0]/B[:,i])

    #S = (u+VA)**2*UA/(VA*B)
    #Can show that S**(-3/2)dS = RS*dr, where RS given by:
    alphatilde=2*eff*(refl*(1+refl)*(1+refl**2)**(-1.5))
    RS = ((-alphatilde/ell_perp)*(np.sqrt(B*VA/rho)/(u+VA)**2))

    UAdamped = np.zeros((models,steps))
    S = np.zeros((models,steps))
    QA = np.zeros((models,steps))
    intRS = np.zeros((models,steps))
    for j in range(models):
        intRS[j,0] = ((RS[j,1]+RS[j,0])/2)*(r[1]-r[0]) #
        for i in range(0,steps-1):
            dr = r[i+1]-r[i]
            intRS[j,i+1] = rk4(intRS[j,i],r[i],dr,r,dfdr=RS[j,:])
    S = ((1/np.sqrt(S0))-0.5*(intRS))**(-2)
    UAdamped = ((VA*S*B)/(u+VA)**2)
    QA = alphatilde*(rho*UAdamped)**0.5/ell_perp
    return UAdamped,QA

def outflows(r,nmods,nsteps,rhs,ucr):
    """
    PURPOSE: To find the correct critical point based on the zero of the
        RHS, where the integral of the RHS is at an absolute minumum
        (see Kopp & Holzer 1976). With critical point (located between
        icrit and icrit+1, find slope at critical location and solve
        out from critical point to get full outflow
    INPUTS:
        r - radius array where all profiles are defined
        nmods - number of models given
        nsteps - number of steps for each model
        rhs - rhs used to find critical points (where rhs is zero)
        ucr - critical speed profile, only = u(r) at true critical point
    OUTPUT:
        u - full outflow profile for solar wind
        locCrit - critical pt, given as height in Rsun above photosphere
    EXTERNAL PACKAGES: numpy
    """
    modArray = np.zeros(nsteps)
    modcmp = np.zeros(nsteps)
    rhscmp = np.zeros(nsteps)
    rootflag = np.zeros(nsteps)
    badflag=0
    icrit = np.zeros(nmods)

    F = np.zeros((nmods,nsteps))
    for j in range(0,nmods):
        F[j,0] = 1 #arbitrary amplitude
        fnow = F[j,0]
        for k in range(0,nsteps-1):
            rstart = r[k]
            dr = r[k+1]-r[k]
            fstart = fnow
            F[j,k+1] = rk4(fstart,rstart,dr,r[:],dfdr=rhs[j,:])
            fnow = F[j,k+1]
    #Find all roots of RHS
    for j in range(0,nmods):
        for k in range(1,nsteps-2):
            if ((np.sign(rhs[j,k]) != np.sign(rhs[j,k+1])) and
                (np.sign(rhs[j,k-1]) != np.sign(rhs[j,k+2]))):
                rootflag[k] = 1
        roots = np.where(rootflag > 0)
        if len(roots[0]) == 0:
            icrit[j] = -1
            print ('CAUTION: No critical point for model',j)
            badflag=1
        else: #Find the absolute minimum of F for all roots
            extrema = F[j,roots[0]]
            xpt = extrema.argmin()
            icrit[j] = roots[0][xpt]
    if badflag == 1:
        print ('indexCrit set to -1 for failed models')

    rCplus,uCplus,dUdrcplus = critSlope(r,nmods,nsteps,rhs,ucr,icrit+1)
    rCminus,uCminus,dUdrcminus = critSlope(r,nmods,nsteps,rhs,ucr,icrit)

    rC = np.zeros(nmods)
    uC = np.zeros(nmods)
    dUdrc = np.zeros((nmods,2))
    locCrit = np.zeros(nmods)
    u = np.zeros((nmods,nsteps))
    for j in range(0,nmods):
        rC[j] = (rCminus[j] + rCplus[j])/2.0
        uC[j] = (uCminus[j] + uCplus[j])/2.0
        dUdrc[j,0] = dUdrcminus[j]
        dUdrc[j,1] = dUdrcplus[j]
        if icrit[j] != -1:
            locCrit[j] = rC[j]-1.0
            u[j,:] = slope2curve(r,icrit[j],rC[j],uC[j],dUdrc[j,:],
                                 ucr[j,:],rhs[j,:])
    return u,locCrit

def critSlope(r,models,steps,rhs,ucr,indexcrit):
    """
    PURPOSE: Given the RHS and critical speed profile, find the slope
        of the solar wind outflow at the critical point using the
        following method:
        du/dr = N/D = 0/0 at critical point : L'Hoptial's Rule
        N = RHS from parkerRHS or fullRHS, D = u - (uC**2/u)
        du/dr = [dN/dr] / [dD/dr]
        where dD/dr = (du/dr) + [(uC/u)**2](du/dr) - (uC/u)*duc/dr)
                    = 2(du/dr) - duC/dr  at r=rC, u=uC
        du/dr = 0.5*(duC/dr + np.sqrt((duC/dr)**2 + 2*dN/dr))
    INPUTS:
        r - radius array where all profiles are defined
        models - number of models given
        steps - number of steps for each model
        rhs - rhs used to find critical points (where rhs is zero)
        ucr - critical speed profile, only = u(r) at true critical point
        indexcrit - location in rhs, ucr, r where the critical point lies
    OUTPUT:
        rC - critical radius (in cm), found by r[indexcrit]
        uC - crtical speed (in cm/s), found by ucr[indexcrit]
        dUdrc - slope of outflow at indexcrit
    EXTERNAL PACKAGES: numpy
    """
    dNdr = quickDeriv(rhs,r,models,steps)
    duCdr = quickDeriv(ucr,r,models,steps)
    rC = np.zeros(models)
    uC = np.zeros(models)
    dUdrc = np.zeros(models)
    dNdrC = np.zeros(models)
    for j in range(0,models):
        if indexcrit[j] != -1:
            uC[j] = ucr[j,indexcrit[j]]
            rC[j] = r[indexcrit[j]]
            dNdrC[j]=dNdr[j,indexcrit[j]]
            radicand =duCdr[j,indexcrit[j]]**2+(2.0*dNdrC[j])
            if radicand <= 0:
                radicand = 0
                print ('invalid value encountered in sqrt, set to 0')
            dUdrc[j] = (0.5*(duCdr[j,indexcrit[j]]+np.sqrt(radicand)))
    if models > 1:
        print ('range of slopes:',min(dUdrc),max(dUdrc))
    return rC,uC,dUdrc

def slope2curve(r,iC,rpt,upt,dUdrpt,ucrj,rhsj):
    """
    PURPOSE: To integrate out from critical point to get
        full outflow solution
    INPUTS:
        r - radius array where profiles are defined
        iC - index in r where critical radius occurs
        rpt - radius of "true" critical point (cm)
        upt - outflow speed of "true" critical point (cm s^-1)
        dUdrpt - slope of outflow of indicies on either side of critical radius
        ucrj - critical speed profile for model j
        rhsj - right hand side of momentum equation for model j
    OUTPUT:
        u - full solar wind outflow speed profile for model j
    EXTERNAL PACKAGES: numpy
    """
    #the "j" refers to a single model being considered
    npoints = len(r)
    iC = int(iC)
    u = np.zeros(npoints)

    u[iC] = upt + (r[iC] - rpt)*dUdrpt[0]
    u[iC+1] = upt + (r[iC+1] - rpt)*dUdrpt[1]

    u[iC-1] = u[iC] + (r[iC-1]-r[iC])*dUdrpt[0]
    u[iC+2] = u[iC+1] + (r[iC+2]-r[iC+1])*dUdrpt[1]

    for i in range(iC-1,0,-1):
        #loops down from iC-1 to 1 inclusive
        #populates u for iC-2 to 0, start of array
        dr = r[i-1]-r[i] # < 0
        u[i-1] = rk4(u[i],r[i],dr,r,dfdr=(ucrj,rhsj))
        if u[i-1] < 0:
            u[i-1] = u[i]
            print ('Negative value encountered (down), i=', i)

    for i in range(iC+2,npoints-1):
        #loops from iC+2 to npoints-2 inclusive
        #populates u for iC+3 to npoints-1, end of array
        dr = r[i+1]-r[i]
        u[i+1] = rk4(u[i],r[i],dr,r,dfdr=(ucrj,rhsj))
        if u[i+1] < 0:
            u[i+1] = u[i]
            print ('Negative value encountered (up), i=', i)
    return u

def upwindmapping(r,phi,nmodels,ubound):
    """
    PURPOSE: Following section 2.4 of Riley & Lionello (2011)
        to better explain the way that solar wind streams can
        interact from near the Sun to 1 AU.
    INPUTS:
        r - radius array where profiles are defined
        phi -
        nmodels -
        ubound -
    OUTPUT:
        u1au - speeds at 1AU for streams based on upwind model
    EXTERNAL PACKAGES: numpy
    """
    nsteps = len(r)                 # will use index i for r steps
        #step size should be limited by the Courant condition
    nangles = len(phi)              # will use index j for phi angles
    u=np.zeros((nsteps,nangles))

    #need to map boundary condition ubound to r,phi grid

    #upwind velocity stream mapping
    for i in range(nsteps-1):
        for j in range(nangles-1):
            u[i+1,j] = u[i,j] + (((r[i+1]-r[i])*omegarot/u[i,j])*
                                 ((u[i,j+1]-u[i,j])/(phi[j+1]-phi[j])))
    return u1au

if __name__ == '__main__':
    main()
