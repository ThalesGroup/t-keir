#!/bin/bash
set -e
script_path=$(dirname "$0")
cd "$script_path"
rm -f .coverage .coverage.* 2>/dev/null || true

# Keep in sync with UnitTestSuite.sh plus modules that raise scoped coverage.
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
    unittests/TestActionLayer.py
    unittests/TestIngest.py
    unittests/TestAudit.py
    unittests/TestGovernor.py
    unittests/TestInstaller.py
    unittests/TestToolsDocExamples.py
    unittests/TestAllDocExamples.py
    unittests/TestDocExampleCoverage.py
    unittests/TestSpacyTokenizerPipe.py
    unittests/TestInputFormat.py
    unittests/TestTitleGenerator.py
    unittests/TestPipelineSummary.py
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
    functional_tests/TestPipeline.py
)

uv run --python 3.11 python -m coverage run \
    --rcfile=../pyproject.toml --source=thot \
    -m pytest "${ACTIVE_TESTS[@]}" -q

COVERAGE_FAIL_UNDER="${COVERAGE_FAIL_UNDER:-90}"
COVERAGE_REPORT_DIR="${COVERAGE_REPORT_DIR:-../../coverage-reports}"

uv run --python 3.11 python -m coverage report \
    --rcfile=../pyproject.toml \
    --fail-under="${COVERAGE_FAIL_UNDER}"
uv run --python 3.11 python -m coverage xml
mkdir -p "${COVERAGE_REPORT_DIR}"
mv coverage.xml "${COVERAGE_REPORT_DIR}/"
