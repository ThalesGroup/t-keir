#!/bin/bash
################################################
# Author : Eric Blaudez
# Copyright (c) 2019 by THALES
# Wait : avoid container exit
################################################

trap 'stop_signal' 2 3 6 9 15

stop_signal()
{
  log_date=`date +"%F [%H:%M:%S]"`
  echo "$log_date Caught STOP. Okay I'll quit ..."
  exit 1
}

### main script
while :
do
  log_date=`date +"%F [%H:%M:%S]"`
  echo "$log_date NLP SERVICE UP with pid $$"
  sleep 15
done
