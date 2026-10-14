// Independent exact checker for the stored binary64 system in a Certloom certificate.
// Matrices use integer coefficients and a common power-of-two scale. No floating
// arithmetic is used for the theorem, its enclosure, or the threshold decision.
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_N = 128;
const ROOT_KEYS = ["format", "A", "R", "b", "x", "decision"];

export class VerificationError extends Error {
  constructor(message) {
    super(message);
    this.name = "VerificationError";
  }
}
function fail(message) {
  throw new VerificationError(message);
}

// JSON.parse alone silently overwrites duplicate keys. This bounded parser uses
// JSON.parse only for individual strings and detects decoded duplicate keys.
function parseDocument(text) {
  if (typeof text !== "string") fail("Certificate must be UTF-8 JSON text.");
  if (
    text.length > MAX_BYTES ||
    new TextEncoder().encode(text).length > MAX_BYTES
  )
    fail("Certificate exceeds the 2 MiB input limit.");
  let pos = 0,
    nodes = 0;
  const ws = () => {
    while (/[ \t\r\n]/.test(text[pos] || "~")) pos++;
  };
  function string() {
    const start = pos++;
    while (pos < text.length) {
      const ch = text[pos++];
      if (ch === '"') {
        try {
          return JSON.parse(text.slice(start, pos));
        } catch {
          fail("Invalid JSON string.");
        }
      }
      if (ch === "\\") pos++;
      else if (ch.charCodeAt(0) < 32) fail("Invalid JSON string.");
    }
    fail("Unterminated JSON string.");
  }
  function value(depth) {
    if (++nodes > 40000 || depth > 8)
      fail("JSON structure exceeds the certificate limits.");
    ws();
    const ch = text[pos];
    if (ch === '"') return string();
    if (ch === "[") {
      pos++;
      ws();
      const result = [];
      if (text[pos] === "]") {
        pos++;
        return result;
      }
      for (;;) {
        result.push(value(depth + 1));
        ws();
        if (text[pos] === "]") {
          pos++;
          return result;
        }
        if (text[pos++] !== ",") fail("Invalid JSON array.");
      }
    }
    if (ch === "{") {
      pos++;
      ws();
      const result = Object.create(null),
        seen = new Set();
      if (text[pos] === "}") {
        pos++;
        return result;
      }
      for (;;) {
        ws();
        if (text[pos] !== '"') fail("Invalid JSON object key.");
        const key = string();
        if (seen.has(key)) fail("Duplicate JSON object key.");
        seen.add(key);
        ws();
        if (text[pos++] !== ":") fail("Invalid JSON object.");
        result[key] = value(depth + 1);
        ws();
        if (text[pos] === "}") {
          pos++;
          return result;
        }
        if (text[pos++] !== ",") fail("Invalid JSON object.");
      }
    }
    for (const [token, result] of [
      ["null", null],
      ["true", true],
      ["false", false],
    ]) {
      if (text.startsWith(token, pos)) {
        pos += token.length;
        return result;
      }
    }
    const number = /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(
      text.slice(pos),
    );
    if (number && number.index === 0) {
      pos += number[0].length;
      // JSON 1.0 and 1e0 are floating values in the Python parser, not indices.
      return /[.eE]/.test(number[0])
        ? { nonIntegerJsonNumber: true }
        : Number(number[0]);
    }
    fail("Invalid JSON value.");
  }
  const result = value(0);
  ws();
  if (pos !== text.length) fail("Unexpected bytes after JSON document.");
  return result;
}

function exactKeys(obj, keys, where) {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj))
    fail(`${where} must be an object.`);
  const actual = Object.keys(obj);
  if (
    actual.length !== keys.length ||
    keys.some((key) => !Object.hasOwn(obj, key))
  )
    fail(`${where} has missing or unknown fields.`);
}

