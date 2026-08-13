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
    unittests/TestJsonRecords.py
    unittests/TestUserWorkspace.py
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
    unittests/TestOkfModels.py
    unittests/tools/test_collector.py
    unittests/TestOkfExporter.py
    unittests/TestOkfApplicator.py
    unittests/TestOkfMcpTools.py
    unittests/TestOkfServer.py
    unittests/TestOkfExtra.py
    unittests/okf/test_iterative_wiki.py
    unittests/okf/test_chunk_cluster.py
    unittests/agent/test_agent_paths.py
    functional_tests/TestPipeline.py
    functional_tests/TestOkfWorkflow.py
)

uv run --project ../tkeir --python 3.11 python -m coverage run \
    --rcfile=../tkeir/pyproject.toml --source=thot \
    -m pytest "${ACTIVE_TESTS[@]}" -q

COVERAGE_FAIL_UNDER="${COVERAGE_FAIL_UNDER:-90}"
COVERAGE_REPORT_DIR="${COVERAGE_REPORT_DIR:-../coverage-reports}"
QUALITY_REPORT_DIR="${QUALITY_REPORT_DIR:-../reports/quality}"
export COVERAGE_FAIL_UNDER COVERAGE_REPORT_DIR QUALITY_REPORT_DIR

mkdir -p "${COVERAGE_REPORT_DIR}" "${QUALITY_REPORT_DIR}"

uv run --project ../tkeir --python 3.11 python -m coverage report \
    --rcfile=../tkeir/pyproject.toml \
    --fail-under="${COVERAGE_FAIL_UNDER}" \
    | tee "${QUALITY_REPORT_DIR}/coverage_report.txt"

uv run --project ../tkeir --python 3.11 python -m coverage xml -o "${COVERAGE_REPORT_DIR}/coverage.xml"
cp "${COVERAGE_REPORT_DIR}/coverage.xml" "${QUALITY_REPORT_DIR}/coverage.xml"

uv run --project ../tkeir --python 3.11 python -m coverage json \
    --rcfile=../tkeir/pyproject.toml \
    -o "${QUALITY_REPORT_DIR}/coverage.json"

# Compact summary for the quality dashboard (TOTAL line from the scoped report).
{
  echo "threshold_percent=${COVERAGE_FAIL_UNDER}"
  grep -E '^TOTAL' "${QUALITY_REPORT_DIR}/coverage_report.txt" || true
  python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["QUALITY_REPORT_DIR"]) / "coverage.json"
data = json.loads(path.read_text(encoding="utf-8"))
totals = data.get("totals", {})
print(f"percent_covered={totals.get('percent_covered')}")
print(f"num_statements={totals.get('num_statements')}")
print(f"covered_lines={totals.get('covered_lines')}")
print(f"missing_lines={totals.get('missing_lines')}")
PY
} > "${QUALITY_REPORT_DIR}/coverage_summary.txt"
