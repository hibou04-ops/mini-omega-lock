"""Deterministic provider-call accounting; no live model or timing claim.

Run with an optional source tree to compare a preserved baseline checkout.
"""
import argparse
import json
import sys
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument("--source-root", type=Path)
args=parser.parse_args()
if args.source_root: sys.path.insert(0,str(args.source_root/"src"))

from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.judge import Dimension, HardGate, JudgeResult, JudgeRubric
from mini_omega_lock.probes import empirical_preflight


class Judge:
    def __init__(self): self.calls=0
    def score(self,**kwargs):
        self.calls+=1
        return JudgeResult(scores={"q":4},gate_results={"g":self.calls%2==1}), {"input_tokens":10,"output_tokens":2}


out=[]
for consistency,gates in [(3,5),(7,3),(3,0)]:
    judge=Judge()
    jq,ep,pf,warnings=empirical_preflight(judge=judge,
        rubric=JudgeRubric(dimensions=[Dimension(name="q",description="q",weight=1)],
            hard_gates=[HardGate(name="g",description="g",evaluator="judge")]),
        probe_item=DatasetItem(id="probe",input="question"),probe_response="answer",
        consistency_repeats=consistency,gate_flip_repeats=gates)
    out.append({"consistency_repeats":consistency,"gate_flip_repeats":gates,
                "actual_judge_calls":judge.calls,"consistency_samples":jq.samples,
                "consistency":jq.consistency,
                "observation_batches":getattr(warnings,"probe_accounting",{}).get("observation_batches")})
print(json.dumps({"kind":"deterministic development workload; not blinded or live model evidence","cases":out},indent=2))
