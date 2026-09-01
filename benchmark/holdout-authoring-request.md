# Independent holdout authoring request

Create exactly three evaluator-only benchmark bundles for dsh-houdini: one `mechanical`, one `simulation`, and one `lookdev`, all with `instanceRole="holdout"`.

The author must not reveal the task text, evaluator criteria, target parameters, reference material, node recipe, or answer files to the implementation/design thread before production-surface freeze. Do not inspect existing calibration/counterexample content. Design distinct tasks that exercise the capability-family boundaries in `docs/cross-domain-benchmark-plan.md`, not wording or parameter variations of known tasks.

Each bundle must contain:

- `public-brief.json` matching `benchmark/public-brief.schema.json`;
- `allowed-answers.json` matching `benchmark/allowed-answers.schema.json`;
- `seed-fixture.json` matching `benchmark/seed-fixture.schema.json`;
- `evaluator-spec.json` matching `benchmark/evaluator-spec.schema.json`;
- any public resource files referenced by the brief;
- `sealed-manifest.json` produced by `tools/benchmark-instance.mjs seal`.

Use production-surface commit `4316620011cf74b1b489448d57aaf28e2bfcadc3` and keep all bundle files outside the plugin repository and execution `$HIP` workspace. The evaluator spec must total exactly 40/25/25/10 points, use hard failures only for existing `critical=true` criteria, and never expose evaluator material to the execution agent.

Return only these values to the implementation thread before freeze:

```json
{
  "mechanical": "<sealedInstanceSha256>",
  "simulation": "<sealedInstanceSha256>",
  "lookdev": "<sealedInstanceSha256>"
}
```

Retain the actual bundles privately. After the implementation thread freezes the final protocol and production surface, provide the bundle files to the evaluator/run operator. Once revealed or executed, each holdout automatically becomes calibration material for future rounds and must never be reused as unseen evidence.
