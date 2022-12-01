#!/bin/bash
##############################################
# Author : Eric Blaudez
# Copyright (c) 2021 by THALES
# Description:
# Install nodejs & elasticdump to into docker
##############################################
# install nodejs and elasticdump
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.35.3/install.sh | bash; 
export NVM_DIR="$HOME/.nvm"; 
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh";
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion";
nvm install 14.17.5;
npm install elasticdump -g;
