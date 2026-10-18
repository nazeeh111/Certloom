# Reporting implementation defects

Certloom checks bounded data describing an exact stored binary64 linear system. Dense certificates supply an approximate inverse; sparse certificates supply canonical CSR entries and positive weights. Every proof premise, residual and enclosure is recomputed. Failed contraction or weighted diagonal dominance is a supported `not_certified` outcome, not evidence of singularity or a vulnerability. A certified but wide enclosure may leave a threshold undecidable.

Inputs are limited to 2 MiB of UTF-8 JSON. Dense systems have at most 128 unknowns; sparse systems have at most 4,096 unknowns and 32,768 nonzeros. Duplicate keys, extra fields, noncanonical/nonfinite values, malformed sparse indices, duplicate coordinates, explicit zero sparse entries and nonpositive weights refuse. The arithmetic limits do not guarantee constant running time. Browser computations run in a disposable local worker with Cancel and a 20-second deadline. The standalone Python command has no browser deadline.

The checker does not evaluate input expressions, execute uploaded code, authenticate a producer, certify measurements or validate a physical model. A transient system's right-hand side may contain a previous approximate state; checking it does not certify accumulated simulation error. Downloads include executable checker source that recipients should inspect before running. Hashes identify bytes, not a trusted author.

Report ordinary correctness and reliability defects in [GitHub Issues](https://github.com/nazeeh111/Certloom/issues). Include the version, a minimal nonsensitive certificate, observed result and expected behavior. Do not post secrets, private equations or an unreviewed exploit in a public issue. For a suspected vulnerability, use GitHub's private reporting option if enabled, or first open an issue requesting a private contact without exposing sensitive details.

We assess impact from reproduced behavior. No critical-security claim or audit guarantee is made.
