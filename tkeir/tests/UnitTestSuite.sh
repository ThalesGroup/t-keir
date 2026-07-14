#!/bin/bash
set -e
script_path=$(dirname "$0")
cd "$script_path"

ACTIVE_TESTS=(
    unittests/TestConstants.py
    unittests/TestDictionaryTrie.py
    unittests/TestAnnotationConfiguration.py
    unittests/TestCommonConfiguration.py
    unittests/TestConverterConfiguration.py
    unittests/TestKeywordsConfiguration.py
    unittests/TestLoggerConfiguration.py
    unittests/TestMorphoSyntacticTaggerConfiguration.py
    unittests/TestNERTaggerConfiguration.py
    unittests/TestSyntacticTaggerConfiguration.py
    unittests/TestTokenizerConfiguration.py
    unittests/TestTkeirPaths.py
    unittests/TestVespaClient.py
    unittests/TestOntologyUtils.py
    unittests/TestToolsDocExamples.py
    unittests/TestAllDocExamples.py
    unittests/TestDocExampleCoverage.py
    unittests/TestSpacyTokenizerPipe.py
    unittests/TestLanguageDetector.py
    unittests/TestSentenceSegmenter.py
    unittests/TestSpacyModelLoader.py
    unittests/TestResourceSelector.py
    unittests/TestPipelineConfiguration.py
    unittests/TestPipelineTasks.py
    unittests/TestPipelineRunner.py
    unittests/TestPipeline.py
    unittests/TestSyntacticTagger.py
    unittests/TestConverter.py
    unittests/TestMarkItDownConverter.py
    unittests/TestPdfImageOcr.py
    unittests/TestKeywordsExtractor.py
    unittests/TestMorphoSyntacticTagger.py
    unittests/TestTokenizerMultilingual.py
    unittests/TestRawConverter.py
    unittests/TestThotLogger.py
    unittests/TestUtils.py
    unittests/TestLlmWrapper.py
    unittests/TestQueryAnalyzer.py
    functional_tests/TestPipeline.py
)

uv run --python 3.11 pytest "${ACTIVE_TESTS[@]}" -q "$@"
