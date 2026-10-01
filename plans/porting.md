# Porting duhportinf: signal-first JavaScript inference

Status: planning draft updated with user decisions; implementation not started. P0–P4 sequence confirmed, including P2 hierarchical regex mapping, per-channel ready/valid tagging, and Verilator `--json-only` input. Remaining defaults and later-phase questions in §9.

Research snapshot: 2026-09-30. Repository baseline: `f7c02b6` (2019-12-18). Sources and upstream revisions in §10. External performance/accuracy numbers are upstream reports, not measurements on hardware signals.

## 1. Goal and recommended approach

Replace Python runtime and native numerical dependencies with JavaScript library usable from Node.js and browser. Preserve DUH workflows while generalizing inference from top-level ports to named signals.

Three distinct problems:

1. **Structure recovery:** infer hierarchy, repeated instances, vectors, bundles from names and metadata.
2. **Protocol recognition:** propose bus family, role, logical-signal mappings.
3. **Selection:** choose compatible proposals, expose alternatives and uncertainty, retain unmatched signals.

Recommended architecture: **deterministic structure + constrained assignment + optional learned ranking**.

- Ship useful, offline, model-free inference first. Do not equate modern inference with mandatory neural inference.
- Defer model implementation/benchmarks to **Phase 4: Laya**, running locally on desktop. Other models remain research references, not planned integrations.
- Use exact bipartite assignment for fixed group/bus pair; do not replace structural constraints with independent model choices.
- Keep browser-capable core free of filesystem, shell, Python, native addons, implicit network access.
- Support one regex mapping multiple sockets/channels into hierarchical bundles, with named captures defining group axes and signal roles. Keep explicit resolved membership alongside pattern.
- Keep human review central: proposals are not proof that wiring or protocol behavior is correct.

### 1.1 Confirmed scope and sequence

- **P0:** complete drop-in JS CLI replacement, including inference and bundling. Every shipped third-party runtime library must also work in browser; no temporary Node-only inference/parser dependency.
- **P1:** run same implementation in desktop browser, locally. No mobile target and no inference server dependency.
- **P2:** hierarchical multi-socket/channel regex mapping and bundle folding, with special per-channel ready/valid handshake tags.
- **P3:** improve signals/ports API; support Verilog portlists, VCD inventories, Verilator JSON through adapters.
- **P4:** optional local Laya inference; no Von export or hosted Jev integration in current scope.

CLI names/flags and DUH integration remain compatible; debug output may be redesigned/versioned. Packaging/tests/docs ship with each phase, not deferred until separate final milestone. Generic public API stabilization is P3; internal portable contracts start in P0 to avoid rewrite.

Not initial scope: full Verilog/SystemVerilog compiler, waveform-value analysis, functional protocol verification, full schematic editor, remote inference/upload, mandatory model training, arbitrary user-code execution. Use externally generated `verilator --json-only` output for HDL parsing/elaboration; importer runs entirely in browser-compatible JS. Separate raw-Verilog parser not required by current plan.

Desktop model download/RAM/latency budgets remain open; desktop-only and local inference do not themselves authorize unlimited model downloads.

## 2. Existing implementation: behavior to preserve or deliberately change

Reviewed all Python modules, tests, packaging helpers; also existing JS sketches, README, and `overview.md`.

### 2.1 Pipeline and module map

| File | Actual responsibility |
| --- | --- |
| `duhportinf/util.py` | DUH loading/ref resolution; signed-width conversion; assigned-port exclusion; name features; JSON output |
| `duhportinf/_bundle.py` | Token prefix tree; vector detection; passthrough flattening; candidate groups; ancestor/leaf-based pruning |
| `duhportinf/busdef.py` | JSON5 abstraction loading; master/slave variants; required/optional/illegal ports; user groups |
| `duhportinf/_optimize.py` | Cheap group scores; pair costs; greedy/LP assignment; sideband/user-group classification |
| `duhportinf/main_portinf.py` | Bus catalog discovery; shortlist; two pruning passes; inference CLI |
| `duhportinf/main_portbundler.py` | Bundle unassigned ports; bundler CLI |
| `duhportinf/test/test.py` | 13 tests covering bundles, grouping, coarse costs, mapping, user groups |

Current algorithm:

1. Convert physical port shorthand into `(name, width, direction)`; positive = input, negative = output. Symbolic width becomes unknown for scoring.
2. Exclude signals referenced by existing RTL-view interfaces/bundles.
3. Split names into words; construct prefix tree. Collapse consecutive numeric branches when each branch is singleton path and widths/directions agree. Vector counts as one assignment item, using member width, not summed width.
4. Flatten passthroughs. Normally propose groups with at least four assignment items. Root with at least 100 items gets special reduced interface.
5. Score each group against bus variants using width/direction counts and name overlap. Keep best five global plus up to four local candidates absent from global shortlist.
6. First group-pruning pass uses direction component of best global score, not full score.
7. Build rectangular pair-cost matrix. Try independent row minima; if column choices collide, solve assignment LP with CVXOPT/GLPK. Distinct row minima already attain sum-of-row-minima lower bound, hence are optimal for that matrix.
8. Reclassify weak-name matches and unmatched physical signals as sideband. Assign matching direction/prefix sidebands to declared user groups.
9. Recompute cost, prune groups again, emit best proposal plus alternatives per retained group.

### 2.2 Details missed by prose overview

Code is characterization source; comments are not specification:

- Name features include **1-, 2-, and 3-character** tokens, not only bigrams/trigrams.
- Digit splitting is asymmetric. Direct helper check: `a1b2` → `['a', '1b', '2']`; repeated underscores retain empty words. Dots/brackets are not hierarchy delimiters.
- Cost weights: name **2**, width **1**, direction **4**. Only name component is normalized by number of assignment items; width/direction penalties remain cumulative.
- Exact pair scorer gives no width penalty if either width is unknown, despite contradictory comment. Coarse count scorer treats unknown widths differently.
- Global name score uses Jaccard distance scaled by interface size; local name score uses fraction of missing bus-name tokens.
- Sideband threshold is missing-token count **greater than median + 1**, not merely greater than median.
- Assignment objective contains pair costs only. Missing-required penalties and sideband effects enter afterward. “Optimal mapping” therefore means optimal pair-cost assignment, not optimum of final reported cost or whole-component partition.
- Local shortlist can surface narrower protocols sharing one prefix; it does **not** jointly extract multiple disjoint buses from that prefix.
- Pruning can retain tied ancestor/descendant candidates; it is not global non-overlap optimization. Minimum winning-leaf threshold relaxes when no node qualifies.

### 2.3 Risks and known gaps

