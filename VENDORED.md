# Vendored leaf support

Source: [hibou04-ops/omegaprompt](https://github.com/hibou04-ops/omegaprompt/tree/b197427765963100df25960524f01bf789a9303f/src/omegaprompt), commit `b197427765963100df25960524f01bf789a9303f` (v2.2.3).
Copyright 2026 Kyunghoon Gwak. Apache-2.0; original LICENSE and NOTICE are retained in this directory.

Only the probe-facing dataset/rubric/enums/profiles, provider contracts and lazy SDK adapters, LLMJudge, measurement records and adaptation-plan functions are included. The calibration runtime, target/search engine, omega-lock, NumPy and provider SDKs are not vendored. SDK imports remain lazy and live callers install the selected SDK separately.

Changes: namespace imports use `mini_omega_lock._vendor`; package initializers export only required leaf types; the pipeline-only `apply_ship_gate_escalation` function was omitted from adaptation.py to avoid importing the parent artifact engine. Otherwise these vendored algorithms retain the source behavior.

This is a source snapshot, not a second calibration engine. Future upstream security or contract changes require an explicit reviewed update. The core never automatically imports omegaprompt. Optional interoperability uses `mini_omega_lock.bridge`: JSON records are validated into the parent classes, and the provider adapter translates capabilities, requests, parsed outputs and provider exceptions. Parent Pydantic objects must pass through that boundary, not be assumed to share class identity.

Original file SHA-256 values before namespace changes:

| Original path | SHA-256 |
|---|---|
| `domain/dataset.py` | `da2ad3889c957b78e374f813a7533e536d5400b4abd72a2999b156abfa8487dd` |
| `domain/enums.py` | `10c9c435e82885a730b71395215477a88e4c9cc3086867d8f144c84612678c4c` |
| `domain/judge.py` | `114cdf7272420018f43e9b7cd5af63b9d564403722500dd99b9214c3e9d5a946` |
| `domain/profiles.py` | `92e778cd66c3b272e01bae64d12a31a8726d0c25220a872ae5d3fd8390b4a5d2` |
| `providers/base.py` | `e270a875340b50555a67fc5adf9bea30f8277513d8a1131b7245ec6601661c20` |
| `providers/factory.py` | `96a382210322f2b7547ff3364afadd612cb4d5cef42fc5b23984452f39218be2` |
| `providers/anthropic_provider.py` | `4f7a768a7eb1deda5c363008c3c1440ba9a443a404da73c541c49eb7ca07f068` |
| `providers/openai_provider.py` | `897e13def9f4fe166eb603a287bbc071816e4f988bcbe9379e3b59e34583fa48` |
| `providers/gemini_provider.py` | `8d5ead2041fe5f268c29792e91178eb28cc22492e04789dcfcade6ac4c4c5e62` |
| `providers/local_provider.py` | `aa59e61b9dd112122c2fb74923912e2540a476fec5bd3dfeed2eb37d6f5e1538` |
| `providers/ollama_provider.py` | `08449e65174305cc810c9cb4a1217104a2839a3b6e314afef0c4cba9917fbda4` |
| `providers/__init__.py` | `da1277fa143f703024fde6731650e3ab756bad48de9f460fa6aee4a923bed430` |
| `judges/base.py` | `9747bc2d5f16183368a7f33234a7ab287bc1ad1a11894f45490a148cedc94e8e` |
| `judges/llm_judge.py` | `244f58bd5599b64cf0d403df998f0a085e9d3aff111ef0bbae0e7bfd7396c608` |
| `preflight/contracts.py` | `288f12c2e8e53ef84e2a058e5803f53b95bb05ce4f5a9077867a71c2d6bbd0b2` |
| `preflight/adaptation.py` | `f948f1575cdcd72dfaec772bb89845137a96f0046e0557999c5643b030a6b153` |
