/* Worker lifecycle/ZIP controls only. No numerical-checker or real-browser claim. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

(async () => {
  const source = path.resolve(__dirname, "../web/app.mjs");
  const { createVerifier, zipStored } = await import(pathToFileURL(source));
  const checks = [];
  function check(name, action) {
    action();
    checks.push(name);
  }
  class FakeWorker {
    constructor() {
      this.terminated = false;
      this.sent = [];
    }
    postMessage(message) {
      this.sent.push(message);
    }
    terminate() {
      this.terminated = true;
    }
    send(data) {
      this.onmessage?.({ data });
    }
  }
  const workers = [],
    timers = new Map();
  let timerId = 0;
  const verifier = createVerifier({
    makeWorker: () => {
      const worker = new FakeWorker();
      workers.push(worker);
      return worker;
    },
    setTimer: (callback, delay) => {
      const id = ++timerId;
      timers.set(id, { callback, delay });
      return id;
    },
    clearTimer: (id) => timers.delete(id),
  });
  let first = verifier.verify('{"original":true}');
  const firstRefusal = assert.rejects(first, /cancelled/);
  const firstCallback = workers[0].onmessage;
  check("one typed request and twenty-second deadline", () => {
    assert.deepEqual(workers[0].sent, [{ id: 1, text: '{"original":true}' }]);
    assert.equal([...timers.values()][0].delay, 20000);
  });
  await assert.rejects(verifier.verify("another"), /already running/);
  checks.push("overlapping request refused");
  check("accepted cancellation terminates owned worker", () => {
    assert.equal(verifier.cancel(), true);
    assert.equal(workers[0].terminated, true);
    assert.equal(verifier.busy, false);
    assert.equal(timers.size, 0);
  });
  await firstRefusal;
  const second = verifier.verify("fresh");
  let secondResolved = false;
  second.then(() => {
    secondResolved = true;
  });
  firstCallback({
    data: { id: 2, ok: true, result: { status: "certified", old: true } },
  });
  await Promise.resolve();
  check("late cancelled callback cannot claim fresh work", () => {
    assert.equal(secondResolved, false);
    assert.equal(verifier.busy, true);
  });
  workers[1].send({ id: 1, ok: true, result: { incorrect: true } });
  await Promise.resolve();
  check("wrong response identity ignored", () =>
    assert.equal(secondResolved, false),
  );
  workers[1].send({ id: 2, ok: true, result: { status: "not_certified" } });
  assert.deepEqual(await second, { status: "not_certified" });
  check("fresh request succeeds and worker is released", () => {
    assert.equal(workers.length, 2);
    assert.equal(workers[1].terminated, true);
    assert.equal(timers.size, 0);
  });
  const third = verifier.verify("deadline"),
    thirdRefusal = assert.rejects(third, /20-second/);
  [...timers.values()][0].callback();
  await thirdRefusal;
  check("deadline cancels and releases current worker", () => {
    assert.equal(workers[2].terminated, true);
    assert.equal(verifier.busy, false);
    assert.equal(timers.size, 0);
  });
  const fourth = verifier.verify("error");
  const fourthRefusal = assert.rejects(fourth, /Duplicate key/);
  workers[3].send({ id: 4, ok: false, error: { message: "Duplicate key" } });
  await fourthRefusal;
  checks.push("worker validation refusal carries no result");
  const fifth = verifier.verify("broken");
  const fifthRefusal = assert.rejects(fifth, /could not run/);
  workers[4].onerror();
  await fifthRefusal;
  checks.push("worker startup failure releases state");
  const sixth = verifier.verify("malformed-response");
  const sixthRefusal = assert.rejects(sixth, /invalid response/);
  workers[5].send({ id: 6, ok: true, result: null });
  await sixthRefusal;
  checks.push("invalid worker response refused");
  const count = workers.length;
  await assert.rejects(verifier.verify("é".repeat(1024 * 1024 + 1)), /2 MiB/);
  check("UTF-8 byte limit enforced before worker creation", () =>
    assert.equal(workers.length, count),
  );
  check("inactive cancellation is harmless", () =>
    assert.equal(verifier.cancel(), false),
  );
  const unavailable = createVerifier({
    makeWorker: () => {
      throw new Error("worker unavailable");
    },
  });
  await assert.rejects(unavailable.verify("valid"), /unavailable/);
  check("worker construction failure leaves no active operation", () =>
    assert.equal(unavailable.busy, false),
  );

  const encode = new TextEncoder(),
    entries = [
      { name: "checker.py", bytes: encode.encode("print('exact')\n") },
      {
        name: "certificate.json",
        bytes: encode.encode('{"preserved":"é","line":"\\n"}\n'),
      },
      { name: "verification.json", bytes: encode.encode("{}\n") },
      {
        name: "README.txt",
        bytes: encode.encode("python3 -I -S checker.py certificate.json\n"),
      },
    ];
  const zip = zipStored(entries),
    view = new DataView(zip.buffer);
  let offset = 0;
  function independentCrc(bytes) {
    let value = -1;
    for (const byte of bytes) {
      value ^= byte;
      for (let bit = 0; bit < 8; bit++)
        value = (value >>> 1) ^ (value & 1 ? 0xedb88320 : 0);
    }
    return (value ^ -1) >>> 0;
  }
  check(
    "ZIP preserves original bytes, CRCs, UTF-8 flag and stored method",
    () => {
      for (const entry of entries) {
        assert.equal(view.getUint32(offset, true), 0x04034b50);
        assert.equal(view.getUint16(offset + 6, true), 0x800);
        assert.equal(view.getUint16(offset + 8, true), 0);
        assert.equal(
          view.getUint32(offset + 14, true),
          independentCrc(entry.bytes),
        );
        assert.equal(view.getUint32(offset + 18, true), entry.bytes.length);
        const nameLength = view.getUint16(offset + 26, true);
        assert.equal(
          new TextDecoder().decode(
            zip.subarray(offset + 30, offset + 30 + nameLength),
          ),
          entry.name,
        );
        assert.deepEqual(
          zip.subarray(
            offset + 30 + nameLength,
            offset + 30 + nameLength + entry.bytes.length,
          ),
          entry.bytes,
        );
        offset += 30 + nameLength + entry.bytes.length;
      }
      assert.equal(view.getUint32(offset, true), 0x02014b50);
      assert.equal(view.getUint32(zip.length - 22, true), 0x06054b50);
      assert.equal(view.getUint16(zip.length - 14, true), 4);
      assert.equal(view.getUint32(zip.length - 6, true), offset);
    },
  );
  check("ZIP refuses traversal, duplicate names and wrong byte types", () => {
    assert.throws(
      () => zipStored([{ name: "../checker.py", bytes: encode.encode("a") }]),
      /Invalid/,
    );
    assert.throws(() => zipStored([entries[0], entries[0]]), /Invalid/);
    assert.throws(
      () => zipStored([{ name: "checker.py", bytes: "text" }]),
      /Invalid/,
    );
  });
  const html = fs.readFileSync(
    path.resolve(__dirname, "../web/index.html"),
    "utf8",
  );
  const app = fs.readFileSync(source, "utf8");
  check(
    "static UI has self-only CSP, relative assets and text-only metadata rendering",
    () => {
      assert.match(html, /worker-src 'self'/);
      assert.match(html, /connect-src 'self'/);
      assert.match(html, /src="\.\/app\.mjs"/);
      assert.match(html, /href="\.\/style\.css"/);
      assert.doesNotMatch(app, /innerHTML|eval\(|new Function/);
      for (const id of [
        "cancel",
        "decision",
        "vector-body",
        "download-bundle",
        "certificate-hash",
      ])
        assert.match(html, new RegExp(`id="${id}"`));
    },
  );
  const receipt = {
    checks: checks.length,
    names: checks,
    scope:
      "Fake workers/timers, ZIP byte structure and static source checks. Not actual browser or numerical checker verification.",
  };
  if (process.argv[2])
    fs.writeFileSync(
      path.resolve(process.argv[2]),
      JSON.stringify(receipt, null, 2) + "\n",
    );
  console.log(JSON.stringify(receipt));
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
