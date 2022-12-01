#!/bin/bash
#############################################
# Author : Eric Blaudez
# Copyright (c) 2019 by THALES

test_fail=0
script_path=`dirname $0`
tkeir_path=`realpath $script_path/../..`
pushd $tkeir_path
rm -f testsuite.log;
log() {
    if [ $? -eq 0 ]; 
    then
        echo "[PASSED] $1" >> testsuite.log;
        echo "[*** PASSED ***] $1"
    else
        echo "[FAILED] $1" >> testsuite.log;
        echo "[### FAILED ###] $1"
        test_fail=1;
        
    fi
}



echo "Functional tests"
python3 -m unittest thot/tests/functional_tests/TestConverterSvc.py
log "TestConverterSvc"

python3 -m unittest thot/tests/functional_tests/TestTokenizerSvc.py
log "TestTokenizerSvc"

python3 -m unittest thot/tests/functional_tests/TestMSTaggerSvc.py
log "TestMSTaggerSvc"

python3 -m unittest thot/tests/functional_tests/TestNERTaggerSvc.py
log "TestNERTaggerSvc"

python3 -m unittest thot/tests/functional_tests/TestSyntacticTaggerSvc.py
log "TestSyntacticTaggerSvc"

python3 -m unittest thot/tests/functional_tests/TestKeywordsExtractorSvc.py
log "TestKeywordsExtractorSvc"

python3 -m unittest thot/tests/functional_tests/TestEmbeddingsSvc.py
log "TestEmbeddingsSvc"

python3 -m unittest thot/tests/functional_tests/TestQASvc.py
log "TestQASvc"

python3 -m unittest thot/tests/functional_tests/TestZeroshotClassifierSvc.py
log "TestZeroShotClassifierSvc"

python3 -m unittest thot/tests/functional_tests/TestSummarizerSvc.py
log "TestSummarizerSvc"

echo -ne "\n************\n"
echo -ne "Test summary:"
echo -ne "\n************\n"
cat testsuite.log

exit $test_fail
#python3 -m unittest thot/tests/unittests/TestTaggersPipeline.py
#python3 -m unittest thot/tests/unittests/TestSearching.py


