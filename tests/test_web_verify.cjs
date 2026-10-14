// Independent reference deliberately uses ordinary reduced rational arithmetic,
// rather than the production checker's shared-scale dyadic matrix arithmetic.
const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const checks = [];
const abs = (n) => (n < 0n ? -n : n);
function gcd(a, b) {
  a = abs(a);
  while (b) [a, b] = [b, a % b];
  return a;
}
function f(n, d = 1n) {
  if (d < 0n) {
    n = -n;
    d = -d;
  }
  const g = gcd(n, d);
  return [n / g, d / g];
}
const add = (a, b) => f(a[0] * b[1] + b[0] * a[1], a[1] * b[1]);
const sub = (a, b) => f(a[0] * b[1] - b[0] * a[1], a[1] * b[1]);
const mul = (a, b) => f(a[0] * b[0], a[1] * b[1]);
const div = (a, b) => f(a[0] * b[1], a[1] * b[0]);
const absolute = (a) => [abs(a[0]), a[1]];
const cmp = (a, b) =>
  a[0] * b[1] < b[0] * a[1] ? -1 : a[0] * b[1] > b[0] * a[1] ? 1 : 0;
const out = (a) => ({
  numerator: a[0].toString(),
  denominator: a[1].toString(),
});
const sum = (values) => values.reduce(add, [0n, 1n]);
const max = (values) =>
  values.reduce((a, b) => (cmp(a, b) > 0 ? a : b), [0n, 1n]);
// Test-only fixture encoder and rational oracle decode raw binary64 bits. It is
// independent of the production canonical-hex parsing and shared-scale engine.
function bits(value) {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, value, false);
  return view.getBigUint64(0, false);
}
function hex(value) {
  const raw = bits(value),
    sign = raw >> 63n ? "-" : "",
    exponent = Number((raw >> 52n) & 2047n),
    fraction = raw & ((1n << 52n) - 1n);
  if (exponent === 0 && fraction === 0n) return `${sign}0x0.0p+0`;
  const e = exponent === 0 ? -1022 : exponent - 1023;
  return `${sign}0x${exponent === 0 ? 0 : 1}.${fraction.toString(16).padStart(13, "0")}p${e >= 0 ? "+" : ""}${e}`;
}
function binaryFraction(value) {
  const raw = bits(value),
    e = Number((raw >> 52n) & 2047n),
    fraction = raw & ((1n << 52n) - 1n);
  let n = e === 0 ? fraction : (1n << 52n) + fraction,
    power = (e === 0 ? -1022 : e - 1023) - 52;
  if (raw >> 63n) n = -n;
  return power >= 0 ? f(n << BigInt(power)) : f(n, 1n << BigInt(-power));
}
function document(A, R, b, x, decision = null) {
  return {
    format: "certloom-linear-v1",
    A: A.map((row) => row.map(hex)),
    R: R.map((row) => row.map(hex)),
    b: b.map(hex),
    x: x.map(hex),
    decision:
      decision === null
        ? null
        : { index: decision.index, above: hex(decision.above) },
  };
}
function reference(A0, R0, b0, x0, decision = null) {
  const A = A0.map((row) => row.map(binaryFraction)),
    R = R0.map((row) => row.map(binaryFraction)),
    b = b0.map(binaryFraction),
    x = x0.map(binaryFraction),
    n = A.length;
  const q = max(
    R.map((row, i) =>
      sum(
        A[0].map((_, j) =>
          absolute(
            sub(
              [i === j ? 1n : 0n, 1n],
              sum(row.map((r, k) => mul(r, A[k][j]))),
            ),
          ),
        ),
      ),
    ),
  );
  const residual = b.map((v, i) =>
    sub(v, sum(A[i].map((a, k) => mul(a, x[k])))),
  );
  const eta = max(
    R.map((row) => absolute(sum(row.map((r, k) => mul(r, residual[k]))))),
  );
  const result = {
    status: "not_certified",
    dimension: n,
    q: out(q),
    eta: out(eta),
  };
  if (cmp(q, [1n, 1n]) >= 0) {
    result.reason = "The recomputed contraction bound q is at least 1; this method cannot certify the solution.";
    return result;
  }
  const radius = div(eta, sub([1n, 1n], q)),
    intervals = x.map((v) => ({
      lower: sub(v, radius),
      upper: add(v, radius),
    }));
  result.status = "certified";
  result.radius = out(radius);
  result.enclosures = intervals.map((v) => ({
    lower: out(v.lower),
    upper: out(v.upper),
  }));
  if (decision !== null) {
    const v = intervals[decision.index],
      above = binaryFraction(decision.above);
    result.decision = {
      index: decision.index,
      above: out(above),
      status:
        cmp(v.lower, above) > 0
          ? "above"
          : cmp(v.upper, above) <= 0
            ? "not_above"
            : "undecidable",
      lower: out(v.lower),
      upper: out(v.upper),
    };
  }
  return result;
}

