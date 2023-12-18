#!/bin/bash
set -ex

if [ -x "$(command -v conda)" ]; then 
  clean_exe="conda"
elif [ -x "$(command -v $PWD/soft/miniconda3/bin/conda)" ]; then 
  clean_exe="$PWD/soft/miniconda3/bin/conda"
  source $PWD/soft/miniconda3/bin/activate
else 
  echo "ERROR!! Conda not installed! Exiting..."
  exit
fi

if [ -x "$(command -v mamba)" ]; then 
  install_exe="mamba"
else
  install_exe="$clean_exe"
fi

solver_cmd="$install_exe install --yes"
if ! $install_exe install conda-libmamba-solver --yes && conda config --set solver libmamba ; then
  if $solver_cmd mrcfile --solver=libmamba ; then
    echo "Found conda-libmamba-solver"
    solver_cmd="$install_exe install --yes --solver=libmamba"
  else
    echo "Found conda-libmamba-solver but couldn't use it"
  fi
else
  echo "Did not find conda-libmamba-solver"
fi

$solver_cmd --channel conda-forge --channel anaconda \
  "numpy<1.25.0" \
  "python<3.10.0a0"\
  "opencv>=4.2.0" \
  "graph-tool>=2.29" \
  future=0.18.2 \
  pip=23.3 \
  mrcfile
$install_exe clean --yes --all
pip install setuptools
pip install beautifulsoup4==4.9.3 \
  lxml \
  pillow \
  pywavelets \
  scikit-image \
  scikit-learn \
  scikit-fmm \
  scipy \
  vtk \
  astropy \
  imageio
$install_exe clean --yes --all

