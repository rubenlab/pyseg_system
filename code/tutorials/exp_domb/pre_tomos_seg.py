"""

    Pre-processing for mb_graph_batch.py of double oriented membranes from a lumen labeled segmentation

    Input:  - STAR file with 3 columns:
                + _rlnMicrographName: tomogram original (denisity map)
                + _psSegImage: labelled tomogram with the segmentations
                + _mtMtubesCsv: (optional) a .csv file with microtubule center lines
            - Setting for segmenting the pairs of membranes:
            - Sub-volume splitting settings

    Output: - A STAR file with 3 columns:
                + _rlnMicrographName: tomogram original
                + _rlnImageName: sub-volumes
                + _psSegImage: Oriented double membrane segmentations for each subvolume
                + Columns for localizing the sub-volumes within each original tomogram

"""

################# Package import

import gc
import os
import sys
import math
import time
import pyseg as ps
import scipy as sp
import skimage as sk
import numpy as np
from pyseg.globals import signed_distance_2d

###### Global variables

__author__ = 'Antonio Martinez-Sanchez'

MB_LBL_1, MB_LBL_2 = 1, 2
EXT_LBL_1, EXT_LBL_2 = 3, 4
GAP_LBL, BG_LBL = 5, 0

########################################################################################
# PARAMETERS
########################################################################################

ROOT_PATH = '/fs/pool/pool-ruben/antonio/nuc_mito'

# Input STAR file
in_star = ROOT_PATH + '/pre/in/dmb_seg_oriented.star'

# Output directory
out_dir = ROOT_PATH + '/pre/mbdo_nosplit'

# Subvolume splitting settings
sp_split = None # (2, 2, 1)
sp_off_voxels = 30 # vox

# Membrane segmentation
sg_lbl_mb1 = 1
sg_lbl_mb2 = 2
sg_lbl_ext1 = 3
sg_lbl_ext2 = 4
sg_lbl_gap = 5
sg_lbl_bg = 6
sg_res = 1.408 # nm/voxel
sg_mb_thick = 5 # nm
sg_mb_neigh = 20 # nm
sg_mb_gap = 40 # nm
sg_min_vx_seg = 10 # vx

# CSV file pre-processing
cv_coords_cools = (1, 2, 3)
cv_id_col = 4

# Microtubule settings
mt_rad = 30 # nm
mt_swap_xy = False


########################################################################################
# MAIN ROUTINE
########################################################################################

########## Print initial message

print 'Pre-processing for SEG analysis of un-oriented membranes from TomoSegMemTV output.'
print '\tAuthor: ' + __author__
print '\tDate: ' + time.strftime("%c") + '\n'
print 'Options:'
print '\tOutput directory: ' + str(out_dir)
print '\tInput STAR file: ' + str(in_star)
print '\tData resolution: ' + str(sg_res) + ' nm/vx'
print '\tMembrane segmentation:'
print '\t\t-Segmentation labels:'
print '\t\t\t+Membrane 1: ' + str(sg_lbl_mb1)
print '\t\t\t+Membrane 2: ' + str(sg_lbl_mb2)
print '\t\t\t+External 1: ' + str(sg_lbl_ext1)
print '\t\t\t+External 2: ' + str(sg_lbl_ext2)
print '\t\t\t+Gap: ' + str(sg_lbl_gap)
print '\t\t-Segmentation resolution: ' + str(sg_res) + ' nm/vx'
print '\t\t-Membrane thickness: ' + str(sg_mb_thick) + ' nm'
print '\t\t-External neighbourhood maximum distance: ' + str(sg_mb_neigh) + ' nm'
print '\t\t-Gap maximum distance: ' + str(sg_mb_gap) + ' nm'
print '\t\t-Minum number of voxels per segmentation: ' + str(sg_min_vx_seg)
print '\tSub-volume splitting settings: '
print '\t\t-Number of splits (X, Y, Z): ' + str(sp_split)
print '\t\t-Offset voxels: ' + str(sp_off_voxels)
print '\tMicrotubule settings:'
print '\t\t-Microtube luminal radius: ' + str(mt_rad) + ' nm'
print '\tCSV pre-processing: '
print '\t\t-Columns for samples coordinates (X, Y, Z): ' + str(cv_coords_cools)
print '\t\t-Column for microtubule ID: ' + str(cv_id_col)
print ''

######### Process

