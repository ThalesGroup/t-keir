#!/bin/bash
#############################################
# Author : Eric Blaudez
# Copyright (c) 2019 by THALES

test_fail=0
script_path=`dirname $0`
tkeir_path=`realpath $script_path/..`
pushd $script_path
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

rm -f .coverage*;


COVERAGE_FILE=.coverage_TestConstants python3 -m coverage run --source=thot -m unittest unittests/TestConstants.py;
log "TestConstants"

COVERAGE_FILE=.coverage_TestDictionaryTrie python3 -m coverage run --source=thot -m unittest unittests/TestDictionaryTrie.py;
log "TestDictionaryTrie"

COVERAGE_FILE=.coverage_TestNetworkConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestNetworkConfiguration.py;
log "TestNetworkConfiguration"

COVERAGE_FILE=.coverage_TestAnnotationConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestAnnotationConfiguration.py;
log "TestAnnotationConfiguration"

COVERAGE_FILE=.coverage_TestCommonConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestCommonConfiguration.py;
log "TestCommonConfiguration"

COVERAGE_FILE=.coverage_TestConverterConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestConverterConfiguration.py;
log "TestConverterConfiguration"

COVERAGE_FILE=.coverage_TestIndexingConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestIndexingConfiguration.py;
log "TestIndexingConfiguration"

COVERAGE_FILE=.coverage_TestKeywordsConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestKeywordsConfiguration.py;
log "TestKeywordsConfiguration"

COVERAGE_FILE=.coverage_TestLoggerConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestLoggerConfiguration.py;
log "TestLoggerConfiguration"

COVERAGE_FILE=.coverage_TestMorphoSyntacticTaggerConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestMorphoSyntacticTaggerConfiguration.py;
log "TestMorphoSyntacticTaggerConfiguration"

COVERAGE_FILE=.coverage_TestEmbeddingConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestEmbeddingConfiguration.py;
log "TestEmbeddingConfiguration"

COVERAGE_FILE=.coverage_TestLoggerConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestLoggerConfiguration.py;
log "TestLoggerConfiguration"

COVERAGE_FILE=.coverage_TestNERTaggerConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestNERTaggerConfiguration.py;
log "TestNERTaggerConfiguration"

COVERAGE_FILE=.coverage_TestQAConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestQAConfiguration.py;
log "TestQAConfiguration"

COVERAGE_FILE=.coverage_TestRelationClusterizerConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestRelationClusterizerConfiguration.py;
log "TestRelationClusterizerConfiguration"

COVERAGE_FILE=.coverage_TestSyntacticTaggerConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestSyntacticTaggerConfiguration.py;
log "TestSyntacticTaggerConfiguration"

COVERAGE_FILE=.coverage_TestTaggersPipelineConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestTaggersPipelineConfiguration.py;
log "TestTaggersPipelineConfiguration"

COVERAGE_FILE=.coverage_TestRuntimeConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestRuntimeConfiguration.py;
log "TestRuntimeConfiguration"

COVERAGE_FILE=.coverage_TestTokenizerConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestTokenizerConfiguration.py;
log "TestRuntimeConfiguration"

COVERAGE_FILE=.coverage_TestZeroShotClassificationConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestZeroShotClassificationConfiguration.py;
log "TestZeroShotClassificationConfiguration"

COVERAGE_FILE=.coverage_TestSentimentConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestSentimentConfiguration.py;
log "TestSentimentConfiguration"

COVERAGE_FILE=.coverage_TestSearchingConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestSearchingConfiguration.py;
log "TestSentimentConfiguration"

COVERAGE_FILE=.coverage_TestSummarizerConfiguration python3 -m coverage run --source=thot -m unittest unittests/TestSummarizerConfiguration.py;
log "TestSentimentConfiguration"

