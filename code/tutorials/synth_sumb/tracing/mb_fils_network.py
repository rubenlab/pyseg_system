"""

    Script for filter a MbGraphMCF object by extracting a filament network

    Input:  - A STAR file with a list of graphs (MbGraphMCF) as it is returned by
              by mb_graph.py script:
            	+ Density map tomogram
            	+ Segmentation tomogram
                + MbGraphMCF object
            - XML files for segmenting source and target vertices
            - Filament settings

    Output: - A STAR file with filtered version of the input MbGraphMCF with filaments network
            - Additional files for visualization

"""

__author__ = 'Antonio Martinez-Sanchez'

# ################ Package import
import argparse
import gc
import os
import time
import pyseg as ps
try:
    import pickle as pickle
except:
    import pickle

########## Global variables

########################################################################################
# PARAMETERS
########################################################################################

####### Input data

ROOT_PATH = '/scratch/users/muth9/simsiam/particle_picking' # Data path

# Input STAR file with the GraphMCF pickles
in_star = ROOT_PATH + '/data/graphs/PN_seg_mb_graph.star' # The outuput of mb_graph.py

# Sources slice XML file
in_sources = ROOT_PATH + '/pyseg-container/pyseg_system/data/tutorials/synth_sumb/tracing/fils/in/mb_sources.xml'

# Targets slice XML file
in_targets = ROOT_PATH + '/pyseg-container/pyseg_system/data/tutorials/synth_sumb/tracing/fils/in/no_mb_targets.xml'

####### Output data

out_dir = ROOT_PATH + '/data/fils' # '/fils/cyto'
out_int_g = True

####### Filament geometrical parameters

g_rg_len = [1, 60] # [1, 50] # [1, 75] # nm (>0)
g_rg_sin = [0, 3]
g_rg_eud = [1, 25] # [1, 15] # [1, 25] # nm (>0)

####### Graph thresholding (Advanced parameters)

th_mode = 'in' # 'out'

########################################################################################
# MAIN ROUTINE
########################################################################################

# Get them from the command line if they were passed through it
parser = argparse.ArgumentParser()
parser.add_argument('--inStar', default=in_star, help='Input star file.')
parser.add_argument('--outDir', default=out_dir, help='Output subtomograms directory.')
parser.add_argument('--inSources', default=in_sources, help='Sources xml file.')
parser.add_argument('--inTargets', default=in_targets, help='Targets xml file.')
parser.add_argument('--thMode', default=th_mode, choices=['in', 'out'],
                    help='Orientation with respect to the membrane/filament.')
parser.add_argument('--gRgLen', nargs='+', type=int, default=g_rg_len,
                    help='Geodesic distance trough the graph between source and target vertices in nm.')
parser.add_argument('--gRgSin', nargs='+', type=int, default=g_rg_sin,
                    help='Filament sinuosity, geodesic/euclidean distances ratio.')
parser.add_argument('--gRgEud', nargs='+', type=int, default=g_rg_eud,
                    help='Euclidean distance between source and target vertices in nm.')
args = parser.parse_args()

in_star = args.inStar
out_dir = args.outDir
in_sources = args.inSources
in_targets = args.inTargets
th_mode = args.thMode
g_rg_len = args.gRgLen
g_rg_sin = args.gRgSin
g_rg_eud = args.gRgEud

# Print initial message
print('Filtering a MbGraphMCF by filaments network.')
print('\tAuthor: ' + __author__)
print('\tDate: ' + time.strftime("%c") + '\n')
print('Options:')
print('\tInput SynGraphMCF STAR file: ' + str(in_star))
print('\tSources slice file: ' + in_sources)
print('\tTargets slice file: ' + in_targets)
print('\tOutput directory: ' + out_dir)
if out_int_g:
    print('\t\t-Intermediate graph will also be stored.')
print('\tFilament geometrical parameters: ')
print('\t\t-Lengths range: ' + str(g_rg_len) + ' nm')
print('\t\t-Euclidean distance range: ' + str(g_rg_eud) + ' nm')
if g_rg_sin:
    print('\t\t-Sinuosity range (inclusive): ' + str(g_rg_sin))
