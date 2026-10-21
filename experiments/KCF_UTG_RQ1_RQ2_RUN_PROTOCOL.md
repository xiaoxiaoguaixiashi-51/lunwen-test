# KCF-UTG RQ1/RQ2 Run Protocol (Draft Freeze)

Status: protocol draft for a future clean environment; no results are claimed by this file.

The previous cloud instance was released and its uncommitted checkout, dependency
cache, generated tests, and experiment archives are treated as unavailable. GitHub
can restore only committed repository files. Any future result must therefore be
marked as a fresh run from this protocol; no cloud-side artifact is assumed to be
recoverable or reused.

## Route and fixed inputs

- Follow the 2026-07-09 route decision at the top of `../RESEARCH_PLAN.md`: RQ1 compares EvoSuite, RAG+LLM, and KCF-UTG; RQ2 evaluates A1/A2/A3 on the same 41 focal methods. Do not restore Stage A, RQ3/RQ4, DCCI, or MACO-aligned paper wording.
- Dataset manifest: `method_lists/kcf_utg_rq1_methods_v1.json` (41 unique IDs across six projects). Its SHA-256 is `98d82152e25894b3c174ceed96be28767ea7dd29979295b507281a96ff1a3980`.
- Dataset card: `kcf_utg_rq1_dataset_card_v1.json`. The project manifest SHA-256 is recorded there. Candidate refs are not resolved commit pins: every checkout must record `git rev-parse HEAD`; stop if it does not match the intended release/commit or the target source does not match the method-list entry.
- The manifest's `target` paths currently point to `/root/maco-aligned-projects/...`. Either recreate that root on the runner host or produce a separately hashed path-rebased copy. Never edit the frozen manifest in place. Verify all 41 target files and method IDs before generation.
- Freeze and record hashes for the method manifest, project manifest, knowledge JSONL, config, repository commit, generated run scripts, and each checked-out project commit. Keep secrets out of archived configs; record model/provider identifiers and parameters, not API keys.

## Comparability controls

- Use the same 41 IDs, project checkout commits, test framework/classpath, JaCoCo version, line/branch extraction code, JVM settings, and evaluator for all arms.
- Freeze the knowledge JSONL before any run. A1 must disable knowledge retrieval in both initial generation and feedback/repair. A2 disables only coverage-gap retrieval; initial knowledge retrieval and failure-repair retrieval remain enabled. A3 disables StaticGuard/project constraints consistently in initial generation, compile/runtime repair, and incremental feedback. Record actual effective flags in each run's metadata.
- Current `run_kcf_utg_feedback.py` delegates to the historical feedback runner. Its `--config` supplies LLM settings, but feedback retrieval path/count and StaticGuard mode are controlled by CLI options; pass `--knowledge-path` and `--max-knowledge-examples` explicitly. Initial batch generation reads retrieval/static-guard settings from YAML. Ensure the same frozen values are supplied to both stages.
- Do not reuse historical Ours-v3 XML for KCF-UTG round 0. Generate a fresh initial KCF batch, compile/run/evaluate those generated tests, then pass only that run's raw XML to the KCF feedback runner.
- Set equal, explicit per-focal-method generation/repair budgets across RAG+LLM and KCF-UTG where applicable. EvoSuite uses a frozen search budget per target class. Record all calls/tokens (prompt and completion), wall time, retries, compile/repair attempts, and timeouts. Report that EvoSuite's unit is target class if it differs from focal-method prompting; do not imply equal cost units without accounting for this.
- For every arm and ablation, keep one output root per independent run and seed/replicate label. Do not resume into another arm's directory. Record failures and missing coverage as failures; never silently drop a focal method.

## RQ1 execution order

1. Validate project checkouts and method targets; build all six projects with the commands in the project manifest and store logs/commit SHAs.
2. Run RAG+LLM generation using `src.core.rag_llm_baseline_runner`, then compile/run/collect JaCoCo with `scripts/run_stage_b_rag_llm_coverage.py`.
3. Run EvoSuite generation using `scripts/maco_stage_b.py evosuite-baseline` (legacy internal tool name only), then compile/run/collect JaCoCo with `scripts/run_stage_b_evosuite_coverage.py`.
4. Run KCF initial generation using `src.core.batch_runner` and the frozen KCF config with retrieval and StaticGuard enabled. Run `scripts/run_stage_b_ours_coverage.py` on this output to obtain the fresh round-0 JaCoCo XML.
5. Run `scripts/run_kcf_utg_feedback.py` with that round-0 XML, the same method list/projects/knowledge/config and a separate output directory. Its final cumulative focal-method line/branch report is the KCF-UTG result. Preserve round-0 and every feedback round.
6. Summarize all arms with the same focal-method denominator and evaluator; include compilation success, runtime success, line/branch coverage, failure categories, model cost, and wall time.