function hexDyadic(text) {
  if (typeof text !== "string")
    fail("Coefficients must be canonical finite float.hex strings.");
  if (text === "0x0.0p+0" || text === "-0x0.0p+0")
    return { integer: 0n, exponent: 0 };
  const match = /^(-?)0x([01])\.([0-9a-f]{13})p([+-])([0-9]+)$/.exec(text);
  if (!match) fail("Noncanonical or nonfinite float.hex coefficient.");
  // Python emits no leading zeroes in exponents, and always emits a plus for 0.
  if (
    (match[5].length > 1 && match[5][0] === "0") ||
    (match[4] === "-" && match[5] === "0")
  )
    fail("Noncanonical float.hex exponent.");
  const exp = Number(`${match[4]}${match[5]}`);
  if (
    !Number.isSafeInteger(exp) ||
    exp < -1022 ||
    exp > 1023 ||
    (match[2] === "0" && exp !== -1022)
  )
    fail("Noncanonical or nonfinite float.hex exponent.");
  let integer = BigInt(`0x${match[2]}${match[3]}`);
  if (integer === 0n) fail("Zero must use the canonical zero spelling.");
  let exponent = exp - 52;
  while ((integer & 1n) === 0n) {
    integer >>= 1n;
    exponent++;
  }
  if (match[1]) integer = -integer;
  return { integer, exponent };
}
function vector(value, n, where) {
  if (!Array.isArray(value) || value.length !== n)
    fail(`${where} has the wrong dimension.`);
  return value.map(hexDyadic);
}
function matrix(value, n, where) {
  if (!Array.isArray(value) || value.length !== n)
    fail(`${where} has the wrong dimension.`);
  return value.map((row) => vector(row, n, where));
}
function scaled(values) {
  let exponent = 0,
    hasNonzero = false;
  for (const v of values)
    if (v.integer !== 0n) {
      exponent = hasNonzero ? Math.min(exponent, v.exponent) : v.exponent;
      hasNonzero = true;
    }
  return {
    exponent,
    values: values.map((v) =>
      v.integer === 0n ? 0n : v.integer << BigInt(v.exponent - exponent),
    ),
  };
}
function scaledMatrix(rows) {
  const n = rows.length,
    flat = scaled(rows.flat());
  return {
    exponent: flat.exponent,
    values: Array.from({ length: n }, (_, i) =>
      flat.values.slice(i * n, (i + 1) * n),
    ),
  };
}
const abs = (a) => (a < 0n ? -a : a);
function gcd(a, b) {
  a = abs(a);
  while (b) {
    const t = a % b;
    a = b;
    b = t;
  }
  return a;
}
function rational(numerator, denominator = 1n) {
  if (denominator <= 0n) fail("Invalid rational denominator.");
  const divisor = gcd(numerator, denominator);
  return { n: numerator / divisor, d: denominator / divisor };
}
function fromDyadic(integer, exponent) {
  return exponent >= 0
    ? rational(integer << BigInt(exponent))
    : rational(integer, 1n << BigInt(-exponent));
}
function out(value) {
  return { numerator: value.n.toString(), denominator: value.d.toString() };
}
function add(a, b, subtract = false) {
  return rational(a.n * b.d + (subtract ? -b.n : b.n) * a.d, a.d * b.d);
}
function compare(a, b) {
  const difference = a.n * b.d - b.n * a.d;
  return difference < 0n ? -1 : difference > 0n ? 1 : 0;
}
function shift(integer, from, to) {
  return integer === 0n ? 0n : integer << BigInt(from - to);
}