print 'Parsing input parameters...'
sp_res, mt_rad, sp_off_voxels = float(sg_res), float(mt_rad), int(sp_off_voxels)
out_stem = os.path.splitext(os.path.split(in_star)[1])[0]
conn_mask = np.ones(shape=(3,3,3))
out_seg_dir = out_dir + '/segs'
if not os.path.isdir(out_seg_dir):
    os.makedirs(out_seg_dir)

print 'Loading input STAR file...'
gl_star = ps.sub.Star()
try:
    gl_star.load(in_star)
except ps.pexceptions.PySegInputError as e:
    print 'ERROR: input STAR file could not be loaded because of "' + e.get_message() + '"'
    print 'Terminated. (' + time.strftime("%c") + ')'
    sys.exit(-1)
star = ps.sub.Star()
star.add_column(key='_rlnMicrographName')
star.add_column(key='_rlnImageName')
star.add_column(key='_psSegImage')
star.add_column(key='_psSegRot')
star.add_column(key='_psSegTilt')
star.add_column(key='_psSegPsi')
star.add_column(key='_psSegOffX')
star.add_column(key='_psSegOffY')
star.add_column(key='_psSegOffZ')

print 'Main Routine: tomograms loop'
tomo_id = 0
for row in range(gl_star.get_nrows()):

    in_ref = gl_star.get_element('_rlnMicrographName', row)
    print '\tProcessing tomogram: ' + in_ref
    out_ref_stem = os.path.splitext(os.path.split(in_ref)[1])[0]
    in_seg = gl_star.get_element('_psSegImage', row)
    print '\t\t-Loading segmentation: ' + in_seg
    orig_seg = ps.disperse_io.load_tomo(gl_star.get_element('_psSegImage', row))
    tomo_ref = ps.disperse_io.load_tomo(in_ref, mmap=True)
    off_mask_min_x, off_mask_max_x = 0, tomo_ref.shape[0]
    off_mask_min_y, off_mask_max_y = 0, tomo_ref.shape[1]
    off_mask_min_z, off_mask_max_z = 0, tomo_ref.shape[2]
    wide_x = off_mask_max_x - off_mask_min_x
    wide_y = off_mask_max_y - off_mask_min_y
    wide_z = off_mask_max_z - off_mask_min_z

    if gl_star.has_column('_mtMtubesCsv'):
        in_csv = gl_star.get_element('_mtMtubesCsv', row)
        print '\tReading input CSV file: ' + in_csv
        mt_dic = ps.globals.read_csv_mts(in_csv, cv_coords_cools, cv_id_col, swap_xy=mt_swap_xy)
        mts_points = list()
        for mt_id, mt_samps in zip(mt_dic.iterkeys(), mt_dic.itervalues()):
            mts_points += mt_samps
        mts_points = np.asarray(mts_points, dtype=np.float32) * (1./sg_res)

        print '\tSegmenting the microtubules...'
        mt_mask = ps.globals.points_to_mask(mts_points, orig_seg.shape, inv=True)
        mt_mask = sp.ndimage.morphology.distance_transform_edt(mt_mask, sampling=sg_res, return_indices=False)
        mt_mask = mt_mask > mt_rad

    print '\t\t-Membranes pair segmentation...'
    sg_mb_thick_2 = 0.5 * sg_mb_thick
    tomo_seg = np.zeros(shape=orig_seg.shape, dtype=np.int8)
    mb1_dst = sp.ndimage.morphology.distance_transform_edt(orig_seg != sg_lbl_mb1, sampling=sg_res, return_indices=False)
    mb2_dst = sp.ndimage.morphology.distance_transform_edt(orig_seg != sg_lbl_mb2, sampling=sg_res, return_indices=False)
    tomo_seg[(mb1_dst <= sg_mb_thick_2 + sg_mb_neigh) & (orig_seg == sg_lbl_ext1)] = EXT_LBL_1
    tomo_seg[(mb2_dst <= sg_mb_thick_2 + sg_mb_neigh) & (orig_seg == sg_lbl_ext2)] = EXT_LBL_2
    tomo_seg[(mb1_dst <= sg_mb_thick_2 + sg_mb_gap) & (mb2_dst <= sg_mb_thick_2 + sg_mb_gap) & (orig_seg == sg_lbl_gap)] = GAP_LBL
    tomo_seg[mb1_dst <= sg_mb_thick_2] = MB_LBL_1
    tomo_seg[mb2_dst <= sg_mb_thick_2] = MB_LBL_2
    tomo_seg[orig_seg == sg_lbl_bg] = BG_LBL
    gap_dst = sp.ndimage.morphology.distance_transform_edt(tomo_seg != GAP_LBL, sampling=sg_res, return_indices=False)
    tomo_seg[gap_dst > sg_mb_thick_2 + sg_mb_neigh] = BG_LBL
    if gl_star.has_column('_mtMtubesCsv'):
        tomo_seg[np.invert(mt_mask)] = BG_LBL

    # Computer segmentation bounds
    hold_mask = tomo_seg != BG_LBL
    ids_mask = np.where(hold_mask)
    off_mask_min_x, off_mask_max_x = ids_mask[0].min()-sp_off_voxels, ids_mask[0].max()+sp_off_voxels
    if off_mask_min_x < 0:
        off_mask_min_x = 0
    if off_mask_max_x > hold_mask.shape[0]:
        off_mask_max_x = hold_mask.shape[0]
    off_mask_min_y, off_mask_max_y = ids_mask[1].min()-sp_off_voxels, ids_mask[1].max()+sp_off_voxels
    if off_mask_min_y < 0:
        off_mask_min_y = 0
    if off_mask_max_y > hold_mask.shape[1]:
        off_mask_max_y = hold_mask.shape[1]
    off_mask_min_z, off_mask_max_z = ids_mask[2].min()-sp_off_voxels, ids_mask[2].max()+sp_off_voxels
    if off_mask_min_z < 0:
        off_mask_min_z = 0
    if off_mask_max_z > hold_mask.shape[2]:
        off_mask_max_z = hold_mask.shape[2]
    del hold_mask
    del ids_mask

    print '\tSegmenting the membranes...'
    if sp_split is None:
        svol_seg = tomo_seg[off_mask_min_x:off_mask_max_x, off_mask_min_y:off_mask_max_y, off_mask_min_z:off_mask_max_z]
        if ((svol_seg == MB_LBL_1).sum() >= sg_min_vx_seg) and ((svol_seg == MB_LBL_2).sum() > sg_min_vx_seg) \
                and ((svol_seg == EXT_LBL_1).sum() >= sg_min_vx_seg) and ((svol_seg == EXT_LBL_2).sum() > sg_min_vx_seg) and \
                    ((svol_seg == GAP_LBL).sum() >= sg_min_vx_seg):
            svol = tomo_ref[off_mask_min_x:off_mask_max_x, off_mask_min_y:off_mask_max_y, off_mask_min_z:off_mask_max_z]
            out_svol = out_seg_dir + '/' + out_ref_stem + '_tid_' + str(tomo_id) + '.mrc'
            out_seg = out_seg_dir + '/' + out_ref_stem + '_tid_' + str(tomo_id) + '_seg.mrc'
            ps.disperse_io.save_numpy(svol, out_svol)
            ps.disperse_io.save_numpy(svol_seg, out_seg)
            del svol_seg
            row_dic = dict()
            row_dic['_rlnMicrographName'] = in_ref
            row_dic['_rlnImageName'] = out_svol
            row_dic['_psSegImage'] = out_seg
            row_dic['_psSegRot'] = 0
            row_dic['_psSegTilt'] = 0
            row_dic['_psSegPsi'] = 0
            row_dic['_psSegOffX'] = off_mask_min_x # 0
            row_dic['_psSegOffY'] = off_mask_min_y # 0
            row_dic['_psSegOffZ'] = off_mask_min_z
            star.add_row(**row_dic)
    else:
        print '\tSplitting into subvolumes:'
        if sp_split[0] > 1:
            hold_wide = int(math.ceil(wide_x / sp_split[0]))
            hold_pad = int(math.ceil((off_mask_max_x - off_mask_min_x) / sp_split[0]))
            hold_split = int(sp_split[0] * math.ceil(float(hold_pad)/hold_wide))
            offs_x = list()
            pad_x = off_mask_min_x + int(math.ceil((off_mask_max_x-off_mask_min_x) / hold_split))
            offs_x.append((off_mask_min_x, pad_x+sp_off_voxels))
            lock = False
            while not lock:
                hold = offs_x[-1][1] + pad_x
                if hold >= off_mask_max_x:
                    offs_x.append((offs_x[-1][1] - sp_off_voxels, off_mask_max_x))
                    lock = True
                else:
                    offs_x.append((offs_x[-1][1]-sp_off_voxels, offs_x[-1][1]+pad_x+sp_off_voxels))
        else:
            offs_x = [(off_mask_min_x, off_mask_max_x),]
        if sp_split[1] > 1:
            hold_wide = int(math.ceil(wide_y / sp_split[1]))
            hold_pad = int(math.ceil((off_mask_max_y - off_mask_min_y) / sp_split[1]))
            hold_split = int(sp_split[1] * math.ceil(float(hold_pad) / hold_wide))
            offs_y = list()
            pad_y = off_mask_min_y + int(math.ceil((off_mask_max_y-off_mask_min_y) / hold_split))
            offs_y.append((off_mask_min_x, pad_y + sp_off_voxels))
            lock = False
            while not lock:
                hold = offs_y[-1][1] + pad_y
                if hold >= off_mask_max_y:
                    offs_y.append((offs_y[-1][1] - sp_off_voxels, off_mask_max_y))
                    lock = True
                else:
                    offs_y.append((offs_y[-1][1] - sp_off_voxels, offs_y[-1][1] + pad_y + sp_off_voxels))
        else:
            offs_y = [(off_mask_min_x, off_mask_max_x),]
        if sp_split[2] > 1:
            hold_wide = int(math.ceil(wide_z / sp_split[2]))
            hold_pad = int(math.ceil((off_mask_max_z - off_mask_min_z) / sp_split[2]))
            hold_split = int(sp_split[2] * math.ceil(float(hold_pad) / hold_wide))
            offs_z = list()
            pad_z = off_mask_min_z + int(math.ceil((off_mask_max_z-off_mask_min_z) / hold_split))
            offs_z.append((off_mask_min_z, pad_z + sp_off_voxels))
            lock = False
            while not lock:
                hold = offs_z[-1][1] + pad_z
                if hold >= off_mask_max_z:
                    offs_z.append((offs_z[-1][1] - sp_off_voxels, off_mask_max_z))
                    lock = True
                else:
                    offs_z.append((offs_z[-1][1] - sp_off_voxels, offs_z[-1][1] + pad_z + sp_off_voxels))
        else:
            offs_z = [(off_mask_min_z, off_mask_max_z),]
        split_id = 1
        for off_x in offs_x:
            for off_y in offs_y:
                for off_z in offs_z:
                    print '\t\t-Splitting subvolume: [' + str(off_x) + ', ' + str(off_y) + ', ' + str(off_z) + ']'
                    svol_seg = tomo_seg[off_x[0]:off_x[1], off_y[0]:off_y[1], off_z[0]:off_z[1]]
                    if ((svol_seg == MB_LBL_1).sum() >= sg_min_vx_seg) and ((svol_seg == MB_LBL_2).sum() > sg_min_vx_seg) \
                            and ((svol_seg == EXT_LBL_1).sum() >= sg_min_vx_seg) and ((svol_seg == EXT_LBL_2).sum() > sg_min_vx_seg) and \
                                ((svol_seg == GAP_LBL).sum() >= sg_min_vx_seg):
                        svol = tomo_ref[off_x[0]:off_x[1], off_y[0]:off_y[1], off_z[0]:off_z[1]]
                        out_svol = out_seg_dir + '/' + out_ref_stem + '_id_' + str(tomo_id) + '_split_' + str(split_id) + '.mrc'
                        out_seg = out_seg_dir + '/' + out_ref_stem + '_id_' + str(tomo_id) + '_split_' + str(split_id) + '_mb.mrc'
                        ps.disperse_io.save_numpy(svol, out_svol)
                        ps.disperse_io.save_numpy(svol_seg, out_seg)
                        split_id += 1
                        row_dic = dict()
                        row_dic['_rlnMicrographName'] = in_ref
                        row_dic['_rlnImageName'] = out_svol
                        row_dic['_psSegImage'] = out_seg
                        row_dic['_psSegRot'] = 0
                        row_dic['_psSegTilt'] = 0
                        row_dic['_psSegPsi'] = 0
                        row_dic['_psSegOffX'] = off_x[0]
                        row_dic['_psSegOffY'] = off_y[0]
                        row_dic['_psSegOffZ'] = off_z[0]
                        star.add_row(**row_dic)

    # Prepare next iteration
    gc.collect()
    tomo_id += 1

out_star = out_dir + '/' + out_stem + '_pre.star'
print '\tStoring output STAR file in: ' + out_star
star.store(out_star)

print 'Terminated. (' + time.strftime("%c") + ')'