Characterize before changing; do not preserve bugs as permanent API:

- Empty inputs/catalogs/groups expose unchecked indexing, empty reductions, division by zero, progress totals of zero. Vector-only groups need coverage too.
- Set iteration and filesystem order can affect tie resolution/output order. Python tuple-value equality does not translate to JS array/object identity.
- `inout` and unknown directions lack proper model. Bus parser treats every non-`in` direction as output.
- Numeric zero/non-finite values, symbolic expressions, explicit wire objects, duplicate normalized names need validation.
- `illegal` bus ports are discarded; variants with no required ports are omitted.
- Bundle writer replaces existing bundle definitions; repeated execution risks stale refs/name collisions. Inference writer maintains `pg_cnt`; repeated-run semantics need tests.
- Progress output can contaminate stdout JSON. Ref names need JSON Pointer escaping.
- `test_label_vector` constructs changed-width input but accidentally tests different list. Several mapping assertions use subset checks, allowing under-mapping to pass.
- Fixture helper `make_testcase_mapping.py` is broken (`bus_defs` undefined; `.items()` on filter). Not authoritative golden generator.
- SciPy appears in requirements but no Python source imports it. NumPy mainly supplies arrays/counting/sign/median; CVXOPT/GLPK only serves assignment fallback.
- Packaging still installs Python via npm, including removed `distutils` API. Root package and `LICENSE` say Apache-2.0; `setup.py` and nested JS draft say MIT. Resolve metadata; do not silently relicense.

Existing untracked JS files are sketches, not runnable port: required `busdef.js`, `_bundle.js`, `_optimize.js`, `util.js`, and JS test file do not exist. Utility sketch also assumes Python-like exception behavior: `Math.abs('WIDTH')` and `Math.sign('WIDTH')` yield `NaN`, not exception. Preserve sketches untouched during planning; supersede deliberately during implementation.

### 2.4 Current DUH ecosystem changes

Sibling checkouts are evidence of integration target, not proof of published npm versions:

- `../duh-bus` 1.0.0 exposes generated CommonJS catalog index; CLI is `duh-bus`, not legacy `duh-bus-which`.
- All **27** abstraction specs inspected use modern roles: **444 `onInitiator` + 444 `onTarget`, zero `onMaster`/`onSlave`**. Legacy loader yields no variants from those specs.
- `../duh-schema` accepts both role naming generations; components support signed shorthand, explicit wire objects, expanded port arrays, symbolic widths, `inout`.
- `../duh-core/lib/expand-ports.js` already defines shorthand normalization. Reuse semantics; avoid dragging Node/ref-resolution dependencies into browser core.
- Neighbor packages target Node >=22 and CommonJS. **Decision:** follow ecosystem CommonJS source + generated browser ESM entry, or move to ESM source with deliberate CJS compatibility. Never hand-maintain two inference implementations.

## 3. Library and model research

### 3.1 Deterministic assignment

| Option | Evidence / tradeoff | Recommendation |
| --- | --- | --- |
| Rectangular Hungarian algorithm | Same fixed-pair assignment problem as Python LP; polynomial, commonly O(n³) for square matrix; pure JS feasible | Default solver family; support both matrix orientations and deterministic ties |
| `munkres-js` 1.2.2 | Browser/Node implementation; upstream describes O(n³); latest npm release from 2017 | Small auditable candidate/reference, not blindly selected because available; verify rectangular padding, float costs, ties, license notices |
| `highs` 1.15.3 | MIT; HiGHS compiled to WASM; Node/browser LP/MIP/QP; single-threaded build, worker recommended | Optional future global-selection solver or independent test oracle; unnecessary default weight for basic assignment |
| `glpk.js` 5.0.0 | Browser/Node WASM LP/MILP; GPL-3.0 npm metadata | Not default; avoid new distribution/license burden merely to mirror old dependency |

Solver spike: compare audited package against small isolated rectangular implementation; test with brute-force oracle before selection. Measure allocation, not only solve time. Worst-case dense matrix remains O(mn) memory; candidate pruning still matters.

Do not casually add dummy assignments during parity port: changing cardinality or adding required-port penalties changes objective. Introduce partial matching explicitly in improved scoring profile.

### 3.2 Jev-like decision models: browser reality

Here “decision model” means learned typed Choice/Score/yes-no model, not business rules engine. These models score candidates; they do not enforce one-to-one assignment or infer electrical correctness.

| Candidate | What was verified from upstream docs/source | Fit for this project |
| --- | --- | --- |
| **LayaForWeb** | Actual browser port of Laya; ModernBERT-large + typed head, 421M parameters; ONNX Runtime Web. q8e8 ~440 MB, q4e8 ~290 MB. WASM reference; WebGPU experimental and q4e8-only in inspected port. Code exports `Laya.systemOne` | Selected model family for P4 browser-local spike; substantial download/RAM/latency |
| **Laya typed-decisions** | Same 421M architecture; context 1024 vs base 512; web converter supports both. Fine-tuned on four synthetic business workflows, not hardware. Model card explicitly warns about calibration and inherited temperatures | Compare with base, do not assume “typed” means better RTL mapping |
| **Von** | 395M ModernBERT; Apache-2.0; Python inference/server with CPU/OpenVINO, CUDA, ROCm, MPS. TS SDK speaks System One protocol. README reports ~3 GB first-use weight download | Research reference only; no verified browser-local runtime in inspected docs; export work out of scope |
| **Kev** | Apache-2.0 project; Qwen-based decision heads, including 0.8B model. Documented CUDA/ROCm/MLX serving and HF Space | Research reference only; browser UI for hosted Space is not browser inference |
| **AnyJev** | Apache-2.0 framework turning LLM logits/hidden states into typed decisions; Python/Transformers/vLLM backends. Option rotation/calibration and per-question linear heads | Evaluation-method reference; no planned provider integration |
| **TypeSafe Jev** | Official System One HTTP API with Choice/Score/Noul. Hosted endpoint/auth; no browser-local weights/runtime established by reviewed docs | Excluded from implementation/benchmark scope by local-inference requirement |
| **Small task-specific ranker** | Linear/logistic model or compact tree over lexical, width, direction, coverage features can execute in ordinary JS | Strong lightweight learned baseline; needs labeled hardware corpus, but no hundreds-of-MB runtime |

LayaForWeb reports roughly 2–5 seconds for three questions on two-core CPU. This is not a target-device result and not evidence that scoring every physical/logical pair is viable. Its “single forward pass” batches questions; inspected code builds separate sequence per question, repeating state. Do not assume constant cost as questions increase.

