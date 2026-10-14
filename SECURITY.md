# Reporting implementation defects

Certloom accepts bounded data describing a square real linear system. It does not evaluate input expressions, execute uploaded code, authenticate a producer, or certify physical measurements. Browser computations run in a local worker; downloads include executable checker source that recipients should inspect before running.

Report ordinary correctness and reliability defects in [GitHub Issues](https://github.com/nazeeh111/Certloom/issues). Include the version, a minimal nonsensitive certificate, observed result and expected behavior. Do not post secrets, private equations or an unreviewed exploit in a public issue. For a suspected vulnerability, use GitHub's private reporting option if enabled, or first open an issue requesting a private contact without exposing sensitive details.

We will assess impact from reproduced behavior. A failed numerical proof is an ordinary supported outcome; it is not itself a vulnerability. No critical-security claim or audit guarantee is made.
