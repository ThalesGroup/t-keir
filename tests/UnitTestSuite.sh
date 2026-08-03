#!/bin/bash
set -e
script_path=$(cd "$(dirname "$0")" && pwd)
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
    unittests/TestConfigurationUtils.py
    unittests/TestQueryAnalyzer.py
    unittests/TestOkfModels.py
    unittests/TestOkfExporter.py
    unittests/TestOkfApplicator.py
    unittests/TestOkfMcpTools.py
    unittests/TestOkfServer.py
    unittests/TestOkfExtra.py
    unittests/okf/test_iterative_wiki.py
    unittests/agent/test_agent_paths.py
    unittests/TestJsonRecords.py
    unittests/TestUserWorkspace.py
    functional_tests/TestPipeline.py
    functional_tests/TestOkfWorkflow.py
)

uv run --project ../tkeir --python 3.11 pytest "${ACTIVE_TESTS[@]}" -q "$@"
