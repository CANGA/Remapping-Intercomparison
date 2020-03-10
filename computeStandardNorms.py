#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Dec 18 14:28:23 2018

Computes the standard error norms for the regridded and reference target data

@author: jeguerra
"""
import math as mt
import numpy as np
from computeGlobalWeightedIntegral import computeGlobalWeightedIntegral

def computeStandardNorms(varConT, varS2T, varST, areaT, jacobiansT, SpectralElement):
       
       # Get the total number of cells/elements
       NT = varConT.shape[0]
       
       # Compute the difference
       varDiff = np.subtract(varS2T, varST)
       varDiff2 = np.power(varDiff, 2)
       varST2 = np.power(varST, 2)
       
       # Compute the necessary integrals
       L1Den = computeGlobalWeightedIntegral(NT, varConT, np.abs(varST), areaT, jacobiansT, SpectralElement)
       L2Den = computeGlobalWeightedIntegral(NT, varConT, np.abs(varST2), areaT, jacobiansT, SpectralElement)
       LinfDen = np.amax(np.abs(varST))
       
       L1Num = computeGlobalWeightedIntegral(NT, varConT, np.abs(varDiff), areaT, jacobiansT, SpectralElement)
       L2Num = computeGlobalWeightedIntegral(NT, varConT, np.abs(varDiff2), areaT, jacobiansT, SpectralElement)
       LinfNum = np.amax(np.abs(varDiff))

       # print('NORMS: ', L1Num, L1Den, L2Num, L2Den, LinfNum, LinfDen)
       print('error: ', varS2T, varST)
       
       L_1 = L1Num / L1Den
       L_2 = mt.sqrt(L2Num / L2Den)
       L_inf = LinfNum / LinfDen
       
       return L_1, L_2, L_inf


def computeStandardNormsNew(varConT, varS2T, varST, areaT, jacobiansT, SpectralElement):
       
       # Get the total number of cells/elements
       NT = varConT.shape[0]
       
       # Compute the difference
       varDiff = np.abs(np.subtract(varS2T, varST))
       varDiff2 = np.power(varDiff, 2)
       varST2 = np.power(varST, 2)
       
       # Compute the necessary integrals
       # L1Den = computeGlobalWeightedIntegral(NT, varConT, np.abs(varST), areaT, jacobiansT, SpectralElement)
       # L2Den = computeGlobalWeightedIntegral(NT, varConT, np.abs(varST2), areaT, jacobiansT, SpectralElement)
       LinfDen = np.amax(np.abs(varST))
       LareaDen = computeGlobalWeightedIntegral(NT, varConT, np.ones(varST.shape), areaT, jacobiansT, SpectralElement)
       
       L1Num = computeGlobalWeightedIntegral(NT, varConT, np.abs(varDiff), areaT, jacobiansT, SpectralElement)
       L2Num = computeGlobalWeightedIntegral(NT, varConT, np.abs(varDiff2), areaT, jacobiansT, SpectralElement)
       LinfNum = np.amax(np.abs(varDiff))
       
       # L_1 = L1Num / L1Den
       # L_2 = mt.sqrt(L2Num / L2Den)
       # L_inf = LinfNum / LinfDen
       L_1 = L1Num / LinfDen / LareaDen
       L_2 = mt.sqrt(L2Num) / LinfDen / LareaDen
       L_inf = LinfNum / LinfDen
       
       return L_1, L_2, L_inf