Its sequence builder truncates state/options to token budgets. Large interfaces must be summarized/chunked with explicit truncation diagnostics, not silently lose required evidence.

**Confidence is not interchangeable:** Laya Choice confidence uses normalized entropy; TypeSafe Choice docs use normalized peak probability. Von documents configurable Noul band remapping. Keep raw probabilities, provider-specific confidence definition, calibration version, and decision policy separate. Low entropy is not proof of correct hardware mapping.

### 3.3 Runtime/support choices

- Core: ordinary JS, JSDoc types, dense numeric typed arrays where profiling supports them. JSON5 adapter via `json5`; validation via `ajv`/DUH schemas at boundaries.
- **P0 dependency gate:** prove browser compatibility for every transitive third-party runtime dependency, including parsers, schema validators, catalog loaders and ref handling. Browser bundle/import smoke test belongs in P0 even though complete browser workflow ships P1. No Node polyfill escape hatch.
- Thin CLI wrapper may use Node built-ins for files/process streams/arguments; shared implementation receives objects/text/bytes. Node-only dev tools/reference tooling are not shipped runtime libraries. Prefer `node:util.parseArgs` in wrapper over additional CLI dependency. Browser validators may need standalone precompilation for strict CSP.
- Ref handling: local JSON Pointer support plus injectable resolver. Evaluate existing ecosystem resolver instead of assuming Python `JsonRef` API exists in JS `jsonref`.
- Tests: existing ecosystem Mocha/c8/ESLint or Node test runner; **Decision:** choose one primary runner. Add `fast-check` for properties, Playwright for browser workers.
- Optional models: ONNX Runtime Web for Laya/custom exported rankers; Transformers.js for supported encoder baselines. Runtime availability does not guarantee arbitrary custom model/head support.
- No TensorFlow/PyTorch/native numerical dependency in shipped inference package. Offline training/export can remain Python tooling if approved.
- Pin selected package versions and model revisions when implemented; npm `latest` metadata is research snapshot, not lockfile.

## 4. Hierarchical architecture

```text
DUH JSON5 (P0) / Verilog portlists, VCD, Verilator JSON (P3)
  └─ A. Validation + normalization + provenance
      └─ B. Name analysis + hierarchy/instance/index extraction
          └─ C. Candidate bundles and groups
              ├─ D. Catalog variants + cached features
              └─ E. Cheap retrieval / shortlist
                  └─ F. Pair scoring + constrained assignment
                      └─ G. Sidebands + proposal conflict handling
                          ├─ H. Optional learned reranking / abstention
                          └─ I. Results + explanations
                              ├─ DUH serializer / CLI
                              ├─ Browser worker / review UI
                              └─ Bundle pattern / regex export
```

ML hook placement is experimental: group-family retrieval, pair rescoring, or final-proposal reranking. Start with final reranking; select one winning intervention rather than applying model everywhere. Pair rescoring, if adopted, must precede assignment.

### 4.1 A: Signal-first data contract

Use stable IDs; never use JS tuple/object identity for value-based matching.

```js
{
  id: "signal-17",
  name: "soc.cpu[2].axi_awaddr",
  scope: ["soc", "cpu[2]"],
  kind: "port", // port | net | variable | unknown
  width: { kind: "known", value: 40 }, // or symbolic/expression, or unknown
  direction: "in", // in | out | inout | unknown
  directionScope: "soc.cpu[2]",
  source: { adapter: "duh", pointer: "/component/model/ports/..." }
}
```

- Original name and metadata remain lossless; normalized tokens are derived features.
- Symbolic width is not zero, `NaN`, or guessed integer. Preserve expression without `eval`; parameter elaboration belongs to explicit trusted adapter.
- Internal nets often lack meaningful port direction. Unknown is missing evidence, not output or mismatch. Scope defines direction viewpoint; optional connectivity can add endpoint evidence later.
- Width, member count, packed bit vector, unpacked array, repeated interface instance are distinct concepts.
- Equal names in different scopes remain distinct; token-normalization collisions retain all IDs with diagnostic.
- Preserve user annotations and existing assignments as constraints.

### 4.2 B–C: Names, hierarchy, bundles

Two versioned name-analysis profiles:

1. `legacy`: reproduce Python tokenization and vector rules for differential tests.
2. `signal`: hierarchy-aware tokenization; configurable separators; camel/acronym boundaries; bidirectional digit boundaries; index spelling and active-low suffix preservation.

Use explicit scope when supplied. Otherwise inferred hierarchy is tentative: dot, slash, brackets can be literal characters in escaped HDL identifiers. Do not destructively split raw names.

Represent literal leaves, records, indexed collections, repeated instance records, and unresolved groups. Require compatible shape/suffix/metadata before folding indexed siblings. Sparse indices stay explicit, not silently made contiguous.

Candidate generators: prefix-tree baseline; explicit hierarchy; suffix/instance-template patterns later. All return provenance and member IDs. Share cached token/ngram features; bound candidate count/depth/group size. Replace hardcoded root-size workaround only after benchmarks.

### 4.3 D–E: Catalog and retrieval

- Compile bus documents into immutable, identified role variants; accept legacy and modern role names. Normalize master→initiator and slave→target for new output; preserve existing input interfaces without rewriting their spelling. Record modernization in CLI migration notes.
- If both aliases present, validate equivalence or report conflict; no silent precedence.
- Preserve required, optional, illegal, user-group, width-expression and semantic tags (`isClock`, `isReset`, `isAddress`, `isData`). Explicit policy for variants with no required ports.
- Browser consumes JSON-safe compiled catalog; Node can discover files or use package index. Catalog compilation validates once and caches features.
- Legacy retrieval preserves top-5 global/top-4 local behavior. Improved retrieval measures recall@K, handles missing metadata, and allows configurable candidate budgets.
- Candidate recall is release metric: perfect reranker cannot recover discarded correct bus.

### 4.4 F–G: Scoring, assignment, selection

Separate cost construction, assignment solver, sideband classification, group selection.

**Legacy scoring profile:** reproduce observed weights/objective/postprocessing; compare optimal cost before demanding same tie mapping.

**Improved profile:** explicit objective with optional unmatched slots, missing-required penalties, forbidden illegal mappings, configurable known-direction constraints, width compatibility and lexical features. Unknown metadata must neither forbid pair nor manufacture positive evidence. Version objective and parameters.

Every solver result checked for unique physical/logical membership and admissibility. Strong direction conflicts can remain visible as rejected diagnostic candidates rather than silently emitted valid mapping.

After classification, report mapped, user-group, sideband, unmatched, missing-required sets separately. No signal disappears.