(async () => {
  const { verifyText, decimalBound, VerificationError } = await import(
    pathToFileURL(path.resolve(__dirname, "../web/verify.mjs"))
  );
  function check(name, fn) {
    fn();
    checks.push(name);
  }
  function matches(A, R, b, x, decision) {
    assert.deepEqual(
      verifyText(JSON.stringify(document(A, R, b, x, decision))),
      reference(A, R, b, x, decision),
    );
  }
  check("exact zero radius and negative zero", () =>
    matches([[1]], [[1]], [-0], [0], { index: 0, above: -0 }),
  );
  check("non-dyadic radius and above decision", () =>
    matches([[1.5]], [[0.5]], [1], [0.5], { index: 0, above: 0 }),
  );
  check("upper equality is not_above", () =>
    matches([[1]], [[1]], [2], [1], { index: 0, above: 2 }),
  );
  check("lower equality is undecidable", () =>
    matches([[1]], [[1]], [2], [1], { index: 0, above: 0 }),
  );
  check("zero R refuses theorem and decision", () =>
    matches([[1]], [[0]], [3], [0], { index: 0, above: 0 }),
  );
  check("q greater than one refuses", () =>
    matches([[2]], [[2]], [1], [0], null),
  );
  check("off-diagonal exact row sums", () =>
    matches(
      [
        [2, 0.5],
        [-0.25, 1],
      ],
      [
        [0.5, -0.25],
        [0.125, 1],
      ],
      [1, 2],
      [0.25, 1.5],
      { index: 1, above: 1 },
    ),
  );
  check("binary64 extremes and subnormal exactness", () => {
    matches(
      [[Number.MAX_VALUE]],
      [[Number.MIN_VALUE]],
      [Number.MIN_VALUE],
      [-Number.MIN_VALUE],
      null,
    );
    matches([[Number.MIN_VALUE]], [[Number.MAX_VALUE]], [1], [1], null);
    matches([[1]], [[1]], [Number.MIN_VALUE], [0], { index: 0, above: 0 });
  });
  check("independent deterministic dyadic systems", () => {
    let seed = 190013;
    const next = () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed;
    };
    for (let trial = 0; trial < 64; trial++) {
      const n = 1 + (next() % 4);
      const A = Array.from({ length: n }, (_, i) =>
        Array.from({ length: n }, (_, j) =>
          i === j ? 1 + (next() % 4) / 16 : ((next() % 7) - 3) / 64,
        ),
      );
      const R = Array.from({ length: n }, (_, i) =>
        Array.from({ length: n }, (_, j) =>
          i === j ? 1 : ((next() % 3) - 1) / 128,
        ),
      );
      const b = Array.from({ length: n }, () => ((next() % 33) - 16) / 8),
        x = Array.from({ length: n }, () => ((next() % 33) - 16) / 8);
      matches(A, R, b, x, {
        index: next() % n,
        above: ((next() % 17) - 8) / 4,
      });
    }
  });
  const base = JSON.stringify(
    document([[1]], [[1]], [2], [1], { index: 0, above: 2 }),
  );
  const refuses = (text) =>
    assert.throws(() => verifyText(text), VerificationError);
  check("duplicate root and decoded nested keys refuse", () => {
    refuses(
      base.replace('"format":', '"format":"certloom-linear-v1","format":'),
    );
    refuses(base.replace('"index":0', '"index":0,"\\u0069ndex":0'));
  });
  check("all schema/type/index constraints", () => {
    for (const index of [true, false, 1, -1, 0.5, "0", null]) {
      const d = JSON.parse(base);
      d.decision.index = index;
      refuses(JSON.stringify(d));
    }
    refuses(base.replace('"index":0', '"index":0.0'));
    refuses(base.replace('"index":0', '"index":0e0'));
    const changes = [
      (d) => {
        delete d.R;
      },
      (d) => {
        d.extra = 0;
      },
      (d) => {
        d.A = [];
      },
      (d) => {
        d.A = [[hex(1), hex(1)]];
      },
      (d) => {
        d.R = [[]];
      },
      (d) => {
        d.b = [1];
      },
      (d) => {
        d.x = {};
      },
      (d) => {
        d.decision.extra = 0;
      },
      (d) => {
        d.decision = [];
      },
      (d) => {
        d.format = "other";
      },
    ];
    for (const change of changes) {
      const d = JSON.parse(base);
      change(d);
      refuses(JSON.stringify(d));
    }
  });
  check("canonical finite hex only", () => {
    const bad = [
      "0x1.0p+0",
      "+0x1.0000000000000p+0",
      "0x1.0000000000000p-0",
      "0x1.0000000000000p+00",
      "0x1.00000000000000p+0",
      "0X1.0000000000000p+0",
      "0x1.A000000000000p+0",
      "0x1.0000000000000p+1024",
      "0x1.0000000000000p-1023",
      "0x0.0000000000001p-1021",
      "0x0.0000000000000p-1022",
      "0x0.0p-0",
      "nan",
      "inf",
      "1",
      "1+1",
    ];
    for (const value of bad) {
      const d = JSON.parse(base);
      d.b[0] = value;
      refuses(JSON.stringify(d));
    }
  });
  check("JSON grammar depth and byte limits", () => {
    for (const value of [
      "",
      base + "x",
      base.replace('"A":[[', '"A":[[,'),
      base.replace('"A":', "A:"),
      "null",
      "[]",
      base.replace('"index":0', '"index":01'),
    ])
      refuses(value);
    refuses("[".repeat(10) + "0" + "]".repeat(10));
    refuses(" ".repeat(2 * 1024 * 1024 + 1));
    refuses('"' + "é".repeat(1024 * 1024) + '"');
    const d = JSON.parse(base);
    d.A = Array.from({ length: 129 }, () => []);
    refuses(JSON.stringify(d));
  });
  check("maximum accepted dimension exact identity", () => {
    const n = 128,
      A = Array.from({ length: n }, (_, i) =>
        Array.from({ length: n }, (_, j) => (i === j ? 1 : 0)),
      );
    const result = verifyText(
      JSON.stringify(document(A, A, Array(n).fill(1), Array(n).fill(1))),
    );
    assert.equal(result.status, "certified");
    assert.deepEqual(result.radius, out([0n, 1n]));
    assert.equal(result.enclosures.length, 128);
  });
  check("outward decimals including negative values", () => {
    assert.equal(decimalBound(out([1n, 3n]), 3, "lower"), "0.333");
    assert.equal(decimalBound(out([1n, 3n]), 3, "upper"), "0.334");
    assert.equal(decimalBound(out([-1n, 3n]), 3, "lower"), "-0.334");
    assert.equal(decimalBound(out([-1n, 3n]), 3, "upper"), "-0.333");
    assert.equal(decimalBound(out([-1n, 3n]), 0, "lower"), "-1");
    assert.equal(decimalBound(out([-1n, 3n]), 0, "upper"), "0");
    assert.equal(decimalBound(out([0n, 1n]), 2, "lower"), "0.00");
    assert.equal(decimalBound(out([-2n, 1n]), 2, "upper"), "-2.00");
    assert.throws(() => decimalBound({numerator:"2",denominator:"2"}), VerificationError);
    assert.throws(() => decimalBound({numerator:"0",denominator:"2"}), VerificationError);
    for (const places of [true, -1, 1001, 0.5, "3"])
      assert.throws(
        () => decimalBound(out([1n, 3n]), places),
        VerificationError,
      );
    assert.throws(
      () => decimalBound(out([1n, 3n]), 2, "nearest"),
      VerificationError,
    );
    assert.throws(
      () => decimalBound({ numerator: "1", denominator: "0" }),
      VerificationError,
    );
  });
  const messages = [],
    timers = [];
  let handler;
  const oldSelf = global.self,
    oldTimer = global.setTimeout;
  global.self = {
    addEventListener: (type, fn) => {
      assert.equal(type, "message");
      handler = fn;
    },
    postMessage: (value) => messages.push(value),
  };
  global.setTimeout = (fn) => {
    timers.push(fn);
    return timers.length;
  };
  try {
    await import(pathToFileURL(path.resolve(__dirname, "../web/worker.mjs")));
    check("worker protocol refuses malformed and oversized requests", () => {
      for (const data of [
        null,
        [],
        { id: true, text: base },
        { id: -1, text: base },
        { id: Infinity, text: base },
        { id: "", text: base },
        { id: 1, text: base, extra: 1 },
        { id: 1, text: {} },
      ])
        handler({ data });
      assert.equal(messages.length, 8);
      assert(messages.every((m) => m.id === null && m.ok === false));
      messages.length = 0;
      handler({ data: { id: 7, text: " ".repeat(2 * 1024 * 1024 + 1) } });
      assert.equal(messages.pop().id, 7);
      assert.equal(timers.length, 0);
    });
    check("worker acceptance overlap refusal and fresh requests", () => {
      handler({ data: { id: 1, text: base } });
      handler({ data: { id: 2, text: base } });
      assert.equal(messages.pop().ok, false);
      assert.equal(timers.length, 1);
      timers.shift()();
      const result = messages.pop();
      assert.equal(result.id, 1);
      assert.equal(result.ok, true);
      assert.deepEqual(result.result, verifyText(base));
      handler({ data: { id: "invalid", text: "{}" } });
      timers.shift()();
      assert.equal(messages.pop().ok, false);
      handler({ data: { id: "new", text: base } });
      timers.shift()();
      assert.equal(messages.pop().ok, true);
    });
  } finally {
    global.self = oldSelf;
    global.setTimeout = oldTimer;
  }
  console.log(
    JSON.stringify(
      {
        status: "passed",
        checks: checks.length,
        referenceSystems: 74,
        checksPassed: checks,
      },
      null,
      2,
    ),
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