COVERAGE_FILE=.coverage_TestSyntacticTagger python3 -m coverage run --source=thot -m unittest unittests/TestSyntacticTagger.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestEmbeddings python3 -m coverage run --source=thot -m unittest unittests/TestEmbeddings.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestConverter python3 -m coverage run --source=thot -m unittest unittests/TestConverter.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestAnnotationResources python3 -m coverage run --source=thot -m unittest unittests/TestAnnotationResources.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestEmailConverter python3 -m coverage run --source=thot -m unittest unittests/TestEmailConverter.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestURIConverter python3 -m coverage run --source=thot -m unittest unittests/TestURIConverter.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestKeywordsExtractor python3 -m coverage run --source=thot -m unittest unittests/TestKeywordsExtractor.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestMorphoSyntacticTagger python3 -m coverage run --source=thot -m unittest unittests/TestMorphoSyntacticTagger.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestNERTagger python3 -m coverage run --source=thot -m unittest unittests/TestNERTagger.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestRawConverter python3 -m coverage run --source=thot -m unittest unittests/TestRawConverter.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestThotLogger python3 -m coverage run --source=thot -m unittest unittests/TestThotLogger.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestTokenizer python3 -m coverage run --source=thot -m unittest unittests/TestTokenizer.py;
log "TestSyntacticTagger"

COVERAGE_FILE=.coverage_TestQueryExpansion python3 -m coverage run --source=thot -m unittest unittests/TestQueryExpansion.py;
log "TestQueryExpansion"

COVERAGE_FILE=.coverage_TestScorer python3 -m coverage run --source=thot -m unittest unittests/TestScorer.py;
log "TestQueryExpansion"

COVERAGE_FILE=.coverage_TestTextQueryFormulator python3 -m coverage run --source=thot -m unittest unittests/TestTextQueryFormulator.py;
log "TestQueryExpansion"

COVERAGE_FILE=.coverage_TestZeroShotClassification python3 -m coverage run --source=thot -m unittest unittests/TestZeroShotClassification.py;
log "TestQueryExpansion"

COVERAGE_FILE=.coverage_TestQA python3 -m coverage run --source=thot -m unittest unittests/TestQA.py;
log "TestQueryExpansion"

COVERAGE_FILE=.coverage_TestSentiment python3 -m coverage run --source=thot -m unittest unittests/TestSentiment.py;
log "TestQueryExpansion"

COVERAGE_FILE=.coverage_TestSummarizer python3 -m coverage run --source=thot -m unittest unittests/TestSummarizer.py;
log "TestQueryExpansion"

COVERAGE_FILE=.coverage_TestConverterSvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestConverterSvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestTokenizerSvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestTokenizerSvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestMSTaggerSvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestMSTaggerSvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestNERTaggerSvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestNERTaggerSvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestSyntacticTaggerSvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestSyntacticTaggerSvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestKeywordsExtractorSvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestKeywordsExtractorSvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestEmbeddingsSvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestEmbeddingsSvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestQASvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestQASvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestZeroshotClassifierSvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestZeroshotClassifierSvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestSummarizerSvc python3 -m coverage run --source=thot -m unittest tests/functional_tests/TestSummarizerSvc.py;
log "TestConverterSvc"

COVERAGE_FILE=.coverage_TestClusterInferClient python3 -m unittest unittests/TestClusterInferClient.py
log "TestClusterInferClient"

COVERAGE_FILE=.coverage_TestIndexClient python3 -m unittest unittests/TestIndexClient.py
log "TestIndexClient"

COVERAGE_FILE=.coverage_TestNERTaggerClient python3 -m unittest unittests/TestIndexClient.py
log "TestNERTaggerClient"

COVERAGE_FILE=.coverage_TestConvertClient python3 -m unittest unittests/TestConverterClient.py
log "TestConverterClient"

COVERAGE_FILE=.coverage_TestKeywordClient python3 -m unittest unittests/TestKeywordClient.py
log "TestKeywordClient"

COVERAGE_FILE=.coverage_TestTokenizerClient python3 -m unittest unittests/TestTokenizerClient.py
log "TestTokenizerClient"

COVERAGE_FILE=.coverage_TestEmbeddingsClient python3 -m unittest unittests/TestEmbeddingsClient.py
log "TestEmbeddingClient"

COVERAGE_FILE=.coverage_TestMSTaggerClient python3 -m unittest unittests/TestMSTaggerClient.py
log "TestMSTaggerClient"


python3 -m coverage combine .coverage_*
python3 -m coverage report
python3 -m coverage xml
mkdir -p ../../coverage-reports

mv coverage.xml ../../coverage-reports/
echo -ne "\n************\n"
echo -ne "Test summary:"
echo -ne "\n************\n"
cat testsuite.log

exit $test_fail
#python3 -m unittest unittests/TestTaggersPipeline.py
#python3 -m unittest unittests/TestSearching.py