Separate **candidate alternatives** from **selected proposals**. Alternatives may overlap; selected output cannot silently double-assign exclusive signals. Shared clocks/resets require explicit sharing policy. Initial conflict policy: deterministic selection with reported conflicts or abstention; do not claim global optimality. Later compare tree dynamic programming for nested groups and HiGHS set-packing/MIP for arbitrary overlaps or multi-bus decomposition.

### 4.5 H: Optional learned decision provider

Provider-neutral async contract: bounded structured state + typed questions → distributions + provider/model/revision + truncation/latency/calibration metadata.

Initial task: rerank small set of complete candidate mappings using names, widths, directions, required-port coverage, bus descriptions and deterministic evidence. Include “none/insufficient evidence” option. Model may rank or abstain, never invent signal IDs, protocol ports, numeric widths, or override hard constraints.

Possible later task: resolve abbreviation pairs such as `blk_aln_ctrl` versus `BLOCKALIGNCTRL`. Do not ask model to guess missing metadata as fact.

Implement in **P4**, initially in **shadow mode**: save both deterministic and learned recommendations; no output change. Timeouts, unavailable GPU, failed download, malformed results → deterministic fallback plus diagnostic. Model download explicit and optional, with local asset provisioning supported. Hardware data never transmitted; no remote inference fallback.

### 4.6 I: API, adapters, packaging

Proposed API boundaries, not final signatures:

- `compileCatalog(documents, options)`
- `analyzeNames(signals, options)` / `bundleSignals(signals, options)`
- `inferInterfaces(signals, catalog, options)` → proposals, alternatives, unassigned, diagnostics
- `foldBundlePatterns(bundle, options)` → exact pattern descriptions
- DUH adapter reads normalized input and applies approved proposals to original document.

Expose cancellation/progress at async orchestration boundary. Browser runs expensive work in Web Worker; terminate/recreate worker when synchronous solver cannot cancel cooperatively. Keep stable IDs/provenance across messages; avoid unbounded copies.

Retain `duh-portinf` and `duh-portbundler` binaries, `-b`, `-o`, `--debug`, positional component input. stdout = output only; diagnostics/progress = stderr. Default catalog resolution uses package data, not shell command.

Separate generic inference result from DUH rendering. Preserve unrelated document fields, existing definitions and refs. Compatible rendering covers `busInterfaces`, `busInterfaceAlts`, `busDefinitions`, `busMappedPortGroups`, `pg_cnt`, user groups and `__UMAP__`. New proposals use modern roles. JSON whitespace need not be byte-identical.

**Modern debug format:** versioned JSON object with `formatVersion`, catalog/algorithm/config metadata, groups, candidate IDs, cost breakdowns, selected/alternate mappings, missing-required and unmapped sets, conflicts, provenance and diagnostics. Keep timings separate from stable result fields for snapshots. `--debug` emits this report instead of normal DUH output, preserving CLI switch but not historical positional-array shape. Debug schema must remain useful without ML and add optional model metadata in P4.

Use single root package. Browser entry excludes Node imports and optional model weights; Node entry supports ecosystem integration. Preserve Apache license/notices pending metadata audit.

### 4.7 P3 input adapters

All adapters run on caller-provided local text/bytes/objects in Node and desktop browser. Use browser-compatible JS/WASM parser if needed; never invoke Verilog/Verilator tools at inference runtime.

| Source | Extract / preserve | Boundary |
| --- | --- | --- |
| Verilog portlist | Original identifiers, direction, packed dimensions, unpacked dimensions and source locations where available | Extract through Verilator `--json-only` AST adapter, then select requested module/top ports. Caller runs preprocessing/elaboration externally; generic structured-list input also supported. Do not add raw HDL regex parser or browser compiler dependency |
| VCD | `$scope` hierarchy, `$var` name/type/width/range, identifier code, aliases | Stream declaration section through `$enddefinitions`; ignore value changes initially. VCD variable kind is not port direction. Multiple scoped aliases can share identifier code: preserve alias relation without dropping names |
| Verilator JSON | Module/top/scope identity, original versus generated names, port direction, dtype references/dimensions and variable kinds where present | Confirmed producer: `verilator --json-only`. Consume `.tree.json` plus optional `.tree.meta.json` and producer manifest. Pin version/flags; distinguish hierarchical and transformed AST variants. Unsupported schema → explicit diagnostic, not guessed fields |

Adapter result uses shared lossless contract; supplied scope beats inferred hierarchy. Equivalent inventories across DUH/Verilog/VCD/Verilator should produce equivalent grouping after accounting for metadata differences. Large VCD source streams must not force entire waveform into RAM. Browser file selection never uploads files.

#### Verilator producer/schema investigation

Local probe executed successfully with **Verilator 5.051 devel rev `v5.050-308-gc917f04c6`**. Independently written SystemVerilog fixture under temporary directory covered parameterized packed width, scalar ready/valid, inout, unpacked array and internal variable. No corpus RTL modified or compiled. Reproduction command shape:

```sh
verilator --json-only --no-json-edit-nums --top-module probe \
  --Mdir /tmp/duhportinf-verilator-pkoglJ/obj \
  /tmp/duhportinf-verilator-pkoglJ/probe.sv
```

Observed files: `Vprobe.tree.json`, `Vprobe.tree.meta.json`. These are elaborated AST and shared metadata, not build-system `--make json` output. `--no-json-edit-nums` improves diff stability; `--json-only-output` / `--json-only-meta-output` can select paths. Generation is optional external preparation/reference tooling, never required at inference runtime.

Importer design informed by probe and installed upstream docs/tests:

- Root `NETLIST.modulesp` contains module declarations; `VAR` declarations have `dtypep` references to type nodes identified by `addr`. Traverse structural child arrays, then resolve links with indexed lookup, bounds and cycle guards. Do not count every `VARREF` as signal declaration.
- Top-level ports in probe have `isPrimaryIO: true`; `direction` is `INPUT`, `OUTPUT` or `INOUT`. Internal variable and parameter have `NONE`. Inout `pads` had `varType: "WIRE"`, **not** `"PORT"`; never select all ports solely by `varType`. For non-top module ports, use module context and validated direction/port evidence; exclude parameters explicitly.
- Preserve `name`, `origName`, `verilogName` distinctly. `loc` encodes source-file ID and span; optional metadata `files` resolves file IDs. Missing metadata loses path resolution, not signal identity. Never fetch source paths embedded in metadata automatically.
- Resolve numeric packed width through dtype nodes, not `dtypeName`. Probe `WIDTH=12` resolves to `BASICDTYPE.range: "11:0"`; scalar logic has no range. `UNPACKARRAYDTYPE.declRange: "[0:2]"` with `refDTypep` pointing to `logic[7:0]` is three 8-bit elements, not one 24-bit scalar wire. Preserve dimension bounds/order; inspect additional dtype forms before claiming struct/interface support.
- Module definitions are not instance scopes. Instantiate module/cell paths when exposing internal signals; keep repeated instance IDs distinct and guard recursive references. Probe plus upstream primary-I/O fixture establish initial shapes, not complete netlist coverage.
- Short `addr` links are AST-local references, not public stable IDs. Metadata `pointers` contains process addresses; ignore for semantic identity and golden output. Preserve source evidence but normalize machine-specific paths only in approved snapshots.
- Upstream internals docs show `ioDirection` in example, while tested executable and regression fixture emit `direction`. Docs also say false boolean fields are omitted. Version adapter against **observed fixtures**, not prose example alone; known absent flags default false only in supported schema.
- Probe files do not include producer version. Store sidecar manifest with `verilator --version`, command/flags, top, source/config hashes and schema profile; accept bare AST with explicit profile detection/diagnostic, not guessed version guarantee. Support newer compatible shapes by tested feature detection, reject unsupported relevant node forms without discarding signals silently.

P3 fixtures should add repeated child instances, ascending/negative ranges, multidimensional arrays, escaped names, parameter-specialized modules, interfaces and typedefs. Build only supported subset first; unknown widths/types stay explicit or cause scoped unsupported-format diagnostics. `--json-only` disables some aggressive transforms but still elaborates; do not promise every original source signal or symbolic expression survives unchanged.

## 5. Hierarchical regex mapping and bundle folding

### 5.1 Multi-socket AXI4 capture contract

User example, retained verbatim:

```js
/^core_local_port_0_axi4_(?<g1>\d)_(?<g0>(ar|r|aw|w|b))_((?<valid>valid)|(?<ready>ready)|)/
```

Confirmed interpretation: fixed root `core_local_port_0_axi4` → socket `g1` → channel `g0` → specially tagged handshake signal or remaining payload path. One expression describes many interface instances/channels, not one flat bus assignment.

- Capture schema explicitly declares grouping order `["g1", "g0"]`; do not rely on capture-number order or lexicographic sorting.
- Named `valid`/`ready` captures create explicit **handshake tags per `(root, socket, channel)`**, not ordinary payload fields or one handshake pair for entire AXI4 interface. Retain original names and signal IDs; protocol mapping validates role/direction/width separately.
- Original expression is **prefix matcher**, not exact finite member regex: `\d` permits one digit; empty alternative admits remaining payload; no `$` allows trailing text. Preserve unmatched suffix plus consumed length for downstream field-path analysis. Do not silently “fix” semantics by anchoring it.
- Confirmed payload behavior: empty role branch leaves `bits_addr`, `bits_id`, etc. as residual field path for recursive grouping. Reject or flag partial role matches such as `valid_extra` unless requested by rule policy.
- Socket capture must not collapse repeated AXI4 interfaces into scalar bit vector. Sparse socket/channel combinations remain sparse.

Example grouping (synthetic fixture based on supplied pattern):

```text
core_local_port_0_axi4_2_ar_valid     → socket 2 / ar / valid
core_local_port_0_axi4_2_ar_ready     → socket 2 / ar / ready
core_local_port_0_axi4_2_ar_bits_addr → socket 2 / ar / payload bits_addr
core_local_port_0_axi4_5_r_valid      → socket 5 / r / valid
```

Represent pattern source/flags, match mode (`prefix` or `full`), ordered group captures, role captures, residual-field policy, observed domains and resolved member IDs in pattern IR. Compiler factors repeated validated mappings into one capture-aware pattern; application to current inventory produces explicit per-socket/channel mappings. Pattern itself never implies unobserved signals exist.

**P2 deliverable:** infer/export this class of hierarchical patterns and apply constrained capture rules; retain exact membership snapshots for DUH interoperability and regression tests. Arbitrary generalized pattern learning is not prerequisite.

#### Per-channel handshake representation

Each channel has semantic role bindings separate from payload hierarchy, e.g.:

```js
{
  groupPath: ["core_local_port_0_axi4", "2", "ar"],
  handshake: {
    kind: "ready-valid",
    valid: "signal-valid-id",
    ready: "signal-ready-id",
    bindingStatus: "complete"
  },
  payload: { bits: { addr: "signal-addr-id" } }
}
```

Tags belong to mapping memberships, reference immutable signal IDs, and retain evidence (`capture-rule`, catalog match, or later model proposal). They survive regex export/reapplication, debug serialization and browser display. Tag only successful named capture matches, not arbitrary substring occurrences; handshake tags do not depend on display-name spelling after mapping.

- Materialize role lists before uniqueness checks; duplicate candidates produce conflict diagnostic, never last-write-wins. Missing role remains null with incomplete status, not invented signal. `bindingStatus: complete` means bindings present/unique, not functional protocol validation.
- AXI4 known ready/valid widths must be one bit; opposite directions expected relative to same endpoint. Unknown VCD direction/width evidence remains unknown and does not erase semantic tags. Conflicting known metadata marks invalid/unvalidated proposal.
- Initiator endpoint: AR/AW/W VALID out, READY in; R/B VALID in, READY out. Target reverses. Evaluate per channel; never assume all VALID signals share direction across AXI4.
- Payload includes remaining fields, not handshake leaves. Each socket/channel tracks its own bindings; never pair channel AR VALID with channel AW READY or another socket's READY.
- Capture grouping does not identify clock/reset or prove transfer timing. Future waveform analysis may consume tags; no transaction decoding or behavioral checking in P2.

### 5.2 Exact membership mode

Canonical output remains explicit member IDs plus typed pattern structure. Regex is compiled view, not only stored representation.

Example observed names: `lane0_data`, `lane1_data`, `lane3_data`.

```json
{
  "kind": "indexed",
  "prefix": "lane",
  "suffix": "_data",
  "indices": [0, 1, 3],
  "indexSpellings": ["0", "1", "3"],
  "regex": "^lane(?<index>0|1|3)_data$"
}
```

In **exact** mode, do not emit `lane\\d+_data`: language includes unseen members. In **template/prefix** mode, open index domains are allowed but actual membership comes only from supplied inventory. `lane00` and `lane0` need separate original spellings even when numeric index equal.

### 5.3 Algorithm and constraints