else:
    print('\t\t-Sinuosity range (exclusive): ' + str(g_rg_sin))
print('')

# Getting stem strings
s_stem = os.path.splitext(os.path.split(in_sources)[1])[0]
t_stem = os.path.splitext(os.path.split(in_targets)[1])[0]

print('Paring input star file...')
star = ps.sub.Star()
star.load(in_star)
in_graph_l = star.get_column_data('_psGhMCFPickle')
star.add_column('_psGhMCFPickle')
del_rows = list()

# Loop for processing the input data
print('Running main loop: ')
for row, in_graph in enumerate(in_graph_l):

    print('\tLoading input pickle: ' + in_graph)
    graph = ps.factory.unpickle_obj(in_graph)
    graph.compute_vertices_dst()
    graph.compute_vertices_fwdst()

    print('\tCompute GraphGT...')
    graph_gtt = ps.graph.GraphGT(graph)
    graph_gt = graph_gtt.get_gt()

    print('\tProcessing sources slice: ' + in_sources)
    s_slice = ps.xml_io.SliceSet(in_sources)
    try:
        _, s_ids, _ = graph.get_cloud_mb_slice(s_slice.get_slices_list()[0], cont_mode=False, graph_gt=graph_gt)
    except ValueError:
        print('WARNING: no points found in the slice, this row will be deleted from the STAR file!')
        del_rows.append(row)
        continue

    print('\tProcessing targets slice: ' + in_targets)
    t_slice = ps.xml_io.SliceSet(in_targets)
    try:
        _, t_ids, _ = graph.get_cloud_mb_slice(t_slice.get_slices_list()[0], cont_mode=False, graph_gt=graph_gt)
    except ValueError:
        print('WARNING: no points found in the slice, this row will be deleted from the STAR file!')
        del_rows.append(row)
        continue

    print('\tBuilding the filament network in lengths range ' + str(g_rg_len) + ' nm and sinuosity range ' + \
          str(g_rg_sin) + '...')
    net = graph.gen_fil_network(s_ids, t_ids, g_rg_len, g_rg_sin, graph_gt=graph_gt, key_l=ps.globals.SGT_EDGE_LENGTH)

    print('\tFiltering filaments by Euclidean distance between extrema with range ' + str(g_rg_eud) + ' nm')
    net.filter_by_eud(g_rg_eud[0], g_rg_eud[1], inc=True)

    print('\tFiltering the Graph...')
    net.filter_graph_mcf(graph, mode=th_mode)

    print('\tAdding filamentness to the Graph...')
    net.add_vprop_graph_mcf(graph, key_p=ps.filament.globals.STR_FIL_FNESS, mode='max')

    print('\tComputing output paths...')
    p_stem = os.path.splitext(os.path.split(in_graph)[1])[0]
    out_stem = out_dir + '/' + p_stem + '_fil_' + s_stem + '_to_' + t_stem + '_net'

    out_pkl = out_stem + '.pkl'
    print('\tStoring filtered graph as: ' + out_pkl)
    graph.pickle(out_pkl)
    star.set_element('_psGhMCFPickle', row, out_pkl)

    if out_int_g == 1:
        print('\tStoring intermediate graphs...')
        ps.disperse_io.save_vtp(graph.get_vtp(av_mode=True, edges=True), out_stem + '_edges.vtp')
        ps.disperse_io.save_vtp(graph.get_vtp(av_mode=True, edges=True), out_stem + '_edges2.vtp')
        # ps.disperse_io.save_vtp(graph.get_scheme_vtp(nodes=True, edges=True), out_stem + '_sch.vtp')

    print('\tStoring filament network in: ' + out_stem + '.vtp')
    ps.disperse_io.save_vtp(net.get_vtp(), out_stem+'.vtp')

    gc.collect()

if len(del_rows) > 0:
    print('\tDeleting empty rows...')
    star.del_rows(del_rows)

out_star = out_dir + '/fil_' + s_stem + '_to_' + t_stem + '_net.star'
print('\tStoring output STAR file in: ' + out_star)
star.store(out_star)

print('Terminated. (' + time.strftime("%c") + ')')