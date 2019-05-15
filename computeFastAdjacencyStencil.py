#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Dec 21 09:16:45 2018

Computes the adjacency array (augmented to the connectivity). Assumes that all
cells have the same orientation (clockwise or aniclockwise). For a given cell,
make an (NP, 2) array of edges in reversed order to match any other cells that
also have that same edge, again assuming all cells have the same orientation.
Supports: quadrilaterals and triangles.

NOTE: edgeMap: [cell 2, node1, node2, cell 1] outer give the two cells that
belong to the edge specified in nodes. left to right connectivity for cell 1
and right to left connectivity for cell 2 

@author: jeguerra
"""

import numpy as np
from scipy.spatial import cKDTree
from computeEdgesArray import computeEdgesArray

COINCIDENT_TOLERANCE = 1.0E-14
kdleafs = 64

def computeFastAdjacencyStencil(varCon):
       
       NC = varCon.shape[0]
       NP = varCon.shape[1]
       
       varConStenDex = np.zeros((NC, NP + NP))
       
       # Make an array of edges based on grid pairs from connectivity and a cell id
       # This has coincident pairs of edges for each cell processed
       for cc in range(NC):
              
              # Copy over the connectivity of the current cell
              varConStenDex[cc, range(NP)] = varCon[cc,:]
              
              # Make the cell id column for dim 3 of edgeMap
              cid = (cc + 1) * np.ones((NP, 1))
              
              # Get the local node pair map for these edges
              edges = computeEdgesArray(NP, varCon[cc,:])
              
              # Append the cell map to the end of the node map
              edges = np.append(edges, cid, axis=1)
              
              if cc == 0:
                     edgeNodeMap = edges
              else:
                     edgeNodeMap = np.append(edgeNodeMap, edges, axis=0)
                     
       '''
       # Sort edgeMap first 2 column in ascending order to enable coincident check
       sortedEdges = np.sort(edgeNodeMap[:,[0, 1]], axis=1)
                     
       # Build a KDtree around the edge map of cell - node pair
       edgeTree = cKDTree(sortedEdges, leafsize=kdleafs)
       
       # Compute the edges to cells map [c1 n1 n2 c2]
       NE = np.size(edgeNodeMap, axis=0)
       keepDex = []
       edgeCellMap = []
       thisCellMap = []
       for ii in range(NE):
              # Compute the list of nodes that are coincident
              thisEdge = sortedEdges[ii,:]
              
              # ndex will have 2 cellID's for non-degenerate edges
              ndex = edgeTree.query_ball_point(thisEdge, COINCIDENT_TOLERANCE, p=2, eps=0)
              
              # coinDex stores indices of coincident edges (and degenerate points)
              # keepDex stores indices for unique edges
              if int(thisEdge[0]) != int(thisEdge[1]):
                     if len(ndex) < 2:
                            # This edge has an empty space adjacent
                            adjCell1 = ndex[0]
                            adjCell2 = -1
                     elif len(ndex) == 2:
                            # This edge has 2 cells adjacent
                            adjCell1 = ndex[0]
                            adjCell2 = ndex[1]
                            keepDex.append(int(min(ndex)))
                     else:
                            adjCell1 = -1
                            adjCell2 = -1
                            print('Found an edge with more than 2 adjacent cells.', thisEdge)
                     
                     # Make the cell - edge - cell map for this cell
                     thisCellMap = np.array([edgeNodeMap[adjCell1,2], \
                                             thisEdge[0], thisEdge[1], \
                                             edgeNodeMap[adjCell2,2]])

                     if len(edgeCellMap) == 0:
                            edgeCellMap = [thisCellMap]
                     elif len(thisCellMap) > 0:
                            edgeCellMap = np.append(edgeCellMap, [thisCellMap], axis=0)
              else:
                     continue
                     
       # Trim coincidents from edgeCellMap with keepDex array
       keepDex = np.unique(keepDex)
       cleanEdgeCellMap = edgeCellMap[keepDex,:]
                     
       # Compute a KDtree from the smaller cleanEdgeCellMap (on edge coordinates)
       edgeTree = cKDTree(cleanEdgeCellMap[:,[1, 2]], leafsize=kdleafs)
       '''
       edgeTree = cKDTree(edgeNodeMap[:,[0, 1]], leafsize=kdleafs)
       # Loop over the node connectivity and construct the adjacency stencil
       for ii in range(NC):
              # Get the local node pair map for these edges
              edges = computeEdgesArray(NP, varCon[ii,:])
              
              # Loop over the surrounding edges to this cell
              for jj in range(NP):
                     # Check for degenerate edge leaves a 0 in the stencil
                     if edges[jj,0] == edges[jj,1]:
                            continue
                     
                     # Fetch the current edge in both local directions
                     #thisEdge = edges[jj,:]
                     thisEdge = edges[jj,::-1]
                     
                     # Find the matching edge (should only give one result)
                     cdex = edgeTree.query_ball_point(thisEdge, COINCIDENT_TOLERANCE, p=2, eps=0)
                     #cdex2 = edgeTree.query_ball_point(thisEdge2, COINCIDENT_TOLERANCE, p=2, eps=0)
                     
                     # Check for no edge found
                     if not cdex:
                            continue
                     
                     # Fetch the edge map
                     #thisEdgeMap = edgeNodeMap[cdex,:]
                     #print(thisEdge, cdex, thisEdgeMap)
                     
                     # Get the connected cell and set the stencil
                     varConStenDex[ii,NP+jj] = edgeNodeMap[cdex,2]
                            
       return edgeNodeMap, varConStenDex
