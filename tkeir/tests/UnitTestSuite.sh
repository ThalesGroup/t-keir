#!/bin/bash
#############################################
# Author : Eric Blaudez
# Copyright (c) 2019 by THALES

test_fail=0
script_path=`dirname $0`
tkeir_path=`realpath $script_path/`
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

python3 -m unittest unittests/TestConstants.py
log "TestConstant"

python3 -m unittest unittests/TestDictionaryTrie.py
log "TestDictionaryTrie"

python3 -m unittest unittests/TestNetworkConfiguration.py
log "TestNetworkConfiguration"

python3 -m unittest unittests/TestAnnotationConfiguration.py
log "TestAnnotationConfiguration"

python3 -m unittest unittests/TestCommonConfiguration.py
log "TestCommonConfiguration"

python3 -m unittest unittests/TestConverterConfiguration.py
log "TestConverterConfiguration"

python3 -m unittest unittests/TestIndexingConfiguration.py
log "TestIndexingConfiguration"

python3 -m unittest unittests/TestKeywordsConfiguration.py
log "TestKeywordsConfiguration"

python3 -m unittest unittests/TestLoggerConfiguration.py
log "TestLoggerConfiguration"

python3 -m unittest unittests/TestMorphoSyntacticTaggerConfiguration.py
log "TestMorphoSyntacticTaggerConfiguration"

python3 -m unittest unittests/TestEmbeddingConfiguration.py
log "TestEmbeddingConfiguration"

python3 -m unittest unittests/TestLoggerConfiguration.py
log "TestLoggerConfiguration"

python3 -m unittest unittests/TestNERTaggerConfiguration.py
log "TestNERTaggerConfiguration"

python3 -m unittest unittests/TestQAConfiguration.py
log "TestQAConfiguration"

python3 -m unittest unittests/TestRelationClusterizerConfiguration.py
log "TestRelationClusterizerConfiguration"

python3 -m unittest unittests/TestSyntacticTaggerConfiguration.py
log "TestSyntacticTaggerConfiguration"

python3 -m unittest unittests/TestRuntimeConfiguration.py
log "TestRuntimeConfiguration"

python3 -m unittest unittests/TestTokenizerConfiguration.py
log "TestTokenizerConfiguration"

python3 -m unittest unittests/TestZeroShotClassificationConfiguration.py
log "TestZeroShotClassificationConfiguration"

python3 -m unittest unittests/TestSentimentConfiguration.py
log "TestSentimentConfiguration"

python3 -m unittest unittests/TestSearchingConfiguration.py
log "TestSearchingConfiguration"

python3 -m unittest unittests/TestSummarizerConfiguration.py
log "TestSummarizerConfiguration"

echo "Test basic NLP"
python3 -m unittest unittests/TestSyntacticTagger.py
log "TestSyntacticTagger"

python3 -m unittest unittests/TestConverter.py
log "TestConverter"

python3 -m unittest unittests/TestAnnotationResources.py
log "TestAnnotationResources"

python3 -m unittest unittests/TestEmailConverter.py
log "TestEmailConverter"

python3 -m unittest unittests/TestURIConverter.py
log "TestURIConverter"

python3 -m unittest unittests/TestKeywordsExtractor.py
log "TestKeywordsExtractor"

python3 -m unittest unittests/TestMorphoSyntacticTagger.py
log "TestMorphoSyntacticTagger"

python3 -m unittest unittests/TestRawConverter.py
log "TestRawConverter"

python3 -m unittest unittests/TestThotLogger.py
log "TestThotLogger"

python3 -m unittest unittests/TestUtils.py
log "TestUtils"

echo "Test High Level NLP"

python3 -m unittest unittests/TestScorer.py
log "TestScorer"

python3 -m unittest unittests/TestClusterInferClient.py
log "TestClusterInferClient"

python3 -m unittest unittests/TestIndexClient.py
log "TestIndexClient"

python3 -m unittest unittests/TestNERTaggerClient.py
log "TestNERTaggerClient"

python3 -m unittest unittests/TestConverterClient.py
log "TestConverterClient"

python3 -m unittest unittests/TestKeywordClient.py
log "TestKeywordClient"

python3 -m unittest unittests/TestTokenizerClient.py
log "TestTokenizerClient"

python3 -m unittest unittests/TestEmbeddingsClient.py
log "TestEmbeddingClient"

python3 -m unittest unittests/TestMSTaggerClient.py
log "TestMSTaggerClient"

#python3 -m unittest unittests/TestQueryExpansion.py
#log "TestQueryExpansion"

#python3 -m unittest unittests/TestTextQueryFormulator.py
#log "TestTextQueryFormulator"

#python3 -m unittest unittests/TestZeroShotClassification.py
#log "TestZeroShotClassification"

#python3 -m unittest unittests/TestQA.py
#log "TestQA"

#python3 -m unittest unittests/TestSentiment.py
#log "TestSentiment"

#python3 -m unittest unittests/TestSummarizer.py
#log "TestSummarizer"

#python3 -m unittest unittests/TestEmbeddings.py
#log "TestEmbeddings"

#python3 -m unittest unittests/TestNERTagger.py
#log "TestNERTagger"

#python3 -m unittest unittests/TestTokenizer.py
#log "TestTokenizer"



echo -ne "\n************\n"
echo -ne "Test summary:"
echo -ne "\n************\n"
cat testsuite.log

exit $test_fail
#python3 -m unittest unittests/TestTaggersPipeline.py
#python3 -m unittest unittests/TestTaggersPipelineConfiguration.py
#log "TestTaggersPipelineConfiguration"
#python3 -m unittest unittests/TestSearching.py


