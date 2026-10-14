const MAX_BYTES = 2 * 1024 * 1024;
const encoder = new TextEncoder();

/** Task-owned worker lifecycle. A new worker is used for every computation. */
export function createVerifier({
  makeWorker,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
  deadline = 20000,
} = {}) {
  let active = null,
    epoch = 0,
    nextId = 0;
  function cancel(reason = "Computation cancelled.") {
    if (!active) return false;
    const operation = active;
    active = null;
    epoch++;
    clearTimer(operation.timer);
    operation.worker.onmessage = null;
    operation.worker.onerror = null;
    operation.worker.terminate();
    operation.reject(new Error(reason));
    return true;
  }
  function verify(text) {
    if (active)
      return Promise.reject(new Error("A computation is already running."));
    if (typeof text !== "string" || encoder.encode(text).length > MAX_BYTES)
      return Promise.reject(new Error("Certificate exceeds the 2 MiB limit."));
    const generation = ++epoch,
      id = ++nextId;
    return new Promise((resolve, reject) => {
      let worker;
      try {
        worker = makeWorker();
      } catch (error) {
        reject(error);
        return;
      }
      const operation = { worker, reject, timer: null };
      active = operation;
      function finish(error, result) {
        if (active !== operation || generation !== epoch) return;
        active = null;
        clearTimer(operation.timer);
        worker.onmessage = null;
        worker.onerror = null;
        worker.terminate();
        if (error) reject(error);
        else resolve(result);
      }
      worker.onmessage = (event) => {
        if (
          generation !== epoch ||
          active !== operation ||
          event.data?.id !== id
        )
          return;
        const response = event.data;
        if (
          response.ok === true &&
          response.result &&
          typeof response.result === "object"
        )
          finish(null, response.result);
        else if (response.ok === false)
          finish(
            new Error(
              typeof response.error === "string"
                ? response.error
                : response.error?.message ||
                  "The verifier refused this certificate.",
            ),
          );
        else finish(new Error("The verifier returned an invalid response."));
      };
      worker.onerror = () =>
        finish(
          new Error(
            "The computation worker could not run. Serve the bundle over HTTP and try again.",
          ),
        );
      operation.timer = setTimer(
        () =>
          cancel(
            "The 20-second computation limit was reached. No claim was retained.",
          ),
        deadline,
      );
      try {
        worker.postMessage({ id, text });
      } catch (error) {
        finish(error);
      }
    });
  }
  return {
    verify,
    cancel,
    get busy() {
      return active !== null;
    },
  };
}

const crcTable = Array.from({ length: 256 }, (_, value) => {
  for (let bit = 0; bit < 8; bit++)
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  return value >>> 0;
});
function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = crcTable[(crc ^ byte) & 255] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}
/** Standards-conforming ZIP method 0. Fixed filenames, UTF-8 flag, known CRCs. */
export function zipStored(files) {
  if (!Array.isArray(files) || files.length > 65535)
    throw new Error("Invalid archive entries.");
  const chunks = [],
    central = [],
    names = new Set();
  let offset = 0,
    centralSize = 0;
  for (const { name, bytes } of files) {
    if (
      !/^[A-Za-z][A-Za-z0-9._-]*$/.test(name) ||
      names.has(name) ||
      !(bytes instanceof Uint8Array)
    )
      throw new Error("Invalid archive member.");
    names.add(name);
    const filename = encoder.encode(name),
      crc = crc32(bytes);
    if (
      filename.length > 65535 ||
      bytes.length > 0xffffffff ||
      offset > 0xffffffff
    )
      throw new Error("Archive too large.");
    const local = new Uint8Array(30 + filename.length),
      lv = new DataView(local.buffer);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true);
    lv.setUint16(6, 0x800, true);
    lv.setUint16(12, 0x2821, true);
    lv.setUint32(14, crc, true);
    lv.setUint32(18, bytes.length, true);
    lv.setUint32(22, bytes.length, true);
    lv.setUint16(26, filename.length, true);
    local.set(filename, 30);
    const entry = new Uint8Array(46 + filename.length),
      cv = new DataView(entry.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(8, 0x800, true);
    cv.setUint16(14, 0x2821, true);
    cv.setUint32(16, crc, true);
    cv.setUint32(20, bytes.length, true);
    cv.setUint32(24, bytes.length, true);
    cv.setUint16(28, filename.length, true);
    cv.setUint32(42, offset, true);
    entry.set(filename, 46);
    chunks.push(local, bytes);
    central.push(entry);
    offset += local.length + bytes.length;
    centralSize += entry.length;
  }
  if (offset + centralSize + 22 > 0xffffffff)
    throw new Error("Archive too large.");
  const end = new Uint8Array(22),
    ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, files.length, true);
  ev.setUint16(10, files.length, true);
  ev.setUint32(12, centralSize, true);
  ev.setUint32(16, offset, true);
  const archive = new Uint8Array(offset + centralSize + end.length);
  let cursor = 0;
  for (const part of [...chunks, ...central, end]) {
    archive.set(part, cursor);
    cursor += part.length;
  }
  return archive;
}

