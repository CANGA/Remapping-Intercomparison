#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Dec 24 08:26:47 2018

Compute a low order FV gradient on the manifold based on the adjacency stencil 
around a cell. Corresponds to "strategy 2" in Barth & Jespersen, 1989 page 6.

By construction, all the vectors involved start at the origin... convenient.
Parameterized flux integral assumes constant radius and field value.

@author: jeguerra
"""

import numpy as np
import math as mt
from computeAreaIntegral import computeAreaIntegral
from computeCentroid import computeCentroid

def computeGradientFV2(varField, varCon, varCoords, varStenDex):
       SF = np.float64
       
       # Gradients are 3 component vectors
       nc = 3
       gradShape = (nc, varField.shape[0])
       
       # Set the main return variable
       varGradient = np.zeros(gradShape, dtype=SF)
       
       cellCoords = np.zeros((nc, varCon.shape[0]), dtype=SF)
       
       NC = int(varStenDex.shape[0])
       NP = int(varStenDex.shape[1])
       fluxIntegral = np.zeros(nc, dtype=SF)
       
       # Precompute the cell centroid map
       cellCoords = np.zeros((nc,NC), dtype=SF)
       radius = np.zeros((NC,1), dtype=SF)
       for jj in range(NC):
              #pdex = np.array(range(NP), dtype = int)
              cdex = (varCon[jj,:]) - 1
              cdex = cdex.astype(int)
              cell = varCoords[:,cdex]
              cellCoords[:,jj] = computeCentroid(NP, cell)
              radius[jj] = np.linalg.norm(cellCoords[:,jj])
       
       # Loop over the cells
       for jj in range(NC):
              pdex = np.array(range(NP), dtype = int)
              
              # Check for local degeneracy in stencil and fix connectivity
              for pp in range(NP):
                     # Look for -1 in the adjacency stencil
                     if varStenDex[jj,pp] <= 0:
                            pdex = np.delete(pdex, pp)
                     else:
                            continue
                     
              thisStencil = varStenDex[jj,pdex]
              
              # Loop over the stencil and get dual edges map
              fluxIntegral = np.zeros(nc, dtype=SF)
              dualEdgeMap = np.zeros((nc,len(pdex)))
              boundaryNorm = np.zeros((nc,len(pdex)))
              boundaryAngles = np.zeros((len(pdex),1))
              for pp in pdex:
                     # Fetch the dual edge and store
                     sid1 = thisStencil[pp] - 1
                     sid1 = sid1.astype(int)
                     # Make the dual polygon convex
                     if pp == len(pdex) - 1:
                            sid2 = thisStencil[0] - 1
                     else:
                            sid2 = thisStencil[pp+1] - 1
                     sid2 = sid2.astype(int)
                     
                     # Store the dual mesh polygon
                     dualEdgeMap[:,pp] = cellCoords[:,sid1]
                     
                     # Compute angles spanned by each boundary segment
                     RE = 0.5 * (radius[sid1] + radius[sid2])
                     unCoord1 = 1.0 / radius[sid1] * cellCoords[:,sid1]
                     unCoord2 = 1.0 / radius[sid2] * cellCoords[:,sid2]
                     boundaryAngles[pp] = mt.acos(np.dot(unCoord1, unCoord2))
                     boundaryAngles[pp] = abs(boundaryAngles[pp])
                     
                     # Compute the stencil boundary normals
                     boundaryNorm[:,pp] = np.cross(cellCoords[:,sid2], \
                                                   cellCoords[:,sid1])
                     bnMag = np.linalg.norm(boundaryNorm[:,pp])
                     boundaryNorm[:,pp] = 1.0 / bnMag * boundaryNorm[:,pp]
                     
                     # Compute the weighted average of the two cell values AT the shared edge location
                     vWeight = 0.5 * boundaryAngles[pp] * RE
                     varAvg = varField[sid1] + varField[sid2]
                     
                     # Compute the integral over this edge
                     fluxIntegral = np.add(fluxIntegral, \
                                        vWeight * varAvg * \
                                        boundaryNorm[:,pp])
                        
              # Compute the dual polygon area
              areaD = computeAreaIntegral(None, dualEdgeMap, 6, False, True)
              
              # Compute the local gradient at this cell
              varGradient[:,jj] = 1.0 / areaD * fluxIntegral
              
       return varGradient