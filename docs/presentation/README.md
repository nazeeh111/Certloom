# A result that travels without its solver

This is a fresh check of the retained captured FiPy equations using Certloom source `0c7728c9af019b60209a9f7c557a97fbd5b197f7`, not a new diffusion simulation or accuracy study. The current product, package and command are **Certloom**, version `0.2.1.dev0`. No solver, NumPy, API key or computation service is required by either checker.

## Open and verify the actual artifacts

- [CLI-produced six-member proof](transient-proof.zip).
- [Actual browser-produced proof](browser-proof.zip).
- [Four exact case results](results.json), [trusted recomputation](trusted-verification.json) and [fresh recipient/tamper controls](handoff-checks.json).
- [All 400 plotted components and exact-check record](figure-data.json), [wide SVG](proof.svg), [portrait SVG](proof-mobile.svg) and [figure source](render.py).

From this pinned current source, with Python 3.10 or later:

```sh
python3 -m certloom verify examples/fipy-transient400.json
python3 -m certloom bundle examples/fipy-transient400.json --out /tmp/certloom-new-proof.zip
python3 -m certloom verify-bundle /tmp/certloom-new-proof.zip
```

The output must be new. `verify-bundle` compares member names, checksums, the exact bundled checker against this trusted source, the receipt and a fresh mathematical recomputation. It never executes archive code. For a received ZIP, establish a matching trusted installation separately. Older releases have different checker bytes and require their corresponding trusted source; the historical release is not silently substituted for this development version.

For this delivered proof, the extracted `checker.py` was compared byte-for-byte with the trusted current source before being run in a fresh directory:

```sh
python3 -I -S checker.py certificate.json
```

Its full result matched `verification.json`. This succeeded for both the CLI and actual browser downloads. The standard-library-only recipient used Python 3.14; no producer/FiPy/NumPy import was available through `-I -S`. Checksums identify bytes, not authorship or a trusted producer. The generated checker retains its current historical comment bytes because trusted admission compares its entire identity; this presentation does not change checker compatibility.

## What is actually established

The final transient capture contains 400 unknowns and 1,920 nonzeros. An independent Fraction calculation from the stored CSR data recomputed all 400 residuals, positive weighted gaps, radii and exact endpoints. The global minimum gap is exactly:

```text
250199979298361 / 1125899906842624
```

For component 19, the exact threshold is stored binary64 `0x1.f5c28f5c28f5cp-1`, not an assertion about an intended infinitely precise decimal. The guaranteed endpoints, rounded outward at 18 decimal places, are:

```text
lower  0.996898828203779540
upper  0.996898828203785027
```

The lower exact rational endpoint exceeds the stored threshold, so that strict stored-system decision is `above`. These are enclosures of the unique solution to the stored equations. They are not confidence intervals, measured uncertainty, accumulated time-stepping error, discretization error, physical accuracy or authentication of the producing solver. The transient right-hand side includes a prior approximate time state.

The overview plots every stored component index 0–399 on a common numerical axis 0–1.05, with no spatial-distance claim, smoothing, omissions or downsampling. All 400 exact error bounds are included but are subpixel at that scale; their width is not enlarged. The gold dot locates component 19 and does not depict its interval width. Exact fractions in the JSON remain authoritative. The existing Matplotlib 3.11.2 runtime produced the figure; Matplotlib is an optional artwork dependency, not a checker/runtime dependency. Both SVG variants preserve all 400 line vertices and use the same axis limits.

## Proof, decision and refusal are different

The separate **steady-state** controls use that steady system, rather than pretending all cases share the transient matrix:

- Original steady capture: certified, threshold `above`.
- Changed candidate answer: still certified, but threshold `undecidable`. A wide valid enclosure can say little about the proposed answer.
- Unit weights: `not_certified`, because the minimum weighted dominance gap is zero. Failure of this sufficient premise does not establish singularity or a wrong candidate.

A `verify` return code 0 establishes an enclosure, not necessarily a decisive threshold; code 3 means failed proof premise, and code 2 invalid input/file refusal. `bundle` return 0 means an artifact was written and can include a refused proof.

The tamper controls change certificate bytes, change a receipt while recomputing its checksums, and change checker bytes while recomputing its checksums. All refuse with code 2. Export to an existing proof refuses without changing its bytes. Thus the demonstration tests more than checksum equality.

## Actual browser route

The static site was built from this current source and served on task-local HTTP. Its actual Web Worker checked the transient certificate, exported the browser proof above, checked the changed-answer `undecidable` and unit-weight refusal cases, revoked prior results/exports on input editing, and refused invalid JSON. Zero browser errors or external computation requests were observed. [Desktop capture](workbench-desktop.png) · [390px bounds capture](workbench-mobile.png).

On the 390px page, the bounds are a labeled keyboard-focusable local scroll region; ArrowRight advances it without making the entire page wider. A held three-line CSS improvement prevents decimal wrapping and remains separate from this current-main candidate. This presentation does not claim that pending repair has shipped or duplicate its code.

FiPy/NIST source and terms remain in the complete repository and each proof's `LICENSE-FIPY.txt`. See the retained [capture provenance](../../examples/fipy-provenance.json), [source](../../examples/fipy-mesh20x20.py), [NIST terms](../../examples/FIPY-TERMS.txt) and [method](../method.html). Established weighted diagonal-dominance and inverse-contraction theorems are not independently invented mathematics. Existing dense certificates, sparse APIs, expert documentation, MIT copyright and all historical artifacts remain preserved.