Before step 1, run `scripts/preflight_kcf_utg_run.py` and require exit code 0. The preflight is read-only and should run before any LLM call; it accepts either the frozen absolute targets or a path-rebased checkout under `--projects-root`.

## RQ2 ablation matrix

| Variant | Initial batch config | Feedback runner | Meaning |
|---|---|---|---|
| Full KCF-UTG | retrieval on; StaticGuard on | defaults (all retrieval/guard enabled) | Complete route |
| A1 | `config/config.kcf_utg_a1.yaml` | `--disable-coverage-gap-retrieval --disable-failure-repair-retrieval` | No knowledge retrieval anywhere |
| A2 | `config/config.kcf_utg.yaml` | `--disable-coverage-gap-retrieval` | No coverage-gap retrieval; other retrieval remains |
| A3 | `config/config.kcf_utg_a3.yaml` | `--disable-static-guard` | No StaticGuard/project constraints in either stage |

Before formal runs, verify A1/A2/A3 switches are effective end-to-end with a tiny smoke case and inspect metadata/prompts. The existing feedback CLI alone is insufficient to establish initial-stage ablation state. If this propagation is not implemented and tested, do not launch or label the ablation runs as RQ2.

## Evaluation and denominator policy

- The canonical method set and line/branch denominator come from the 41-method KCF manifest and a single reference extraction using the frozen project commits. Retain zero-covered entries for generation/compile/runtime failures if the focal denominator is known; list environment/build failures separately and explain any excluded target before calculating rates.
- A missing JaCoCo report is not grounds to shrink the denominator. Use the fixed-denominator normalizer only when method metadata and canonical reference denominators match; investigate metadata/denominator mismatches instead of forcing a conversion.
- The old A1 fixed-denominator value (74.7% line, 73.1% branch) is a corrected historical calculation, not a new run and not comparable to KCF-UTG unless the same pinned methods and denominator are verified.
- Repeat independent runs to estimate variance before selecting the formal repeat count. Publish per-run values and uncertainty; a single run is descriptive only.

## Entry-point templates

These are templates for the Linux experiment host after paths and commits have been validated. Replace `<...>` placeholders; do not copy old run directories as inputs.

```bash
python -m src.core.rag_llm_baseline_runner --methods experiments/method_lists/kcf_utg_rq1_methods_v1.json --output <run>/rag_llm/generated --config config/config.kcf_utg.yaml
python scripts/run_stage_b_rag_llm_coverage.py --method-list experiments/method_lists/kcf_utg_rq1_methods_v1.json --rag-dir <run>/rag_llm/generated --projects-root <projects> --output-dir <run>/rag_llm/coverage

python scripts/maco_stage_b.py evosuite-baseline --method-list experiments/method_lists/kcf_utg_rq1_methods_v1.json --projects-root <projects> --evosuite-jar <evosuite.jar> --output-dir <run>/evosuite/generated --search-budget <frozen-seconds>
python scripts/run_stage_b_evosuite_coverage.py --evosuite-summary <run>/evosuite/generated/evosuite_baseline_summary.csv --evosuite-dir <run>/evosuite/generated --projects-root <projects> --output-dir <run>/evosuite/coverage

python -m src.core.batch_runner --methods experiments/method_lists/kcf_utg_rq1_methods_v1.json --output <run>/kcf/initial --config config/config.kcf_utg.yaml --no-resume
python scripts/run_stage_b_ours_coverage.py --method-list experiments/method_lists/kcf_utg_rq1_methods_v1.json --ours-dir <run>/kcf/initial --projects-root <projects> --output-dir <run>/kcf/initial_coverage
python scripts/run_kcf_utg_feedback.py --method-list experiments/method_lists/kcf_utg_rq1_methods_v1.json --raw-xml-root <run>/kcf/initial_coverage --projects-root <projects> --output-dir <run>/kcf/feedback --config config/config.kcf_utg.yaml --knowledge-path experiments/knowledge/dependency_construction_knowledge.jsonl --max-knowledge-examples 3 --approach-name KCF_UTG
```

The RAG runner rejects `LUNWEN_ENABLE_JAVA6_GUARD`; make sure it is unset. The EvoSuite output filename shown above is produced by the current legacy internal tool.

For RQ2, use the corresponding initial config from the ablation matrix and append the listed feedback switches to the feedback command. A2 reuses the Full initial config; it differs only in the feedback-stage coverage-gap retrieval switch. Do not set `LUNWEN_ENABLE_JAVA6_GUARD` for one arm only; the explicit YAML StaticGuard setting is the controlled project-constraint treatment.

## Evidence package and claim gate

Archive configs with secrets removed, hashes, project commits, method IDs, raw generated Java, compile/runtime logs, retrieval IDs/effective flags, per-test JaCoCo XML, aggregate CSV/JSON, and cost records. Historical July artifacts remain immutable and must keep their historical labels. No RQ1/RQ2 result or novelty claim is considered updated until the fresh run passes integrity checks and all 41 targets are accounted for in each arm.
