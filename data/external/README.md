# External Data

Third-party datasets are immutable inputs. RouteBench code must access them through a
named adapter and must not silently rewrite, merge, relabel, or train on evaluator-only
fields. Raw dataset directories are ignored by Git; this file records their provenance.

## ATBench

- Local path: `data/external/atbench/`
- Upstream: https://github.com/AI45Lab/AgentDoG
- Dataset page: https://huggingface.co/datasets/AI45Research/ATBench
- Upstream license: Apache-2.0
- Relative-path content manifest SHA-256: `7009c3f62655aca0254815342d53b5cb8118e6aca86769dcccc352b49875492b`
- Imported size: approximately 35 MB across 15 files

`ATBench/test.json` is the 1,000-trajectory release. `ATBench500/test.json` is the
legacy 500-trajectory release. The root `test.json` duplicates the legacy release and
must not be treated as the latest dataset.

ATBench is an offline trajectory-classification dataset, not an executable task
environment. RouteBench uses its taxonomy and an optional offline adapter; it is not
mixed into runtime-authorization metrics.