1. Build trie over raw-name segments; factor shared literal prefix/suffix and identical subtrees.
2. Detect index/field alternatives while retaining correlations. Observing only `a0_x` and `a1_y` must not generate cross-product `a0_y`/`a1_x`.
3. Exact compiler generates anchored escaped-literal alternatives; template compiler preserves declared open domains/prefix behavior. Compact character classes only when language-preserving. Multi-digit numeric ranges need range compiler or explicit alternatives, not naïve `[0-15]`.
4. Add named captures and explicit hierarchy/role schema for reconstruction. Keep width/direction/protocol constraints outside regex. Export each named group once where possible for cross-browser syntax portability.
5. Verify exact expansion returns exact members; template application returns correct group/role/residual captures for every matched member. Detect rule overlap, duplicate logical leaves, missing channels and near-miss role names. Preserve literal fallback if compression is larger or ambiguous.

Generated subset excludes backreferences, arbitrary lookarounds and nested unbounded quantifiers. Enforce pattern size/input length/work budgets; worker isolation for expensive operations. Support imported capture rules through same validated subset; unrestricted arbitrary regex execution is not automatic.

### 5.4 Generalizing reusable naming rules

Template mode may use open socket indices as in supplied AXI4 example. Record scope, ordered captures, observed domains, excluded names, metadata predicates and validation results. On new inventory, show added matches and unresolved/ambiguous leaves for review. Regex matches name structure, not protocol semantics or correctness. Inference of unrestricted naming grammars remains deferred.

## 6. Verification and evaluation

### 6.1 Reference capture and differential tests

- Freeze Python source and fixture catalog versions. Build isolated reference environment with recorded Python/NumPy/CVXOPT/GLPK/JSON5/jsonref versions; avoid global installation.
- Current attempted command: `python3 -m unittest duhportinf.test.test`, Python 3.13.15. **Blocked at import: `ModuleNotFoundError: No module named 'json5'`.** No claim that legacy tests pass; no dependencies installed during planning.
- Extract golden intermediate artifacts: tokens, trees, candidate groups, coarse scores, cost matrices, assignments, sidebands, selected groups, DUH documents.
- Canonicalize IDs/order only where incidental. Tied optimums: compare objective/constraints and explicitly characterize downstream sideband/ranking differences.
- Maintain discrepancy ledger: intended behavior preserved, legacy bug fixed, improved-profile change. Do not tune JS merely to reproduce accidental Python ordering.

### 6.2 Unit, property, and integration tests

Unit coverage: names/acronyms/digits/escaped identifiers; sparse and mixed-width vectors; role aliases; illegal/optional ports; unknown metadata; cost components; rectangular and empty assignment; tied scores; sideband thresholds; ref escaping and serialization.

Properties:

- Brute-force optimum equals solver result for small random rectangular matrices.
- Every input signal remains accounted for; selected exclusive mappings are unique.
- Input permutation does not change canonical deterministic result. Scope-preserving renaming behaves as specified per tokenizer profile.
- Bundle expansion returns exact original IDs; exact regex patterns accept precisely represented names, with adversarial negative tests.
- Hierarchical capture rules map socket/channel/role correctly, preserve residual payload suffix and sparse combinations, report overlaps and partial-role matches. Test supplied one-digit AXI4 rule, multi-digit variants, missing channels, active-low names and several sockets without coalescing interfaces.
- Ready/valid tags survive export/reapplication and serialization; incomplete/duplicate pairs remain explicit. Test opposite R/B versus AR/AW/W directions, non-1-bit known widths, unknown VCD directions and prohibition of cross-channel/socket pairing.
- Verilator fixtures include `WIRE` inout ports, omitted false flags, dtype links, packed versus unpacked dimensions, parameter/internal-variable exclusion, repeated instances and schema-field changes. Do not infer stable identity from AST addresses or decode scalar width from `dtypeName`.
- Neither cost nor confidence contains `NaN`/infinity; malformed data fails explicitly.
- DUH adapter preserves unrelated fields, existing assignments, and valid refs. No-op repeated execution does not duplicate mappings or destroy definitions.

Integration fixtures: signed/symbolic/explicit/expanded ports; nested/vector/user-group maps; existing alternatives; empty component/catalog; repeated runs; output files and stdout; CLI error codes; both old fixture specs and current modern-role catalog. Validate rendered documents against pinned DUH schema, including uniqueness constraints.

Browser: desktop Chromium/Firefox/WebKit deterministic core and workers; no Node polyfills or runtime Python. P0 bundle/import smoke gate checks dependency portability; P1 tests complete workflow. Test offline-after-assets, worker cancellation, blocked network, bounded-memory large inputs. Optional models tested separately on actual supported WASM/WebGPU backends, including CPU fallback, cache eviction, failed downloads, missing cross-origin isolation and quantization drift.

Security: no remote `$ref` fetch by default; opt-in resolver restricted to allowed origins/paths with cycle/depth/size budgets. Test prototype-like keys (`__proto__`, `constructor`), malicious names/regex literals, excessively deep bundles and huge dimensions. Display names as text, never HTML. No inference endpoint, telemetry containing design data, or remote fallback; local processing must work with network blocked after assets provisioned.

### 6.3 Corpus and quality metrics

User-specified corpus roots, all found locally; initial inventory/sample inspection completed:

| Root | Observed material / intended coverage |
| --- | --- |
| `../block-ark/` | `ark.json5`, `ark.full.json5`, `docs/*.json5`; explicit AXI4/AXI4-Lite naming and signed directions |
| `../block-cadence-ddr3/` | `ddr.json5`, `ddr-busprop.json`, Verilog/preprocessed RTL; DFI indexed names and controller ports |
| `../block-nvdla/` | `nvdla.json5`, small/large DUH files, prior bus proposals, RTL; repeated memory interfaces and duplicated channel tokens (`..._aw_awvalid`) |
| `../block-zipline-microsoft-extra/` | DUH source, `.portinf.json5`, `.portbundler.json5`, preprocessed Verilog; historical inferred outputs and diverse naming |
| `../block-100g_mac-opensilicon/` | RTL/verification sources and DUH/register documents; select actual top-level port inventory rather than treating register maps as ports |

Current shallow sample review is not gold-label validation. Initial corpus search found no VCD or filename-marked Verilator/tree JSON samples. Subsequent synthetic `verilator --json-only` probe succeeded on installed 5.051 devel (§4.7); real-design JSON/VCD fixtures and supported producer-version matrix remain P3 work.

Keep corpus manifest with source path/revision/hash, module/top, extraction method, expected format and label provenance (`manual`, `reviewed`, `legacy-inferred`, `unlabeled`). Existing `.portinf`/busprop outputs are **legacy regression evidence, not trusted ground truth**. Review mappings independently; strip existing assignments only in isolated inference-test copies, retain originals for preservation tests.

