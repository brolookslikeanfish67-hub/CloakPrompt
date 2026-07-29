const assert = require("assert");
const { Masker } = require("../index.js");

function test(name, fn) {
  try {
    fn();
    console.log("PASS", name);
  } catch (e) {
    console.log("FAIL", name, "->", e.message);
    process.exitCode = 1;
  }
}

test("email detected and masked", () => {
  const masker = new Masker();
  const { maskedText, mapping } = masker.mask("Contact me at jane.doe@acme.com please.");
  assert(!maskedText.includes("jane.doe@acme.com"));
  assert(maskedText.includes("[EMAIL_1]"));
  assert.strictEqual(mapping["[EMAIL_1]"], "jane.doe@acme.com");
});

test("round trip unmask", () => {
  const masker = new Masker();
  const original = "Hi, I'm Jane Doe. Email me at jane@acme.com or call 555-123-4567.";
  const { maskedText, mapping } = masker.mask(original);
  assert(!maskedText.includes("Jane Doe"));
  assert(!maskedText.includes("jane@acme.com"));
  const fakeReply = `Sure, I'll follow up with ${Object.keys(mapping)[0]} shortly.`;
  const restored = masker.unmask(fakeReply, mapping);
  assert(!restored.includes("["));
});

test("credit card Luhn filters false positives", () => {
  const masker = new Masker();
  const valid = masker.mask("Card: 4111 1111 1111 1111");
  assert.strictEqual(Object.keys(valid.mapping).length, 1);
  const invalid = masker.mask("Order number: 1234 5678 9012 3459");
  assert.strictEqual(Object.keys(invalid.mapping).length, 0);
});

test("session mapping reuses placeholders", () => {
  const masker = new Masker();
  const r1 = masker.mask("Jane Doe emailed jane@acme.com.");
  const r2 = masker.mask("Jane Doe called again about jane@acme.com.", r1.mapping);
  for (const k of Object.keys(r1.mapping)) {
    assert.strictEqual(r2.mapping[k], r1.mapping[k]);
  }
});

test("no PII passthrough", () => {
  const masker = new Masker();
  const text = "What is the capital of France?";
  const { maskedText, mapping } = masker.mask(text);
  assert.strictEqual(maskedText, text);
  assert.strictEqual(Object.keys(mapping).length, 0);
});
