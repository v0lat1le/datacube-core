#!/usr/bin/env bash

if test -e $HOME/miniconda/bin ; then
    echo "miniconda already installed."
else
    echo "Installing miniconda."
    rm -rf $HOME/miniconda
    wget -c https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -O $HOME/miniconda.sh
    bash $HOME/miniconda.sh -b -p $HOME/miniconda
fi