export function verifyText(text) {
  const doc = parseDocument(text);
  exactKeys(doc, ROOT_KEYS, "Certificate");
  if (doc.format !== "certloom-linear-v1") fail("Unknown certificate format.");
  if (!Array.isArray(doc.A) || doc.A.length < 1 || doc.A.length > MAX_N)
    fail("Dimension must be between 1 and 128.");
  const n = doc.A.length;
  // Validate all input before any matrix products.
  const A = scaledMatrix(matrix(doc.A, n, "A")),
    R = scaledMatrix(matrix(doc.R, n, "R"));
  const b = scaled(vector(doc.b, n, "b")),
    x = scaled(vector(doc.x, n, "x"));
  let decision = null;
  if (doc.decision !== null) {
    exactKeys(doc.decision, ["index", "above"], "Decision");
    if (
      !Number.isInteger(doc.decision.index) ||
      doc.decision.index < 0 ||
      doc.decision.index >= n
    )
      fail("Decision index must be an integer in range.");
    const threshold = hexDyadic(doc.decision.above);
    decision = {
      index: doc.decision.index,
      above: fromDyadic(threshold.integer, threshold.exponent),
    };
  }
  const arExponent = A.exponent + R.exponent,
    cExponent = Math.min(0, arExponent);
  const identity = 1n << BigInt(-cExponent);
  const productShift = BigInt(arExponent - cExponent);
  let qInteger = 0n;
  for (let i = 0; i < n; i++) {
    let rowSum = 0n;
    for (let j = 0; j < n; j++) {
      let dot = 0n;
      for (let k = 0; k < n; k++)
        if (R.values[i][k] !== 0n && A.values[k][j] !== 0n)
          dot += R.values[i][k] * A.values[k][j];
      rowSum += abs((i === j ? identity : 0n) - (dot << productShift));
    }
    if (rowSum > qInteger) qInteger = rowSum;
  }
  const axExponent = A.exponent + x.exponent,
    residualExponent = Math.min(b.exponent, axExponent);
  const residual = [];
  for (let i = 0; i < n; i++) {
    let dot = 0n;
    for (let k = 0; k < n; k++)
      if (A.values[i][k] !== 0n && x.values[k] !== 0n)
        dot += A.values[i][k] * x.values[k];
    residual.push(
      shift(b.values[i], b.exponent, residualExponent) -
        shift(dot, axExponent, residualExponent),
    );
  }
  let etaInteger = 0n;
  for (let i = 0; i < n; i++) {
    let dot = 0n;
    for (let k = 0; k < n; k++)
      if (R.values[i][k] !== 0n && residual[k] !== 0n)
        dot += R.values[i][k] * residual[k];
    if (abs(dot) > etaInteger) etaInteger = abs(dot);
  }
  const q = fromDyadic(qInteger, cExponent),
    eta = fromDyadic(etaInteger, R.exponent + residualExponent);
  const result = {
    status: "not_certified",
    dimension: n,
    q: out(q),
    eta: out(eta),
  };
  if (q.n >= q.d) {
    result.reason = "The recomputed contraction bound q is at least 1; this method cannot certify the solution.";
    return result;
  }
  const radius = rational(eta.n * q.d, eta.d * (q.d - q.n));
  const bounds = x.values.map((v) => {
    const center = fromDyadic(v, x.exponent);
    return { lower: add(center, radius, true), upper: add(center, radius) };
  });
  result.status = "certified";
  result.radius = out(radius);
  result.enclosures = bounds.map((v) => ({
    lower: out(v.lower),
    upper: out(v.upper),
  }));
  if (decision) {
    const interval = bounds[decision.index];
    const status =
      compare(interval.lower, decision.above) > 0
        ? "above"
        : compare(interval.upper, decision.above) <= 0
          ? "not_above"
          : "undecidable";
    result.decision = {
      index: decision.index,
      above: out(decision.above),
      status,
      lower: out(interval.lower),
      upper: out(interval.upper),
    };
  }
  return result;
}

export function decimalBound(value, places = 18, direction = "lower") {
  if (!Number.isInteger(places) || places < 0 || places > 1000)
    fail("Decimal places must be between 0 and 1000.");
  if (direction !== "lower" && direction !== "upper")
    fail("Decimal direction must be lower or upper.");
  exactKeys(value, ["numerator", "denominator"], "Rational");
  if (
    typeof value.numerator !== "string" ||
    !/^(?:0|-?[1-9][0-9]*)$/.test(value.numerator) ||
    typeof value.denominator !== "string" ||
    !/^[1-9][0-9]*$/.test(value.denominator) ||
    value.numerator.length > 4096 ||
    value.denominator.length > 4096
  )
    fail("Invalid rational strings.");
  const d = BigInt(value.denominator), n = BigInt(value.numerator);
  if (gcd(n, d) !== 1n) fail("Display rational must be normalized.");
  const numerator = n * 10n ** BigInt(places);
  let rounded = numerator / d;
  const remainder = numerator % d;
  if (direction === "lower" && remainder < 0n) rounded--;
  if (direction === "upper" && remainder > 0n) rounded++;
  const sign = rounded < 0n ? "-" : "",
    digits = abs(rounded)
      .toString()
      .padStart(places + 1, "0");
  return places
    ? `${sign}${digits.slice(0, -places)}.${digits.slice(-places)}`
    : `${sign}${digits}`;
}
