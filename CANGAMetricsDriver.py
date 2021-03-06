#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
NAME
    NetCDF reader and CANGA intercomparison with Python
PURPOSE
    Reads 3 NetCDF files containing model output (identical variables) and
    computes regridding metrics. Also takes mesh data from Exodus or SCRIP.
PROGRAMMER(S)
    Jorge Guerra, Paul Ullrich, Vijay Mahadevan
REVISION HISTORY

REQUIREMENTS
    Input Specifications:
       - sm: source mesh file
       - tm: target mesh file
       - data: field data file
       - src_fields: field names (as variables) in field data file on source mesh
       - tgt_fields: field names (as variables) in field data file on target mesh
       - iterations: maximum dimensionality in 2-D space (number of remap iterations)
    Output:
       - Computed metrics as a table

USAGE
       python CANGAMetricsDriver.py \
              --ss testdata_outCSMesh_ne16_TPW_CFR_TPO.nc \
              --st testdata_outICODMesh_ne16_TPW_CFR_TPO.nc \
              --smc 1 --tmc 1 \
              --data OutputRemapFields-1-CS16-CVT16.nc \
              --field Topography \
              --dimension 2
    
REFERENCES
'''    
#%%
import sys, getopt
import time
import numpy as np
import pandas as pd
from netCDF4 import Dataset  # http://code.google.com/p/netcdf4-python/

# Bring in all the different metric modules
from computeGradientSE import computeGradientSE
from computeGradientFV2 import computeGradientFV2
# from computeGradientFV3 import computeGradientFV3
from computeGradientFV3 import ComputeGradientFV
from computeGlobalConservation import computeGlobalConservation
#from computeLocalityMetric import computeLocalityMetric
from computeStandardNorms import computeStandardNorms
from computeGlobalExtremaMetrics import computeGlobalExtremaMetrics
from computeLocalExtremaMetrics import computeLocalExtremaMetrics
from computeAreaIntegral import computeAreaIntegral
from computeGradientPreserveMetrics import computeGradientPreserveMetrics

import multiprocessing
from multiprocessing import Process
from itertools import repeat

# Parse the command line
def parseCommandLine(argv):

       return sourceSampledFile, targetSampledFile, \
              sourceMeshConfig, targetMeshConfig, \
              fieldName, fieldDataFile, \
              isSourceSpectralElementMesh, isTargetSpectralElementMesh, \
              maxRemapIterations
              
# Print iterations progress
def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█'):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)

    #bar = fill * filledLength + '-' * (length - filledLength)
    bar = '+' * filledLength + '_' * (length - filledLength)

    sys.stdout.write('\r%s |%s| %s%s %s' % (prefix, bar, percent, '%', suffix)),

    if iteration == total:
        sys.stdout.write('\n')
    sys.stdout.flush()


def loadMeshData(mesh_file, mesh_config, SpectralElement):
       
       if mesh_config == 1:
              numCells = 'num_el_in_blk1'
              numDims = 'cart_dims'
              numVerts = ''
              
              if SpectralElement:
                     connCell = 'element_gll_conn'
                     coordCell = 'grid_gll_cart'
              else:
                     connCell = 'connect1'
                     coordCell = 'coord'
              
              # Open the .g mesh files for reading
              m_fid = Dataset(mesh_file, 'r')
              
              # Get connectivity and coordinate arrays (check for multiple connectivity)
              varConn = m_fid.variables[connCell][:]
              varCoord = m_fid.variables[coordCell][:]
              
       elif mesh_config == 2:
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
              m_fid = Dataset(mesh_file, 'r')
                    
              start = time.time()
              try:
                     print('Reading coordinate and connectivity from augmented SCRIP')
                     varConn = m_fid.variables[connCell][:]
                     varCoord = m_fid.variables[coordCell][:]
              except:
                     print('PRE-PROCESSING NOT DONE ON THIS SCRIP MESH FILE!')
                     sys.exit()
              
              endt = time.time()
              print('Time to read SCRIP mesh info (sec): ', endt - start)
       
       elif mesh_config == 3:
              numCells = 'ncells'
              numDims = 'cart_dims'
              numVerts = ''
              
              if SpectralElement:
                     connCell = 'element_gll_conn'
                     coordCell = 'grid_gll_cart'
              else:
                     connCell = 'element_corners'
                     coordCell = 'grid_corners_cart' 
              
              # Open the .nc SCRIP files for reading
              m_fid = Dataset(mesh_file, 'r')
              
              # Get connectivity and coordinate arrays
              varConn = m_fid.variables[connCell][:]
              varConn = varConn.T
                     
              start = time.time()
              try:
                     print('Reading coordinate and connectivity from augmented SCRIP')
                     varCoord = m_fid.variables[coordCell][:]
              except:
                     print('PRE-PROCESSING NOT DONE ON THIS SCRIP MESH FILE!')
                     sys.exit()
              
              endt = time.time()
              print('Time to read SCRIP mesh info (sec): ', endt - start)
              
       elif mesh_config == 4:
              numCells = 'num_el_in_blk0'
              numDims = 'cart_dims'
              numVerts = ''
              
              if SpectralElement:
                     connCell = 'element_gll_conn'
                     coordCell = 'grid_gll_cart'
              else:
                     connCell = 'connect0'
                     coordCell = 'coord'
              
              # Open the .g mesh files for reading
              m_fid = Dataset(mesh_file, 'r')
              
              # Get connectivity and coordinate arrays (check for multiple connectivity)
              varConn = m_fid.variables[connCell][:]
              varCoord = m_fid.variables[coordCell][:]
              
       m_fid.close()
       
       return varCoord, varConn, numCells, numDims, numVerts

def loadMeshAreas(mesh_file, varAreaName, varCon, varCoord):
       start = time.time()
       print('Reading mesh areas...')
              
       m_fid = Dataset(mesh_file, 'r')
       # Check for existing variable data
       try:
              if m_fid.variables[varAreaName].name == varAreaName:
                     areas = m_fid.variables[varAreaName][:]
       
       except:
              print('PRE-PROCESSING FOR AREAS NOT DONE ON TARGET MESH FILE! Computing now.')
              NEL = len(varCon)
              area = np.zeros((NEL,1))
              for ii in range(NEL):
                     cdex = varCon[ii,:] - 1
                     thisCell = varCoord[:,cdex]
                     area[ii] = computeAreaIntegral(None, thisCell, 6, False, True)
                     
              area = np.ravel(area)
              meshFileOut = m_fid.createVariable(varAreaName, 'f8', (NEL, ))
              meshFileOut[:] = area
              # sys.exit()
              
       m_fid.close()
       
       endt = time.time()
       print('Time to read mesh areas (sec): ', endt - start)
       
       return areas

def loadMeshAdjacencyMap(mesh_file, varAdjaName):
       start = time.time()
       print('Reading adjacency maps...')
       # Fetch the adjacency map in the original grid netcdf file (target mesh)
       m_fid = Dataset(mesh_file, 'r')
       # Check for existing variable data
       try:
              if m_fid.variables[varAdjaName].name == varAdjaName:
                     varConStenDex = m_fid.variables[varAdjaName][:]
                     
       except:
              print('PRE-PROCESSING FOR ADJACENCY NOT DONE ON THIS MESH FILE!')
              sys.exit()
              
       m_fid.close()
              
       endt = time.time()
       print('Time to read adjacency maps (sec): ', endt - start)
       
       return varConStenDex

def loadMeshJacobians(mesh_file, varJacoName, SpectralElement):
       if SpectralElement:
              start = time.time()
              print('Reading SE mesh jacobians...')
                     
              m_fid = Dataset(mesh_file, 'r')
              # Check for existing variable data
              try:
                     if m_fid.variables[varJacoName].name == varJacoName:
                            jacobians = m_fid.variables[varJacoName][:]
              
              except:
                     print('ERROR: PRE-PROCESSING FOR JACOBIANS NOT AVAILABLE ON TARGET MESH FILE!')
                     sys.exit()
                     
              m_fid.close()
              
              endt = time.time()
              print('Time to read SE mesh jacobians (sec): ', endt - start)
       else:
              jacobians = None
              
       return jacobians

def loadSField(var_file, varName):
       start = time.time()
       # Open the .nc data files for reading
       ncFieldFileHnd = Dataset(var_file, 'r')
       
       # Get the field data
       varField = ncFieldFileHnd.variables[varName][:]
       
       # Check the extracted variables for dimensionality
       # If the variables are 2D then reshape along the longitude (ASSUMED)
       VS = varField.shape
       if len(VS) > 1:
              varField = np.reshape(varField, VS[0] * VS[1])
              
       #%% Close original NetCDF file.
       ncFieldFileHnd.close()
       
       endt = time.time()
       print('Time to read NC and Exodus data (sec): ', endt - start)
       
       return varField

def loadTField(var_file, varName):
       start = time.time()
       # Open the .nc data files for reading
       ncFieldFileHnd = Dataset(var_file, 'r')
       
       # Get the field data
       varField = ncFieldFileHnd.variables[varName][:]
       
       # Check the extracted variables for dimensionality
       # If the variables are 2D then reshape along the longitude (ASSUMED)
       VS = varField.shape
       if len(VS) > 1:
              varField = np.reshape(varField, VS[0] * VS[1])
              
       #%% Close original NetCDF file.
       ncFieldFileHnd.close()
       
       endt = time.time()
       print('Time to read NC and Exodus data (sec): ', endt - start)
       
       return varField


def loadDataField(ncFieldFileHnd, varName, dimension):
       srcvarName = varName + '_remap_src'
       tgtvarName = varName + '_remap_tgt'

       # Get the field data
       varFieldSrc = ncFieldFileHnd.variables[srcvarName][dimension,:]
       varFieldTgt = ncFieldFileHnd.variables[tgtvarName][dimension,:]

       return varFieldTgt, varFieldSrc


def loadFieldGradient(gradCtx, varField, varConn, varCoord, varConStenDex, jacobians, numCells, SpectralElement):
       
       start = time.time()
       # Read in previously stored ST data if it exists, or compute it and store
       if SpectralElement:
              # This comes from mesh preprocessing
              numDOFS = 'grid_gll_size'
              gradField = computeGradientSE(varField, varConn, varCoord, 4, jacobians)
       else: 
              numDOFS = numCells
              # gradField = computeGradientFV2(varField, varConn, varCoord, varConStenDex)
              # gradField = computeGradientFV3(varField, varConn, varCoord, varConStenDex)
              gradField = gradCtx.computeGradientFV3(varField)

       endt = time.time()
       # print('Time to compute/read gradients on', gradCtx.context, 'mesh (sec): ', endt - start)
       
       return gradField
       
if __name__ == '__main__':
       print('Welcome to CANGA remapping intercomparison metrics!')
       print('Authors: Jorge Guerra, Vijay Mahadevan, Paul Ullrich, 2019')

       # Parse the command-line inputs
       
       # NC files representing sampled data on source and target meshes
       sourceSampledFile = ''
       targetSampledFile = ''
       
       # Mesh information details
       sourceMeshConfig = 0
       targetMeshConfig = 0

       # Field variable name and data file
       fieldNames = ''
       fieldDataFile = ''

       # Spectral element specification
       isSourceSpectralElementMesh = False
       isTargetSpectralElementMesh = False

       # By default, let us not compute the gradient metrics. These are expensive
       includeGradientMetrics = False

       # Max number of remap iteration solutions to use in order to compute the metrics
       maxRemapIterations = 1

       # Parallelization of the driver through multiprocessing
       nprocs = 1
       
       def print_usage():
              print('Command line not properly set:', \
                    'CANGAMEtricsDriver.py', \
                    '--ss <SourceSampledFile>', \
                    '--st <targetSampledFile>', \
                    '--smc <sourceMeshConfiguration>', \
                    '--tmc <targetMeshConfiguration>', \
                    '--data <fieldDataFile>', \
                    '--field <fieldName;comma-separated list>', \
                    '--dimension <maxRemapIterations>', \
                    '--output <metricsFileName>', \
                    '--<includeGradientMetrics>', \
                    '--<isSourceSpectralElementMesh>', \
                    '--<isTargetSpectralElementMesh>', \
                    '--processes <nprocs>')
       
       try:
              opts, args = getopt.getopt(sys.argv[1:], 'hv:', \
                                        ['ss=', 'st=', 'data=', 'field=', \
                                         'smc=', 'tmc=', \
                                         'dimension=', 'includeGradientMetrics', \
                                         'output=', \
                                         'isSourceSpectralElementMesh', 'isTargetSpectralElementMesh', 'processes='])
       except getopt.GetoptError:
              print_usage()
              sys.exit(2)
              
       for opt, arg in opts:
              # Request for usage help
              if opt == '-h':
                     print_usage()
                     sys.exit()
              elif opt == '--ss':
                     sourceSampledFile = arg
              elif opt == '--st':
                     targetSampledFile = arg
              elif opt == '--smc':
                     sourceMeshConfig = int(arg)
              elif opt == '--tmc':
                     targetMeshConfig = int(arg)
              elif opt == '--field':
                     fieldNames = arg
              elif opt == '--data':
                     fieldDataFile = arg
              elif opt == '--isSourceSpectralElementMesh':
                     isSourceSpectralElementMesh = True
              elif opt == '--isTargetSpectralElementMesh':
                     isTargetSpectralElementMesh = True
              elif opt == '--includeGradientMetrics':
                     includeGradientMetrics = True
              elif opt == '--dimension':
                     maxRemapIterations = int(arg)
              elif opt == '--output':
                     outputMetricsFile = arg
              elif opt == '--processes':
                     nprocs = int(arg)

       # Input checks
       if sourceMeshConfig > 4:
              print('ERROR: Invalid source mesh configuration (1-4)')
              sys.exit(2)
       
       if targetMeshConfig > 4:
              print('ERROR: Invalid target mesh configuration (1-4)')
              sys.exit(2)

       if len(fieldNames) == 0:
              print('ERROR: Invalid field name list')
              sys.exit(2)

       mesh_fileS = sourceSampledFile
       mesh_fileT = targetSampledFile

       print('Source sampled mesh :', sourceSampledFile)
       print('Target sampled mesh :', targetSampledFile)
       print('Projected data file :', fieldDataFile)
       print('Field names         :', fieldNames)
       print('Remap dimension     :', maxRemapIterations)
       print('Number of processes :', nprocs)
       
       # Set the names for the auxiliary area and adjacency maps (NOT USER)
       varAreaName = 'cell_area'
       varJacoName = 'element_jacobians'
       varAdjaName = 'cell_edge_adjacency'
       varGradientName = 'FieldGradient'
              
       # Read in raw vertex/connectivity data from mesh files
       varCoordS, varConS, numCellsS, numDimsS, numVertsS = \
       loadMeshData(mesh_fileS, sourceMeshConfig, isSourceSpectralElementMesh)

       varCoordT, varConT, numCellsT, numDimsT, numVertsT = \
       loadMeshData(mesh_fileT, targetMeshConfig, isTargetSpectralElementMesh)
              
       # Read in source and target cell areas
       areaS = loadMeshAreas(mesh_fileS, varAreaName, varConS, varCoordS)
       areaT = loadMeshAreas(mesh_fileT, varAreaName, varConT, varCoordT)

       # Read in source and target Jacobian weights
       jacobiansS = loadMeshJacobians(mesh_fileS, varJacoName, isSourceSpectralElementMesh)
       jacobiansT = loadMeshJacobians(mesh_fileT, varJacoName, isTargetSpectralElementMesh)
       
       # Read in source and target adjacency maps
       varConStenDexS = loadMeshAdjacencyMap(mesh_fileS, varAdjaName)
       varConStenDexT = loadMeshAdjacencyMap(mesh_fileT, varAdjaName)

       gradSCtx = gradTCtx = None

       fieldNames = [x.strip() for x in fieldNames.split(',')]
       
       # Open the .nc data files for reading
       ncFieldFileHnd = Dataset(fieldDataFile, 'r')

       # Read in or compute the respective gradients on target mesh
       if includeGradientMetrics:
              print('\nComputing gradient datastructures for grids...')
              start = time.time()
              gradSCtx = ComputeGradientFV('Source', varConS, varCoordS, varConStenDexS, nprocs)
              gradSCtx.precomputeGradientFV3Data()
              print('Time taken to precompute gradient datastructures for source grid: ', time.time() - start)
              start = time.time()
              gradTCtx = ComputeGradientFV('Target', varConT, varCoordT, varConStenDexT, nprocs)
              gradTCtx.precomputeGradientFV3Data()
              print('Time taken to precompute gradient datastructures for target grid: ', time.time() - start)

       for fieldName in fieldNames:
       # def metrics_per_field(fieldName):

            print('\nComputing Field metrics for ', fieldName)
            runtimeS = time.time()

            varSS = loadSField(sourceSampledFile, fieldName)
            varST = loadTField(targetSampledFile, fieldName)

            # Read in or compute the respective gradients on target mesh
            if includeGradientMetrics:
                   gradTS = loadFieldGradient(gradSCtx, varSS, varConS, varCoordS, varConStenDexS, jacobiansS, numCellsS, isSourceSpectralElementMesh)
                   gradST = loadFieldGradient(gradTCtx, varST, varConT, varCoordT, varConStenDexT, jacobiansT, numCellsT, isTargetSpectralElementMesh)

            #%%
            dataMetrics = pd.DataFrame({  "GC": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "GL1": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "GL2": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "GLinf": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "GMaxE": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "GMinE": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "LMaxL1": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "LMaxL2": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "LMaxLm": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "LMinL1": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "LMinL2": np.zeros(maxRemapIterations+1, dtype='float64'), \
                                 "LMinLm": np.zeros(maxRemapIterations+1, dtype='float64') \
                              })
            if includeGradientMetrics:
                    # For pandas < 1.0
                    #dataMetrics = dataMetrics.concat(pd.DataFrame({ 'H12T': np.zeros(maxRemapIterations+1, dtype='float64'), \
                    #                              'H1T': np.zeros(maxRemapIterations+1, dtype='float64'), \
                    #                              'H12S': np.zeros(maxRemapIterations+1, dtype='float64'), \
                    #                              'H1S': np.zeros(maxRemapIterations+1, dtype='float64')
                    #                            }))

                    # We might need to use the following code for pandas > 1.0:
                    dataMetrics = pd.concat([dataMetrics, pd.DataFrame({ 'H12T': np.zeros(maxRemapIterations+1, dtype='float64'), \
                                                       'H1T': np.zeros(maxRemapIterations+1, dtype='float64'), \
                                                       'H12S': np.zeros(maxRemapIterations+1, dtype='float64'), \
                                                       'H1S': np.zeros(maxRemapIterations+1, dtype='float64')
                                                    })
                                    ], 
                                    axis=1)

            # Print out a table with metric results. Let us print progress during iteration progress
            print('\n')
            printProgressBar(0, maxRemapIterations+1, prefix = 'Progress:', suffix = 'Complete', length = 50)

       #      nprocs_per_field = nprocs/len(fieldNames) if nprocs > len(fieldNames) else 1
            def metrics_per_field_dimension(iteration):
       #      for iteration in range(maxRemapIterations+1):
                    # Read in field variable data
                    varS2T, varT2S = loadDataField(ncFieldFileHnd, fieldName, iteration)

                    #%% Computing all metrics...

                    # Global conservation metric
                    massS2T, massST, L_g = computeGlobalConservation(varConS, varConT, varSS, varS2T, varST, areaS, areaT, jacobiansS, jacobiansT, isSourceSpectralElementMesh, isTargetSpectralElementMesh)

                    # Locality measure (returns an array for each target DOF)
                    #L_local = computeLocalityMetric(varS2T, varST, varConn, varCoord)

                    # Standard Error norms (L_1, L_2, L_inf)
                    L_1, L_2, L_inf = computeStandardNorms(varConT, varS2T, varST, areaT, jacobiansT, isTargetSpectralElementMesh)

                    # Global Extrema preservation
                    Lmin, Lmax = computeGlobalExtremaMetrics(varS2T, varST)

                    # Local Extrema preservation
                    Lmin_1, Lmin_2, Lmin_inf, Lmax_1, Lmax_2, Lmax_inf = \
                    computeLocalExtremaMetrics(varConStenDexT, varConT, varCoordT, varS2T, varST, areaT, jacobiansT, isTargetSpectralElementMesh)

                    # create a local dataframe
                    df = pd.DataFrame(columns=dataMetrics.columns)

                    # Populate the datatable 
                    df.loc[iteration,'GC'] = L_g
                    df.loc[iteration,'GL1'] = L_1
                    df.loc[iteration,'GL2'] = L_2
                    df.loc[iteration,'GLinf'] = L_inf
                    df.loc[iteration,'GMaxE'] = Lmax
                    df.loc[iteration,'GMinE'] = Lmin
                    df.loc[iteration,'LMaxL1'] = Lmax_1
                    df.loc[iteration,'LMaxL2'] = Lmax_2
                    df.loc[iteration,'LMaxLm'] = Lmax_inf
                    df.loc[iteration,'LMinL1'] = Lmin_1
                    df.loc[iteration,'LMinL2'] = Lmin_2
                    df.loc[iteration,'LMinLm'] = Lmin_inf

                    # Read in or compute the respective gradients on target mesh
                    if includeGradientMetrics:

                            # Gradient preservation checks on target grid
                            gradS2T = loadFieldGradient(gradTCtx, varS2T, varConT, varCoordT, varConStenDexT, jacobiansT, numCellsT, isTargetSpectralElementMesh)
                            varsOnTM = [varST, varS2T]
                            gradientsOnTM = [gradST, gradS2T]
                            H1, H1_2 = computeGradientPreserveMetrics(varConT, gradientsOnTM, varsOnTM, areaT, jacobiansT, isTargetSpectralElementMesh)

                            df.loc[iteration, 'H12T'] = H1_2
                            df.loc[iteration, 'H1T'] = H1

                            # Gradient preservation checks on source grid
                            varsOnSM = [varSS, varT2S]
                            gradT2S = loadFieldGradient(gradSCtx, varT2S, varConS, varCoordS, varConStenDexS, jacobiansS, numCellsS, isSourceSpectralElementMesh)
                            gradientsOnSM = [gradTS, gradT2S]
                            H1, H1_2 = computeGradientPreserveMetrics(varConS, gradientsOnSM, varsOnSM, areaS, jacobiansS, isSourceSpectralElementMesh)

                            df.loc[iteration, 'H12S'] = H1_2
                            df.loc[iteration, 'H1S'] = H1

                    #%%
                    # Print out a table with metric results
                    printProgressBar(iteration+1, maxRemapIterations+1, prefix = 'Progress:', suffix = 'Complete', length = 50)

                    # return the computed metrics frame
                    return df


            def append_fieldname(filename):
                    return "{0}_{2}.{1}".format(*filename.rsplit('.', 1) + [fieldName])

            # launch the metrics computation in parallel
            iterationpool = multiprocessing.Pool(processes=nprocs)
            results = iterationpool.starmap(metrics_per_field_dimension, zip(range(maxRemapIterations+1)))
            iterationpool.close()
            iterationpool.join()

            # consolidate the data
            dfnew = results[0]
            for ii in range(1, len(results)):
                   lresults = results[ii]
                   dfnew = pd.concat([dfnew, lresults])
            dataMetrics = dfnew

            # Print and write to file
            pd.options.display.float_format = '{:,.15e}'.format
            print('\nFinished computing metrics for',fieldName,'in', time.time()-runtimeS, 'seconds')
            dataMetrics.to_csv(append_fieldname(outputMetricsFile), index=False)
            print('Writing metrics data for',fieldName,'field to', outputMetricsFile)
            print('\n\t\t\t\tTABLE OF REMAPPING ITERATION METRICS FOR Field=',fieldName,'\n')
            print(dataMetrics)

       ## 
       # Use the following block if we want to parallelize over fields
       # Need to comment and uncomment the `metrics_per_field` declaration above
       ##
       # pool = multiprocessing.Pool(processes=len(fieldNames))
       # results = pool.starmap(metrics_per_field, zip(fieldNames))
       # pool.close()
       # pool.join()

       #%% Close original NetCDF file.
       ncFieldFileHnd.close()

 
#%%