function midpoint(lower, upper) {
  const ln = BigInt(lower.numerator),
    ld = BigInt(lower.denominator);
  const un = BigInt(upper.numerator),
    ud = BigInt(upper.denominator);
  const numerator = ln * ud + un * ld,
    denominator = 2n * ld * ud;
  let a = numerator < 0n ? -numerator : numerator,
    b = denominator;
  while (b) [a, b] = [b, a % b];
  return {
    numerator: (numerator / a).toString(),
    denominator: (denominator / a).toString(),
  };
}

async function init() {
  const { decimalBound } = await import("./verify.mjs");
  const $ = (id) => document.getElementById(id);
  const textInput = $("certificate-text"),
    fileInput = $("certificate-file");
  const verifier = createVerifier({
    makeWorker: () =>
      new Worker(new URL("./worker.mjs", import.meta.url), { type: "module" }),
  });
  let revision = 0,
    current = null,
    selected = null,
    loadController = null,
    exporting = false;
  const display = (fraction, direction = "upper") =>
    decimalBound(fraction, 18, direction);
  const exact = (fraction) => `${fraction.numerator} / ${fraction.denominator}`;
  const setText = (id, text) => {
    $(id).textContent = text;
  };
  function activity(text) {
    setText("activity", text);
  }
  function failure(error) {
    setText("error", error?.message || String(error));
    $("error").hidden = false;
  }
  function buttons() {
    $("verify").disabled = !textInput.value.trim() || verifier.busy;
    $("cancel").disabled = !verifier.busy;
    $("download-bundle").disabled = !current || exporting;
    $("download-receipt").disabled = !current;
  }
  function invalidate(
    message = "Input changed. Run the check again; the previous claim has been revoked.",
  ) {
    revision++;
    current = null;
    if (loadController) {
      loadController.abort();
      loadController = null;
    }
    verifier.cancel("Input changed. Computation cancelled.");
    $("result").hidden = true;
    $("empty").hidden = false;
    $("error").hidden = true;
    activity(message);
    buttons();
  }
  function chooseText(text, name, exampleId = null) {
    invalidate("Certificate ready. Check with exact arithmetic.");
    textInput.value = text;
    selected = exampleId;
    setText("file-name", name);
    for (const button of $("examples").querySelectorAll("button"))
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.exampleId === selected),
      );
    buttons();
  }
  textInput.addEventListener("input", () => {
    selected = null;
    setText("file-name", "Edited certificate");
    invalidate();
    for (const button of $("examples").querySelectorAll("button"))
      button.setAttribute("aria-pressed", "false");
  });
  async function boundedFetch(url, signal, limit = MAX_BYTES) {
    const response = await fetch(url, {
      signal,
      credentials: "omit",
      redirect: "error",
    });
    if (!response.ok)
      throw new Error(
        `Could not load the local file (HTTP ${response.status}).`,
      );
    const reader = response.body?.getReader();
    if (!reader)
      throw new Error("Streaming file reads are unavailable in this browser.");
    let length = 0;
    const parts = [];
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        length += value.length;
        if (length > limit) {
          await reader.cancel();
          throw new Error("Local file exceeds the allowed size.");
        }
        parts.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    const bytes = new Uint8Array(length);
    let offset = 0;
    for (const part of parts) {
      bytes.set(part, offset);
      offset += part.length;
    }
    return bytes;
  }
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    invalidate("Reading certificate locally…");
    const generation = revision;
    try {
      if (file.size > MAX_BYTES)
        throw new Error("Certificate exceeds the 2 MiB limit.");
      const bytes = new Uint8Array(await file.arrayBuffer());
      const text = new TextDecoder("utf-8", {
        fatal: true,
        ignoreBOM: true,
      }).decode(bytes);
      if (generation !== revision) return;
      chooseText(text, file.name);
    } catch (error) {
      if (generation === revision) {
        failure(error);
        activity("No new certificate was loaded.");
      }
    } finally {
      fileInput.value = "";
    }
  });
  async function hash(text) {
    const digest = await crypto.subtle.digest(
      "SHA-256",
      typeof text === "string" ? encoder.encode(text) : text,
    );
    return Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
  }
  function render(result) {
    if (!["certified", "not_certified"].includes(result.status))
      throw new Error("Unexpected verification status.");
    const certified = result.status === "certified";
    $("verdict").classList.toggle("refused", !certified);
    setText(
      "status-kicker",
      certified ? "EXACT STORED-SYSTEM CLAIM" : "PROOF PREMISE FAILED",
    );
    setText(
      "status-title",
      certified
        ? "A unique solution. A bounded answer."
        : "No enclosure was certified.",
    );
    setText(
      "status-copy",
      certified
        ? "The contraction test passed. The radius below bounds the candidate's maximum error. A wide radius still means a weak answer."
        : result.reason ||
            "The contraction bound is not below 1. This method cannot certify the answer.",
    );
    setText("q", display(result.q));
    setText("eta", display(result.eta));
    $("q-meter").value = Math.min(1, Math.max(0, Number(display(result.q))));
    setText("radius", certified ? display(result.radius) : "No bound");
    $("vectors").hidden = !certified;
    $("decision").hidden = !certified || !result.decision;
    $("vector-body").replaceChildren();
    if (certified) {
      setText("dimension", `${result.dimension} unknowns · indices start at 0`);
      result.enclosures.forEach((enclosure, index) => {
        const row = document.createElement("tr");
        const values = [
          String(index),
          display(midpoint(enclosure.lower, enclosure.upper)),
          display(enclosure.lower, "lower"),
          display(enclosure.upper, "upper"),
        ];
        for (const value of values) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        }
        const detailsRow = document.createElement("tr");
        detailsRow.className = "exact-row";
        const cell = document.createElement("td");
        cell.colSpan = 4;
        const details = document.createElement("details");
        details.className = "component-details";
        const summary = document.createElement("summary");
        summary.textContent = `Exact bounds for component ${index}`;
        const pre = document.createElement("pre");
        pre.textContent = `Lower: ${exact(enclosure.lower)}\nUpper: ${exact(enclosure.upper)}`;
        details.append(summary, pre);
        cell.append(details);
        detailsRow.append(cell);
        $("vector-body").append(row, detailsRow);
      });
      if (result.decision) {
        const decision = result.decision,
          label = `Solution component ${decision.index}`;
        const descriptions = {
          above: [
            `${label} is strictly above the threshold.`,
            "The guaranteed lower bound is greater than the threshold. This decision follows for the exact stored system.",
          ],
          not_above: [
            `${label} is not above the threshold.`,
            "The guaranteed upper bound is at or below the threshold. This decision follows for the exact stored system.",
          ],
          undecidable: [
            "The threshold remains undecidable.",
            `The interval for ${label} crosses or touches the threshold. The candidate alone does not establish the decision.`,
          ],
        };
        if (!descriptions[decision.status])
          throw new Error("Unexpected threshold status.");
        setText("decision-title", descriptions[decision.status][0]);
        setText("decision-copy", descriptions[decision.status][1]);
        setText("threshold", exact(decision.above));
        setText("decision-lower", display(decision.lower, "lower"));
        setText("decision-upper", display(decision.upper, "upper"));
      }
    }
    setText(
      "exact",
      JSON.stringify(
        {
          q: result.q,
          eta: result.eta,
          ...(certified
            ? { radius: result.radius }
            : { reason: result.reason }),
        },
        null,
        2,
      ),
    );
    $("empty").hidden = true;
    $("result").hidden = false;
  }
  $("verify").addEventListener("click", async () => {
    if (verifier.busy) return;
    invalidate("Checking exact equations in a local worker…");
    const generation = revision,
      certificate = textInput.value;
    try {
      const computation = verifier.verify(certificate);
      buttons();
      const result = await computation;
      if (generation !== revision) return;
      const certificateHash = await hash(certificate);
      if (generation !== revision) return;
      render(result);
      current = { certificate, certificateHash, result };
      setText("certificate-hash", certificateHash);
      activity(
        result.status === "certified"
          ? "Exact check complete. Inspect the radius and the separate threshold decision."
          : "Check complete. The method refused an enclosure; the failed-premise receipt is still exportable.",
      );
    } catch (error) {
      if (generation === revision) {
        current = null;
        $("result").hidden = true;
        $("empty").hidden = false;
        failure(error);
        activity("No numerical claim was retained.");
      }
    } finally {
      buttons();
    }
  });
  $("cancel").addEventListener("click", () => {
    if (verifier.busy)
      invalidate(
        "Computation cancelled. Input retained. The next check starts a fresh worker.",
      );
  });
  function download(bytes, filename, type) {
    const url = URL.createObjectURL(new Blob([bytes], { type }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function receipt(evidence) {
    return encoder.encode(
      JSON.stringify(
        {
          format: "certloom-verification-v1",
          certificate_sha256: evidence.certificateHash,
          scope:
            "Exact stored binary64 linear system; identity is not authenticity.",
          result: evidence.result,
        },
        null,
        2,
      ) + "\n",
    );
  }
  $("download-receipt").addEventListener("click", () => {
    if (current)
      download(receipt(current), "verification.json", "application/json");
  });
  $("download-bundle").addEventListener("click", async () => {
    if (!current || exporting) return;
    const evidence = current,
      generation = revision;
    exporting = true;
    buttons();
    $("error").hidden = true;
    try {
      const checker = await boundedFetch(
        new URL("./checker.py", import.meta.url),
        undefined,
        MAX_BYTES,
      );
      if (generation !== revision || current !== evidence) return;
      const checkerHash = await hash(checker);
      if (generation !== revision || current !== evidence) return;
      const instructions = `Certloom portable verification\n==============================\n\nFrom this directory, run:\n  python3 -I -S checker.py certificate.json\n\nOnly the Python standard library is required. No API, uploaded code or external solver is used. Compare the checker output with the result field in verification.json. Exit 0 means an enclosure is certified, 3 means the proof premise failed, 2 means invalid input or a file error. Threshold verdicts remain separate.\n\nCertificate SHA-256: ${evidence.certificateHash}\nChecker SHA-256: ${checkerHash}\nThese identify bytes, not source authenticity.\n\nThe claim concerns only the exact stored binary64 linear equations. It does not establish physical model correctness, measurement quality or a solver's reliability. A certified interval may be wide; a threshold may remain undecidable.\n\nSource and method: https://github.com/nazeeh111/Certloom\nOriginal code: MIT. Mathematical foundations and scope are documented in the repository.\n`;
      const archive = zipStored([
        { name: "checker.py", bytes: checker },
        {
          name: "certificate.json",
          bytes: encoder.encode(evidence.certificate),
        },
        { name: "verification.json", bytes: receipt(evidence) },
        { name: "README.txt", bytes: encoder.encode(instructions) },
      ]);
      download(archive, "certloom-proof.zip", "application/zip");
      activity(
        "Portable proof exported. Its Python checker can independently recompute this claim.",
      );
    } catch (error) {
      if (generation === revision) failure(error);
    } finally {
      exporting = false;
      buttons();
    }
  });
  try {
    const manifestUrl = new URL("./examples/manifest.json", import.meta.url);
    const manifest = JSON.parse(
      new TextDecoder("utf-8", { fatal: true }).decode(
        await boundedFetch(manifestUrl, undefined, 65536),
      ),
    );
    if (
      manifest.version !== 1 ||
      !Array.isArray(manifest.examples) ||
      manifest.examples.length > 20
    )
      throw new Error("Invalid example manifest.");
    $("examples").replaceChildren();
    for (const example of manifest.examples) {
      if (
        typeof example.id !== "string" ||
        typeof example.title !== "string" ||
        typeof example.description !== "string" ||
        typeof example.file !== "string"
      )
        throw new Error("Invalid example entry.");
      const url = new URL(example.file, manifestUrl);
      if (
        url.origin !== manifestUrl.origin ||
        !url.pathname.startsWith(new URL("./", manifestUrl).pathname) ||
        url.search ||
        url.hash
      )
        throw new Error(
          "Example file must be local to the examples directory.",
        );
      const button = document.createElement("button");
      button.type = "button";
      button.className = "example";
      button.dataset.exampleId = example.id;
      button.setAttribute("aria-pressed", "false");
      const title = document.createElement("strong"),
        description = document.createElement("span");
      title.textContent = example.title;
      description.textContent = example.description;
      button.append(title, description);
      button.addEventListener("click", async () => {
        invalidate(`Loading ${example.title}…`);
        const generation = revision;
        const controller = new AbortController();
        loadController = controller;
        try {
          const bytes = await boundedFetch(url, controller.signal);
          if (generation !== revision) return;
          loadController = null;
          chooseText(
            new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
              bytes,
            ),
            example.title,
            example.id,
          );
        } catch (error) {
          if (generation === revision && error.name !== "AbortError") {
            failure(error);
            activity(
              "Example unavailable. You can still open or paste a certificate.",
            );
          }
        }
      });
      $("examples").append(button);
    }
  } catch (error) {
    $("examples").replaceChildren();
    const message = document.createElement("p");
    message.className = "muted";
    message.textContent =
      "Examples could not load. Open or paste a local certificate.";
    $("examples").append(message);
  }
  window.addEventListener("pagehide", () => {
    verifier.cancel();
    loadController?.abort();
  });
  buttons();
}

if (typeof document !== "undefined")
  init().catch((error) => {
    const status = document.getElementById("activity");
    if (status)
      status.textContent = `The local application could not initialize: ${error.message}. Serve the source bundle over HTTP.`;
  });
