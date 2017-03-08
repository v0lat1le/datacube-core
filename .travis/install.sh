#!/usr/bin/env bash

if test -e $HOME/miniconda/envs/pyenv; then
    echo "pyenv already exists."
else
    echo "Creating pyenv."
    conda create --yes -q -n pyenv -c conda-forge python=$TRAVIS_PYTHON_VERSION
fi

source activate pyenv

conda config --show-sources
conda config --show
conda info -a

conda install --yes -q -c conda-forge --file .travis/conda_packages_py${TRAVIS_PYTHON_VERSION//.}.txt
pip install -r .travis/pip_packages_py${TRAVIS_PYTHON_VERSION//.}.txt

source deactivate
