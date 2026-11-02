"""Actual preflight warnings survive restricted terminal encoding unchanged in JSON."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("output_format", ["text", "json", "jsonl"])
def test_actual_warning_output_is_safe_on_strict_cp949(tmp_path, output_format):
    expected_path = tmp_path / "measurement.json"
    program = r'''
import json
from pathlib import Path
import sys
from mini_omega_lock import cli
from mini_omega_lock._vendor.domain.judge import JudgeResult
from mini_omega_lock._vendor.providers.base import CapabilityTier, ProviderCapabilities, ProviderResponse
import mini_omega_lock._vendor.providers as providers

class OfflineProvider:
    name = 'anthropic'
    model = 'offline'
    def call(self, request):
        return ProviderResponse(parsed=JudgeResult(scores={'accuracy': 4}, gate_results={}),
                                usage={'input_tokens': 50, 'output_tokens': 10}, latency_ms=5.0)
    def capabilities(self):
        return ProviderCapabilities(provider=self.name, tier=CapabilityTier.CLOUD,
            supports_strict_schema=True, supports_llm_judge=True, ship_grade_judge=True)

providers.make_provider = lambda *args, **kwargs: OfflineProvider()
original_preflight = cli._run_preflight
def record_actual_measurement(args):
    result = original_preflight(args)
    Path(sys.argv[1]).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return result
cli._run_preflight = record_actual_measurement
encoding = sys.stdout.encoding
assert encoding.lower() == 'cp949'
rubric = json.dumps({'dimensions': [{'name': 'accuracy', 'description': 'correct', 'weight': 1.0}]})
item = json.dumps({'id': 'probe', 'input': '2+2', 'reference': '4'})
code = cli.main(['--provider', 'anthropic', '--rubric', rubric, '--probe-item', item,
                 '--probe-response', '4', '--consistency-repeats', '1', '--' + sys.argv[2]])
assert sys.stdout.encoding == encoding
raise SystemExit(code)
'''
    environment = os.environ.copy()
    environment.update(PYTHONUTF8="0", PYTHONIOENCODING="cp949:strict")
    result = subprocess.run([sys.executable, "-c", program, str(expected_path), output_format],
                            capture_output=True, env=environment, check=False)
    assert result.returncode == 2, result.stderr.decode("cp949")
    output = result.stdout.decode("cp949")
    assert output.isascii()
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert any("—" in warning for warning in expected["warnings"])
    if output_format == "json":
        assert json.loads(output) == expected
    elif output_format == "jsonl":
        report, plan = [json.loads(line) for line in output.splitlines()]
        assert report == {key: expected[key] for key in (
            "judge_quality", "endpoint", "performance", "warnings", "measurement_status",
            "probe_accounting", "required_measurements", "quality_thresholds_configured", "quality_assessment",
        )}
        assert plan == {"adaptation_plan": expected["adaptation_plan"]}
    else:
        for warning in expected["warnings"]:
            assert " ".join(warning.replace("—", "-").split()) in output
