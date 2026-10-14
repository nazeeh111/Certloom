import { verifyText } from "./verify.mjs";

let active = false;
const validId = (id) =>
  (typeof id === "number" && Number.isSafeInteger(id) && id >= 0) ||
  (typeof id === "string" && id.length >= 1 && id.length <= 128);
const sendError = (id, message) =>
  self.postMessage({ id, ok: false, error: message });
self.addEventListener("message", (event) => {
  const message = event.data;
  if (
    message === null ||
    typeof message !== "object" ||
    Array.isArray(message) ||
    Object.keys(message).length !== 2 ||
    !Object.hasOwn(message, "id") ||
    !Object.hasOwn(message, "text") ||
    !validId(message.id) ||
    typeof message.text !== "string"
  ) {
    sendError(null, "Expected a bounded request id and certificate JSON text.");
    return;
  }
  if (active) {
    sendError(message.id, "A verification is already running.");
    return;
  }
  if (
    message.text.length > 2 * 1024 * 1024 ||
    new TextEncoder().encode(message.text).length > 2 * 1024 * 1024
  ) {
    sendError(message.id, "Certificate exceeds the 2 MiB input limit.");
    return;
  }
  active = true;
  // Defer one event turn so a request arriving before work starts can be refused.
  // Cancellation during exact arithmetic is worker termination by the controller.
  setTimeout(() => {
    try {
      self.postMessage({
        id: message.id,
        ok: true,
        result: verifyText(message.text),
      });
    } catch (error) {
      sendError(
        message.id,
        error instanceof Error ? error.message : "Verification failed.",
      );
    } finally {
      active = false;
    }
  }, 0);
});