Use local path-configurable integration suite for full designs. Check redistribution/license permissions before committing excerpts; publish only approved minimal fixtures or independently generated equivalents. Do not copy RTL wholesale or upload corpus to model services.

Combine these designs with AXI/DPRAM unit fixtures and generated perturbations. Cover APB/AHB, TileLink, Wishbone, memories, ready/valid, unknown/custom protocols, shared prefixes, repeated instances and sidebands where available or synthetically explicit. Synthetic renaming alone is not external validation.

Split by IP/design family and naming-template lineage, not random individual ports. Hold out entire protocol families for unknown-protocol tests. Training, threshold calibration and final evaluation are disjoint. User corrections become labels only with provenance/consent.

Report separately:

- Grouping precision/recall and exact group recovery.
- Catalog retrieval recall@K; bus-family/role top-1 and top-K.
- Logical mapping precision/recall and exact interface accuracy.
- Required-port coverage, sideband quality, illegal-direction violations, duplicate assignment rate.
- False positive rate on unrelated signals; abstention coverage versus accepted-error risk.
- Per-family/per-naming-style results, not only pooled score.

P4 local-only ML comparisons: deterministic baseline; tuned lexical/alias baseline; small learned ranker; Laya base and typed checkpoint. No hosted or server-provider integration in current scope. Report Brier/ECE or reliability plots, option-order sensitivity, context truncation, quantized-vs-reference drift, and paired uncertainty intervals. Never transfer business-ticket benchmark accuracy or confidence thresholds to RTL.

### 6.4 Performance and release gates

Benchmark 10, 100, 1k, 10k signals; stress larger waveform inventories later. Vary catalog size, longest name, biggest ambiguous group, vector density and no-prefix worst case. Record stage timings, candidate/solve counts, dense matrix sizes, peak memory, worker transfer, browser download size, cold/warm model initialization and p50/p95 inference.

Provisional gates; numeric budgets require target hardware decision:

- All selected outputs satisfy structural invariants; every compatibility difference reviewed.
- P0 CLI installs without Python/native solver; every third-party runtime dependency clears browser compatibility gate. P1 complete deterministic workflow runs entirely locally in desktop browser.
- Existing DUH integration tests pass for agreed output profile.
- No silent truncation, data loss, contradictory alias roles, or duplicate exclusive assignments.
- ML ships only if held-out improvement justifies download/RAM/latency at agreed accepted-error rate. “No useful gain” is valid spike result.
- Record budgets before optimization; do not promise sub-15ms browser inference from server headline.

## 7. Implementation phases and dependencies

### P0 — Complete drop-in CLI replacement using browser-ready libraries

Substeps within P0, not separate release phases:

1. Freeze reference behavior and catalog; reproduce Python in isolated dev environment; correct fixture coverage and record discrepancy ledger. Start local integration corpus from five supplied roots. Python environment failure prevents full parity claim, not portable-helper work.
2. Choose package/module/test strategy, audit all transitive runtime dependencies, run assignment solver spike. Browser compile/import smoke test required before dependency adoption.
3. Implement internal portable port/catalog contracts, value-safe IDs, DUH normalization/ref policy, legacy tokenizer/grouping/vector behavior, bundler and catalog role aliases.
4. Implement shortlist, costs, Hungarian assignment, sideband/user groups, proposal conflict reporting, preservation-safe DUH writer and modern versioned debug JSON.
5. Ship both `duh-portinf` and `duh-portbundler`, compatible flags, modern roles for new output, stdout/stderr discipline. Replace npm Python installation; single package/lockfile/license audit; migration guide and tarball smoke tests.

**Exit:** both CLIs work end-to-end without Python/native inference libraries; user corpus regression suite runs; differences reviewed; no signal loss or overwritten existing definitions; all third-party runtime deps demonstrably browser-compatible. No Laya work required. Public generic API and browser UI not required yet.

### P1 — Desktop browser, same local inference implementation

Expose browser entry, local catalog assets, File/Blob import/export, worker orchestration, cancellation/progress and minimal result/debug review. Same costs/solver/normalization as P0; no server or Node polyfills. Desktop Chromium/Firefox/WebKit tests with network blocked after assets provisioned. Package/browser deployment/CSP docs ship here.

**Exit:** representative DUH files produce equivalent CLI/browser results; responsive UI, bounded memory, working cancellation, local export; no design data leaves browser. Full signals API not prerequisite.

### P2 — Hierarchical regex mappings and bundle patterns

Implement capture-aware pattern IR, ordered socket/channel axes, special ready/valid handshake tags, residual payload policy and per-instance mapping materialization. Infer/export one pattern for repeated AXI4 sockets/channels as in §5; support validated input rules. Distinguish prefix/template from exact-member mode, retain sparse membership and explicit mappings, test overlaps/near misses and incomplete/conflicting handshake bindings. Expose browser review/export and CLI debug representation without forcing regex/tags into incompatible DUH schema fields.

**Exit:** supplied AXI4 case represented by one pattern with correct hierarchy, per-channel handshake tags and payload grouping; round-trip explicit membership and metadata preserved; no accidental socket coalescing or cross-channel ready/valid pairing.

### P3 — Better signals/ports API and source adapters

Stabilize public contracts in §4 with separate signal identity, scope, aliases, width/dimensions and direction evidence. Add streaming VCD declaration and versioned `verilator --json-only` AST adapters; expose Verilog portlist as module/top-port projection of AST, plus generic structured-list input. Extend tested synthetic Verilator schema probe to real-design fixtures and relevant type/instance cases. All runtime parsers browser-compatible; external Verilator supplies elaboration, never runtime dependency.

Enable improved tokenizer/indexed-record recovery and metadata-missing policy. Evaluate improved partial-matching objective separately from legacy profile; add non-prefix/multi-bus candidates based on measured corpus failures. Preserve P0 CLI contract through adapters rather than rewrite core.

**Exit:** equivalent inventories from supported sources map consistently despite missing metadata; alias/scope/original-name identity preserved; unknown syntax/schema fails explicitly; huge VCD waveforms need not be read into memory for name inference.

### P4 — Local Laya

First perform bounded desktop-browser feasibility spike: base/typed checkpoints, WASM reference, supported WebGPU quantization, cold download/init, RAM, warm latency, context limits and calibration drift. Compare with deterministic/lexical/small-ranker baselines on held-out hardware corpus.

Implement optional local provider/shadow mode, integrity-checked cached or user-provisioned model assets, calibrated abstention, worker resource limits and deterministic fallback. No remote API, server fallback, Von export or Kev integration. Model manifests/notices and local/offline deployment docs ship with feature.

