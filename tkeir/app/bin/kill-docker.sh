#!/bin/bash
##############################################
# Author : Eric Blaudez
# Copyright (c) 2019 by THALES
# Description:
# Kill tkeir images
##############################################
docker ps -a | grep tkeir | cut -d" " -f 1 | xargs docker stop
docker ps -a | grep tkeir | cut -d" " -f 1 | xargs docker rm
docker rm -v $(docker ps -a -q -f status=exited)

