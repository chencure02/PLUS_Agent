#!/bin/bash
set -e
echo "Creating conda environment plus-agent..."
conda create -n plus-agent python=3.11 -y
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate plus-agent
echo "Installing GDAL via conda-forge..."
conda install -c conda-forge gdal -y
echo "Installing pip dependencies..."
python -m pip install -r requirements.txt
echo "Setup complete. Run: conda activate plus-agent && chainlit run agent/main.py"