**Exit:** comparative report including negative results; only promote Laya if quality/resource gates pass. Default CLI/browser workflow remains model-free and usable if Laya rejected.

Packaging, tests, schema/debug docs and release notes are deliverables of every phase. Advanced global-selection MIP and unrestricted naming-grammar learning remain separately scoped after real failure data.

## 8. Main risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Browser model too large/slow | Model-free path mandatory; small ranker baseline; lazy download; worker; explicit budgets |
| Model confidently wrong on abbreviations | Hardware corpus, aliases baseline, domain calibration, abstention, hard constraints |
| Modern DUH catalog incompatible with literal port | Role aliases and schema adapters before solver work |
| “Optimal assignment” mistaken for optimal inference | Separate fixed-pair solver, final scoring and global selection; document guarantees |
| Numeric suffix merges unrelated ports | Typed shape/index IR; metadata checks; lossless provenance; legacy profile isolated |
| Missing direction biases internal signals | Explicit unknown and scope-relative direction; metadata ablations |
| Regex overgeneralizes or consumes excessive CPU | Explicit prefix/template versus exact modes; capture schema, resolved membership, restricted constructs and budgets |
| Compatibility locks in old bugs | Golden characterization plus reviewed discrepancy ledger, not blind byte parity |
| Upstream models/APIs change rapidly | Pin code/model/tokenizer/calibration revisions, manifests and hashes; optional provider boundary |

## 9. Confirmed decisions and remaining questions

### Confirmed

- P0 complete drop-in CLI with browser-compatible third-party runtime libraries; P1 desktop browser; P2 hierarchical regex mapping/folding; P3 better signals/ports API; P4 Laya.
- Debug format may be modernized; plan selects versioned structured report.
- Desktop only, local inference only. No remote model providers in planned implementation.
- Source targets: Verilog portlist, VCD, Verilator JSON produced by `verilator --json-only`.
- Regex expresses hierarchical multi-socket AXI4: `g1` = socket, `g0` = channel, empty role branch = residual payload to group recursively.
- Ready/valid handshake signals receive special tags separately for every socket/channel; not merely ordinary regex leaves.
- Five corpus roots in §6.3 designated by user, verified present locally.

### Remaining defaults / later-phase decisions

Confirmed items above need no further approval loop. Working recommendations below do not silently redefine user requirements:

1. **P0 selection:** preserve legacy CLI proposal insertion for non-conflicting groups; lock existing mappings, report ambiguity/conflicts, keep alternatives visible. Do not silently double-assign signals; shared clock/reset exceptions require explicit policy before enablement.
2. **Package conventions:** proposed default JS + JSDoc, Node >=22, CommonJS source plus browser ESM build, Mocha/c8/ESLint to match neighbors. Browser dependency gate remains mandatory regardless of source module format.
3. **P2 index domains:** preserve user-supplied `\d` rule exactly. Inferred templates may support multi-digit indices when observed; show changed domain explicitly rather than silently widening supplied regex.
4. **P3 inputs:** baseline schema investigated on 5.051 devel. Pin supported Verilator builds and acquire representative real-design JSON/VCD fixtures during phase preparation. Portlist projection from Verilator AST avoids separate raw HDL parsing requirement.
5. **P4 resource budgets:** acceptable optional model download, peak RAM and cold/warm latency on target desktop; decide before Laya implementation, not prerequisite for P0.
6. **Corpus authority/distribution:** stored maps need provenance/review; use local paths until excerpts cleared for redistribution. Legacy-generated outputs remain regression evidence until reviewed.

## 10. Research sources and reproducibility

### Local evidence

- Python modules/tests named in §2; root `package.json`, `requirements.txt`, `setup.py`, `.npm-install/*`, `LICENSE`, `README.md`, `overview.md`.
- Existing JS sketches under `duhportinf/` reviewed but not modified.
- Five user-designated corpus roots in §6.3 inventoried; representative DUH/README samples inspected. Full correctness/license audit and real-design VCD/Verilator sampling pending.
- Verilator 5.051 devel `v5.050-308-gc917f04c6`: local `docs/guide/exe_verilator.rst`, `docs/internals.rst`, `test_regress/t/t_json_only_primary_io.{py,out}` inspected under `/home/drom/work/github/verilator/verilator`. Synthetic probe and generated AST/metadata inspected under `/tmp/duhportinf-verilator-pkoglJ`; temporary research artifacts, not committed fixtures.
- Sibling `../duh-bus/{README.md,package.json,specs/}`, `../duh-schema/lib/{component,abstractionDefinition,busInterface}.js`, `../duh-core/{package.json,lib/expand-ports.js}` inspected. Pin actual dependency releases during P0.

### Primary upstream sources

- [LayaForWeb](https://github.com/vishalmysore/layaForWeb), including `web/laya-core.js`; observed HEAD `6e67de8d8ccaf9474c9150c3f3877878d915020b`.
- [Laya base model card](https://huggingface.co/convaiinnovations/laya), [typed-decisions model card](https://huggingface.co/convaiinnovations/laya-typed-decisions). Pin weights separately from browser-port code.
- [Von](https://github.com/wfzyx/von); observed HEAD `0acaa0683cc08aae5a71bc2f489d47ab6929ae06`.
- [Kev](https://github.com/jaredpalmer/kev); observed HEAD `3a184169b07f50722994584a2b4048a9d28fc8ad`.
- [AnyJev](https://github.com/nokia-applied-research/AnyJev); observed HEAD `10d5db91dda38dbde74c6abc1c075ce6463723d1`.
- [TypeSafe API](https://docs.typesafe.ai/api), [models](https://docs.typesafe.ai/models), [confidence](https://docs.typesafe.ai/confidence).
- [ONNX Runtime Web](https://github.com/microsoft/onnxruntime/tree/main/js/web), [Transformers.js](https://github.com/huggingface/transformers.js).
- [Verilator `--json-only`](https://verilator.org/guide/latest/exe_verilator.html#cmdoption-json-only), [Verilator AST JSON internals](https://verilator.org/guide/latest/internals.html); local docs cross-checked against actual probe output, not assumed stable schema.
- [munkres-js](https://github.com/addaleax/munkres-js), [HiGHS JS](https://github.com/lovasoa/highs-js), [GLPK JS](https://github.com/jvail/glpk.js). HiGHS observed HEAD `741e02dd223fdbe1a20b99abe3a9740562d02ab2`.
- npm registry metadata queried for named solver/runtime packages and `fast-check`; license/version claims checked against that snapshot, final bundled-license audit still required.

No model weights downloaded, model inference benchmark run, or solver replacement implemented during this planning pass. Browser support statements distinguish upstream-documented implementations from unverified export possibilities.
