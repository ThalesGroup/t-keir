#!/bin/bash

script_path=`dirname $0`
cd $script_path

if [ -z $1 ] || [ $1 == "build" ]
then
  mkdir build
  sphinx-build -b html source build
  rm -rf ../../public
  mv build ../../public
elif [ $1 == "clean" ]
then
  rm -rf ../../public  
fi
