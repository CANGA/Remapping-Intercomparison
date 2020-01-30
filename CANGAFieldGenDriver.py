#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
NAME
    Global field generator for remapping intercomparison
PURPOSE
    Reads 2 mesh data files (Exodus or SCRIP) and evaluates any one of, or
    combination of 3 fields (TPW, Cloud Fraction, Terrain) derived from
    Spherical Harmonic expansions of satellite global composite data.
PROGRAMMER(S)
    Jorge Guerra, Paul Ullrich
REVISION HISTORY
    
REFERENCES
'''    
#%%
import shutil
import time
import sys, getopt
import pyshtools
import math as mt
import numpy as np
import plotly as py
import plotly.figure_factory as FF
from scipy.spatial import Delaunay
from netCDF4 import Dataset  # http://code.google.com/p/netcdf4-python/
from computeAreaIntegral import computeAreaIntegral, getGaussNodesWeights
import computeSphericalCartesianTransforms as sphcrt

import multiprocessing
from multiprocessing import Process
from itertools import repeat


#%% Utility functions

def computeSpectrum(ND, lfPower, hfPower, degIntersect):
       psd = np.zeros(ND)
       # Compute power spectrum array from coefficients (Power Law assumed)
       degs = np.arange(ND, dtype=float)
       #degs[0] = np.inf
       degs[0] = 1.0E-8
       
       # Check that we aren't fitting a constant function (Terrain)
       for ii in range(ND):
              if degs[ii] < degIntersect:
                     if lfPower[1] > -5.0:
                            psd[ii] = lfPower[0] * np.power(degs[ii], lfPower[1]) + lfPower[2]
                     else:
                            psd[ii] = lfPower[2]
              elif degs[ii] >= degIntersect:
                     if hfPower[1] > -5.0:
                            psd[ii] = hfPower[0] * np.power(degs[ii], hfPower[1]) + hfPower[2]
                     else:
                            psd[ii] = hfPower[2]
                            
       return degs, psd

def computeCentroids(varCon, varCoord):
       # Loop over cells and get centroid vectors
       NC = np.size(varCon, axis=0)
       NP = np.size(varCon, axis=1)
       cellCoord = np.zeros((NC, 3))
       for ii in range(NC):
              # Centroid by averaging corner sphere-center vectors
              centroid = np.mat([0.0, 0.0, 0.0])
              for pp in range(NP):
                     ndex = varCon[ii,pp] - 1
                     centroid += varCoord[:,ndex]
                     
              centroid *= 1.0 / NP
       
              # Renormalize the centroid vector
              RO = np.linalg.norm(centroid)
              centroid *= 1.0 / RO
              
              # Store this centroid
              cellCoord[ii,:] = centroid 
       
       return cellCoord

def computeCentroidsLL(conLon, conLat):
       # Loop over rows of the corner array and get centroid
       NC = np.size(conLon, axis=0)
       NP = np.size(conLon, axis=1)
       cellCoord = np.zeros((NC, 2))
       for ii in range(NC):
              # Centroid by averaging corner sphere-center vectors
              centroid = np.mat([0.0, 0.0])
              for pp in range(NP):
                     centroid += [conLon[ii,pp], conLat[ii,pp]]
                     
              centroid *= 1.0 / NP
              
              # Store this centroid
              cellCoord[ii,:] = centroid 
       
       return cellCoord

def computeCellAverage(clm, varCon, varCoord, order, avg):
       # Compute the number of cells and initialize
       NEL = np.size(varCon, 0)
       varSample = np.zeros(NEL,)
       
       GN, GW = getGaussNodesWeights(order)
       # Loop over each cell and get cell average
       pool = multiprocessing.Pool(processes=10)
       results = pool.starmap(computeAreaIntegral, zip(repeat(clm), [varCoord[:,np.unique(varCon[ii,:]) - 1] for ii in range(NEL)], repeat(GN), repeat(GW), repeat(avg), repeat(False)))
       pool.close()
       pool.join()
       varSample=np.array(results, dtype='f8')
       #for i in range(NEL):
       #       varSample[i] = computeAreaIntegral(clm, varCoord[:,np.unique(varCon[i,:]) - 1], GN, GW, order, avg, False)
       
       return varSample

def computeRandomizedCoefficients(ND):
       # Initialize the coefficients array
       coeffs = np.zeros((2,ND,ND))
       
       # Set the random integer seed
       seed = 384
       
       # Loop over ND (number of degrees)
       for kk in range(ND):
              nrand = np.ones((2, kk+1))
              # Initialize random numbers with number of coefficients at this degree 
              if kk == 0:
                     rand = (1103515245 * seed + 25214903917 + 12345) % 2147483647
              # Loop over the coefficients at this degree
              for ll in range(0, kk+1):
                     nrand[0,ll] = rand
                     rand = (1103515245 * rand + 25214903917 + 12345) % 2147483647
                     nrand[1,ll] = rand
                     rand = (1103515245 * rand + 25214903917 + 12345) % 2147483647
         
              # Turn the random set into double
              nrand = np.multiply(nrand, 1.0 / 2147483647.0)
              
              # Set the coefficients at degree kk+1
              coeffs[:2,kk,:kk+1] = 2.0 * np.add(2.0 * nrand[:2,:], -1.0)
              
       return coeffs

def computeNormalizedCoefficients(N, psd, coeffsLD):
       # Initialize SHCoeffs with a randomized realization of coefficients
       clm = pyshtools.SHCoeffs.from_random(psd, seed=384)

       # Compute the randomized coefficients and update instance of SHCoeffs
       clm.coeffs = computeRandomizedCoefficients(ND)
       
       # Force the coefficients to have the same power as the given spectrum
       power_per_l = pyshtools.spectralanalysis.spectrum(clm.coeffs, normalization='4pi', unit='per_l')
       clm.coeffs *= np.sqrt(psd[0:ND] * np.reciprocal(power_per_l))[np.newaxis, :, np.newaxis]
       
       # Combine the coefficients, low degree from data and high degree randomized
       clm.coeffs[0,0:4,0:4] = coeffsLD
       
       # Returns the SH coefficients object
       return clm

# Parse the command line
def parseCommandLine(argv):
       
       # Mesh information files
       sampleMesh = ''
       ExodusSingleConn = False
       SCRIPwithoutConn = False
       SCRIPwithConn = False
       SpectralElement = False
       
       # Sampling order
       sampleCentroid = False
       sampleOrder = 4
       
       # SET WHICH FIELDS TO EVALUATE
       EvaluateAll = False
       EvaluateTPW = False # Total Precipitable Water
       EvaluateCFR = False # Global Cloud Fraction
       EvaluateTPO = False # Global topography
       
       # Number of modes used up to 512
       numModes = 128
       
       # Pseudo-random number generator seed
       seed = 384
       
       try:
              opts, args = getopt.getopt(argv, 'hv:', \
                                        ['pm=', 'so=', 'nm=', 'rseed=', 'EvaluateAll', \
                                         'EvaluateTPW', 'EvaluateCFR', 'EvaluateTPO', \
                                         'ExodusSingleConn', 'SCRIPwithoutConn', \
                                         'SCRIPwithConn', 'SpectralElement'])
       except getopt.GetoptError:
              print('Command line not properly set:', \
                    'CANGAFieldGenDriver.py', \
                    '--pm <sampleMeshFile>', \
                    '--so <sampleOrderInteger>', \
                    '--nm <numberSHModesMax768>', \
                    '--rseed <randnumSeed>', \
                    '--<evaluateAllFields>', \
                    '--<evaluateTotalPrecipWater>', \
                    '--<evaluateCloudFraction>', \
                    '--<evaluateGlobalTerrain>', \
                    '--<meshConfiguration>', \
                    '--<isSpectralElementMesh>')
              sys.exit(2)
              
       for opt, arg in opts:
              # Request for usage help
              if opt == '-h':
                     print('Command line not properly set:', \
                           'CANGAFieldGenDriver.py', \
                           '--pm <sampleMeshFile>', \
                           '--so <sampleOrderInteger>', \
                           '--nm <numberSHModesMax768>', \
                           '--rseed <randnumSeed>', \
                           '--<evaluateAllFields>', \
                           '--<evaluateTotalPrecipWater>', \
                           '--<evaluateCloudFraction>', \
                           '--<evaluateGlobalTerrain>', \
                           '--<meshConfiguration>', \
                           '--<isSpectralElementMesh>')
                     sys.exit()
              elif opt == '--pm':
                     sampleMesh = arg
              elif opt == '--so':
                     if int(arg) == 1:
                            sampleCentroid = True
                     else:
                            if int(arg)%2 == 0 and int(arg) < 200:
                                sampleOrder = int(arg)
                            else:
                                sys.exit("[FATAL] Error in option passed for --so. Sample order must be \in (0, 200)")
              elif opt == '--nm':
                     numModes = int(arg)
              elif opt == '--rseed':
                     seed = int(arg)
              elif opt == '--EvaluateAll':
                     EvaluateAll = True
              elif opt == '--EvaluateTPW':
                     EvaluateTPW = True
              elif opt == '--EvaluateCFR':
                     EvaluateCFR = True
              elif opt == '--EvaluateTPO':
                     EvaluateTPO = True
              elif opt == '--ExodusSingleConn':
                     ExodusSingleConn = True
              elif opt == '--SCRIPwithoutConn':
                     SCRIPwithoutConn = True
              elif opt == '--SCRIPwithConn':
                     SCRIPwithConn = True
              elif opt == '--SpectralElement':
                     SpectralElement = True
                     
       # Check that the number of modes requested doesn't exceed 512
       if numModes > 512:
              print('Setting maximum number of expansion modes: 512.')
              numModes = 512

       # Check that only one configuration is chosen
       if (ExodusSingleConn == True) & (SCRIPwithoutConn == True):
              print('Expecting only ONE mesh configuration option!')
              print('Multiple options are set.')
              sys.exit(2)
       elif (ExodusSingleConn == True) & (SCRIPwithConn == True):
              print('Expecting only ONE mesh configuration option!')
              print('Multiple options are set.')
              sys.exit(2)
       elif (SCRIPwithoutConn == True) & (SCRIPwithConn == True):
              print('Expecting only ONE mesh configuration option!')
              print('Multiple options are set.')
              sys.exit(2)
       elif (ExodusSingleConn == True) & (SCRIPwithoutConn == True) & (SCRIPwithConn == True):
              print('Expecting only ONE mesh configuration option!')
              print('Multiple options are set.')
              sys.exit(2)
       elif (ExodusSingleConn == False) & (SCRIPwithoutConn == False) & (SCRIPwithConn == False):
              print('ONE mesh configuration option must be set!')
              print('None of the options are set.')
              sys.exit(2)

       if 2*sampleOrder-1 < numModes:
           print("WARNING: The quadrature sampling order of %d is insufficient to exactly integrate SPH expansions of order %d!" % (sampleOrder, numModes))

       return sampleMesh, numModes, seed, \
              sampleCentroid, sampleOrder, \
              EvaluateAll, EvaluateTPW, EvaluateCFR, EvaluateTPO, \
              ExodusSingleConn, SCRIPwithoutConn, SCRIPwithConn, SpectralElement

if __name__ == '__main__':
       print('Welcome to CANGA remapping intercomparison field generator!')
       print('Authors: Jorge Guerra, Vijay Mahadevan, Paul Ullrich, 2019')
       
       # Parse the commandline! COMMENT OUT TO RUN IN IDE
       mesh_file, ND, seed, sampleCentroid, sampleOrder, \
       EvaluateAll, EvaluateTPW, EvaluateCFR, EvaluateTPO, \
       ExodusSingleConn, SCRIPwithoutConn, SCRIPwithConn, SpectralElement \
       = parseCommandLine(sys.argv[1:])
       
       # Set the name for the new data file
       stripDir = mesh_file.split('/')
       onlyFilename = stripDir[len(stripDir)-1]
       data_file = 'testdata_NM' + str(ND) + '_' + (onlyFilename.split('.'))[0]

       print('New data will be stored in (prefix): ', data_file)
       print('Number of SH degrees for sampling set to: ', ND)
       print('Maximum Gaussian quadrature order to be used: ', 2*sampleOrder-1)
       
       if ExodusSingleConn:
              
              if SpectralElement:
                     connCell = 'element_gll_conn'
                     coordCell = 'grid_gll_cart'
              else:
                     connCell = 'connect1'
                     coordCell = 'coord'
                     
              # Open the .g mesh files for reading
              m_fid = Dataset(mesh_file)
              
              # Get connectivity and coordinate arrays (check for multiple connectivity)
              varCon = m_fid.variables[connCell][:]
              varCoord = m_fid.variables[coordCell][:]
              
              # Get the rectilinear attribute if available
              try:
                     print('Rectilinear mesh detected; field variable written as 2D')
                     rectilinear = m_fid.rectilinear
                     # Get the 2D size of the field array from mesh file
                     NLON = m_fid.rectilinear_dim1_size
                     NLAT = m_fid.rectilinear_dim0_size
              except:
                     print('NOT a rectilinear mesh.')
                     rectilinear = False
              
              
       elif SCRIPwithoutConn:
              numEdges = 'grid_corners'
              numCells = 'grid_size'
              numDims = 'cart_dims'
              numVerts = 'grid_corners_size'
              
              if SpectralElement:
                     connCell = 'element_gll_conn'
                     coordCell = 'grid_gll_cart'
              else:
                     connCell = 'element_corners_id'
                     coordCell = 'grid_corners_cart'
              
              # Open the .nc SCRIP files for reading
              m_fid = Dataset(mesh_file, 'a')
                   
              start = time.time()
              try:
                     print('Reading connectivity and coordinate arrays from raw SCRIP')
                     varCon = m_fid.variables[connCell][:]
                     varCoord = m_fid.variables[coordCell][:]
              except:
                     print('PRE-PROCESSING NOT DONE ON THIS MESH FILE!')
              
              endt = time.time()
              print('Time to read SCRIP mesh info (sec): ', endt - start)
              
       elif SCRIPwithConn:
              numEdges = 'ncorners'
              numCells = 'ncells'
              numDims = 'cart_dims'
              
              if SpectralElement:
                     connCell = 'element_gll_conn'
                     coordCell = 'grid_gll_cart'
              else:
                     connCell = 'element_corners'
                     coordCell = 'grid_corners_cart' 
              
              # Open the .nc SCRIP files for reading
              m_fid = Dataset(mesh_file, 'a')
              
              # Get the list of available variables
              varList = m_fid.variables.keys()
              
              # Get RAW (no ID) connectivity and coordinate arrays
              varCon = m_fid.variables[connCell][:]
              varCon = varCon.T
              
              start = time.time()
              try:
                     print('Reading coordinate arrays from raw SCRIP')
                     varCoord = m_fid.variables[coordCell][:]
              except:
                     print('PRE-PROCESSING NOT DONE ON THIS MESH FILE!')
              
              endt = time.time()
              print('Time to read SCRIP mesh info (sec): ', endt - start)
       
       if SpectralElement:
              # Compute Lon/Lat coordinates from GLL nodes
              varLonLat = sphcrt.computeCart2LL(varCoord.T)
       else:
              # Compute Lon/Lat coordinates from centroids
              varCent = computeCentroids(varCon, varCoord)
              varLonLat = sphcrt.computeCart2LL(varCent)
       
       # Convert to degrees from radians
       varLonLat_deg = 180.0 / mt.pi * varLonLat
       varLonLat_deg = 180.0 / mt.pi * varLonLat
       
       m_fid.close()

       # Define our global variables for fields
       TPWvar = np.zeros(3)
       CFRvar = np.zeros(3)
       TPOvar = np.zeros(3)

       #%% Begin the SH reconstructions
       def Evaluate_TPW_Field():
              start = time.time()
              print('Computing Total Precipitable Water on sampling mesh...')
              # Set the power spectrum coefficients
              lfPower = [5.84729561e+04, -2.91678103e-04, -5.83966265e+04]
              hfPower = [2.17936330e+02, -1.99788552e+00, -7.94469251e-04]
              degIntersect = 1.8161917668847762
              # Compute the parent power spectrum for TPW
              degsTPW, psdTPW = computeSpectrum(ND, lfPower, hfPower, degIntersect)

              # Set the low degree coefficients (large scale structures)
              coeffsLD_TPW = np.array([[2.45709150e+01, 0.0, 0.0, 0.0], \
                              [4.00222122e+00, 2.39412571e+00, 0.0, 0.0], \
                              [-1.36433589e+01, 3.90520866e-03, 4.70350344e-01, 0.0], \
                              [-3.54931720e+00, -1.23629157e+00, 4.01454924e-01, 1.76782768e+00]])
              
              # Make the SH coefficients object for this field
              clmTPW = computeNormalizedCoefficients(ND, psdTPW, coeffsLD_TPW)
              
              # THIS NEEDS TO CHANGE TO SUPPORT FE GRIDS
              # Expand the coefficients and check the field
              if sampleCentroid or SpectralElement:              
                     TPWvar = clmTPW.expand(lon=varLonLat_deg[:,0], lat=varLonLat_deg[:,1])
              else:
                     TPWvar = computeCellAverage(clmTPW, varCon, varCoord, sampleOrder, True)
              
              # Compute rescaled data from 0.0 to max
              minTPW = np.amin(TPWvar)
              maxTPW = np.amax(TPWvar)
              deltaTPW = abs(maxTPW - minTPW)
              TPWvar = np.add(TPWvar, -minTPW)
              TPWvar *= maxTPW / deltaTPW
              endt = time.time()
              print('Time to compute TPW (mm): ', endt - start)

              return_dict['TPWvar'] = TPWvar
              #return TPWvar

       #%%
       def Evaluate_CFR_Field():
              start = time.time()
              print('Computing Cloud Fraction on sampling mesh...')
              # Set the power spectrum coefficients
              lfPower = [8.38954430e+00, -1.85962382e-04, -8.38439294e+00]
              hfPower = [1.25594628e-01, -1.99203168e+00,  1.91763519e-06]
              degIntersect = 8.322269484619733
              # Compute the parent power spectrum for CFR
              degsCFR, psdCFR = computeSpectrum(ND, lfPower, hfPower, degIntersect)
              
              # Set the low degree coefficients (large scale structures)
              coeffsLD_CFR = np.array([[6.65795054e-01, 0.0, 0.0, 0.0], \
                              [-2.45480409e-02, 2.24697424e-02, 0.0, 0.0], \
                              [5.72322008e-02, 3.41184683e-02, -7.71082815e-03, 0.0], \
                              [1.86562455e-02, 4.34697733e-04, 8.91735978e-03, -5.53756958e-03]])
       
              # Make the SH coefficients object for this field
              clmCFR = computeNormalizedCoefficients(ND, psdCFR, coeffsLD_CFR)
              
              # THIS NEEDS TO CHANGE TO SUPPORT FE GRIDS
              # Expand the coefficients and check the field
              if sampleCentroid or SpectralElement:              
                     CFRvar = clmCFR.expand(lon=varLonLat_deg[:,0], lat=varLonLat_deg[:,1])
              else:
                     CFRvar = computeCellAverage(clmCFR, varCon, varCoord, sampleOrder, True)
 
              # Compute rescaled data from 0.0 to max
              minCFR = np.amin(CFRvar)
              maxCFR = np.amax(CFRvar)
              deltaCFR = abs(maxCFR - minCFR)
              CFRvar = np.add(CFRvar, -minCFR)
              CFRvar *= maxCFR / deltaCFR
              #  Set all values greater than 1.0 to 1.0 (creates discontinuities)
              CFRvar[CFRvar >= 1.0] = 1.0
              
              endt = time.time()
              print('Time to compute CFR (0.0 to 1.0): ', endt - start)

              return_dict['CFRvar'] = CFRvar
              #return CFRvar

       #%%
       def Evaluate_TPO_Field():
              start = time.time()
              print('Computing Terrain on sampling mesh...')
              # Set the power spectrum coefficients
              lfPower = [1.79242815e+05, -4.28193211e+01,  7.68040558e+05]
              hfPower = [9.56198160e+06, -1.85485966e+00, -2.63553217e+01]
              degIntersect = 3.8942282772035255
              # Compute the parent power spectrum for CFR
              degsTPO, psdTPO = computeSpectrum(ND, lfPower, hfPower, degIntersect)
              
              # Set the low degree coefficients (large scale structures)
              coeffsLD_TPO = np.array([[-2.38452711e+03, 0.0, 0.0, 0.0], \
                              [-6.47223253e+02, -6.06453097e+02, 0.0, 0.0], \
                              [5.67394318e+02, 3.32672611e+02, -4.17639577e+02, 0.0], \
                              [1.57403492e+02, 1.52896988e+02, 4.47106726e+02, -1.40553447e+02]])
                         
              # Make the SH coefficients object for this field
              clmTPO = computeNormalizedCoefficients(ND, psdTPO, coeffsLD_TPO)
              
              # THIS NEEDS TO CHANGE TO SUPPORT FE GRIDS
              # Expand the coefficients and check the field
              if sampleCentroid or SpectralElement:              
                     TPOvar = clmTPO.expand(lon=varLonLat_deg[:,0], lat=varLonLat_deg[:,1])
              else:
                     TPOvar = computeCellAverage(clmTPO, varCon, varCoord, sampleOrder, True)
              
              # Rescale to -1.0 to 1.0
              minTPO = np.amin(TPOvar)
              maxTPO = np.amax(TPOvar)
              deltaTPO = abs(maxTPO - minTPO)
              TPOvar = np.add(TPOvar, -0.5 * (maxTPO + minTPO))
              TPOvar *= 2.0 / deltaTPO
              
              # Rescale topography to real Earth max/min
              minTPO = -10994.0 # Depth at Challenger Deep
              maxTPO = 8848.0 # Elevation of Mt. Everest ASL
              deltaTPO = abs(maxTPO - minTPO)
              TPOvar *= (0.5 * deltaTPO)
              TPOvar += 0.5 * (maxTPO + minTPO)
              
              endt = time.time()
              print('Time to compute TPO (m): ', endt - start)

              return_dict['TPOvar'] = TPOvar
              #return TPOvar

       #%%

       def runInParallel(*fns):
              proc = []
              for fn in fns:
                     p = Process(target=fn)
                     p.start()
                     proc.append(p)
              for p in proc:
                     p.join()

       #%%

       if EvaluateAll:
              manager = multiprocessing.Manager()
              return_dict = manager.dict()
              jobs = []
              for fn in [Evaluate_TPW_Field, Evaluate_CFR_Field, Evaluate_TPO_Field]:
                     p = Process(target=fn)
                     jobs.append(p)
                     p.start()
              for p in jobs:
                     p.join()
              
              TPWvar = return_dict['TPWvar']
              CFRvar = return_dict['CFRvar']
              TPOvar = return_dict['TPOvar']
              # runInParallel(Evaluate_TPW_Field, Evaluate_CFR_Field, Evaluate_TPO_Field)
              #TPWvar = Evaluate_TPW_Field()
              #CFRvar = Evaluate_CFR_Field()
              #TPOvar = Evaluate_TPO_Field()
       else:
              manager = multiprocessing.Manager()
              return_dict = manager.dict()
              jobs = []
              fn_list = list()
              if (EvaluateTPW): 
                      fn_list.append(Evaluate_TPW_Field)
              if (EvaluateCFR):
                      fn_list.append(Evaluate_CFR_Field)
              if (EvaluateTPO):
                      fn_list.append(Evaluate_TPO_Field)
              for fn in fn_list:
                     p = Process(target=fn)
                     jobs.append(p)
                     p.start()
              for p in jobs:
                     p.join()

              if (EvaluateTPW): 
                     TPWvar = return_dict['TPWvar']
                     #TPWvar = Evaluate_TPW_Field()
              if (EvaluateCFR):
                     CFRvar = return_dict['CFRvar']
                     #CFRvar = Evaluate_CFR_Field()
              if (EvaluateTPO):
                     TPOvar = return_dict['TPOvar']
                     #TPOvar = Evaluate_TPO_Field()
              
       #%% Copy grid files and store the new test data (source and target)
       outFileName = data_file
       
       if SpectralElement:
              outFileName = outFileName + 'GLL'
       
       if EvaluateAll:
              outFileName = outFileName + '_TPW_CFR_TPO.nc'
       elif EvaluateTPW:
              outFileName = outFileName + '_TPW.nc'
       elif EvaluateCFR:
              outFileName = outFileName + '_CFR.nc'
       elif EvaluateTPO:
              outFileName = outFileName + '_TPO.nc'
       else:
              outFileName = outFileName + '.nc'
              
       shutil.copy(mesh_file, outFileName)
       
       # write lon, lat, and test data variables
       data_fid = Dataset(outFileName, 'a')
       
       # Set the dimension name depending on the mesh file format
       if ExodusSingleConn:
              numCells = 'num_el_in_blk1'
       elif SCRIPwithoutConn:
              numCells = 'grid_size'
       elif SCRIPwithConn:
              numCells = 'ncells'
              
       if SpectralElement:
              numCells = 'grid_gll_size'
              
       # Process the sampling file
       if SCRIPwithConn:
              lonNC = data_fid.createVariable('nlon', 'f8', (numCells,))
              lonNC[:] = varLonLat_deg[:,0]
              latNC = data_fid.createVariable('nlat', 'f8', (numCells,))
              latNC[:] = varLonLat_deg[:,1]
       else:
              lonNC = data_fid.createVariable('lon', 'f8', (numCells,))
              lonNC[:] = varLonLat_deg[:,0]
              latNC = data_fid.createVariable('lat', 'f8', (numCells,))
              latNC[:] = varLonLat_deg[:,1]
       
       if rectilinear:
              slon = 'lonDim'
              slat = 'latDim'
              data_fid.createDimension(slon, NLON)
              data_fid.createDimension(slat, NLAT)
              
              if EvaluateTPW or EvaluateAll:
                     TPWNC = data_fid.createVariable('TotalPrecipWater', 'f8', (slat, slon))
                     field = np.reshape(TPWvar, (NLAT, NLON))
                     TPWNC[:] = field
              if EvaluateCFR or EvaluateAll:
                     CFRNC = data_fid.createVariable('CloudFraction', 'f8', (slat, slon))
                     field = np.reshape(CFRvar, (NLAT, NLON))
                     CFRNC[:] = field
              if EvaluateTPO or EvaluateAll:
                     TPONC = data_fid.createVariable('Topography', 'f8', (slat, slon))
                     field = np.reshape(TPOvar, (NLAT, NLON))
                     TPONC[:] = field
       else:
              if EvaluateTPW or EvaluateAll:
                     TPWNC = data_fid.createVariable('TotalPrecipWater', 'f8', (numCells,))
                     TPWNC[:] = TPWvar
              if EvaluateCFR or EvaluateAll:
                     CFRNC = data_fid.createVariable('CloudFraction', 'f8', (numCells,))
                     CFRNC[:] = CFRvar
              if EvaluateTPO or EvaluateAll:
                     TPONC = data_fid.createVariable('Topography', 'f8', (numCells,))
                     TPONC[:] = TPOvar
       
       # Close the files out.
       data_fid.close()

       #'''
       #%% Check the data with triangular surface plot
       points2D = varLonLat
       tri = Delaunay(points2D)
       simplices = tri.simplices       
       
       #%% Plot Total Precipitable Water
       if EvaluateTPW or EvaluateAll:
              fig1 = FF.create_trisurf(x=varLonLat[:,0], y=varLonLat[:,1], z=TPWvar, height=800, width=1200, \
                                       simplices=simplices, colormap="Portland", plot_edges=False, \
                                       title="Total Precipitable Water Check (mm)", aspectratio=dict(x=1, y=1, z=0.3))
              py.offline.plot(fig1, filename='TPW' + data_file + '.html')
       #%% Plot Cloud Fraction
       if EvaluateCFR or EvaluateAll:
              fig1 = FF.create_trisurf(x=varLonLat[:,0], y=varLonLat[:,1], z=CFRvar, height=800, width=1200, \
                                       simplices=simplices, colormap="Portland", plot_edges=False, \
                                       title="Cloud Fraction Check (0.0-1.0)", aspectratio=dict(x=1, y=1, z=0.3))
              py.offline.plot(fig1, filename='CFR' + data_file + '.html')
       #%% Plot Topography
       if EvaluateTPO or EvaluateAll:
              fig1 = FF.create_trisurf(x=varLonLat[:,0], y=varLonLat[:,1], z=TPOvar, height=800, width=1200, \
                                       simplices=simplices, colormap="Portland", plot_edges=False, \
                                       title="Global Topography (m)", aspectratio=dict(x=1, y=1, z=0.3))
              py.offline.plot(fig1, filename='TPO' + data_file + '.html')
       #'''
       #%% Check the evaluated spectra
       '''
       fig, (ax0, ax1, ax2) = plt.subplots(nrows=3, figsize=(12, 10), tight_layout=True)
       # Plot the TPW spectrum
       newPSD = pyshtools.spectralanalysis.spectrum(clmTPW.coeffs, unit='per_l')
       ax0.plot(degsTPW, psdTPW, 'k')
       ax0.plot(degsTPW, newPSD, 'r--')
       ax0.set_title('Total Precipitable Water - Evaluated PSD')
       ax0.set(yscale='log', xscale='log', ylabel='Power')
       ax0.grid(b=True, which='both', axis='both')
       # Plot the Cloud Fraction spectrum
       newPSD = pyshtools.spectralanalysis.spectrum(clmCFR.coeffs, unit='per_l')
       ax1.plot(degsCFR, psdCFR, 'k')
       ax1.plot(degsCFR, newPSD, 'r--')
       ax1.set_title('Global Cloud Fraction - Evaluated PSD')
       ax1.set(yscale='log', xscale='log', ylabel='Power')
       ax1.grid(b=True, which='both', axis='both')
       # Plot the Topography spectrum
       newPSD = pyshtools.spectralanalysis.spectrum(clmTPO.coeffs, unit='per_l')
       ax2.plot(degsTPO, psdTPO, 'k')
       ax2.plot(degsTPO, newPSD, 'r--')
       ax2.set_title('Global Topography Data - Evaluated PSD')
       ax2.set(yscale='log', xscale='log', xlabel='Spherical harmonic degree', ylabel='Power')
       ax2.grid(b=True, which='both', axis='both')
       plt.show()
       '''      
