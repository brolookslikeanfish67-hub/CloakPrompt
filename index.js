/**
 * CloakPrompt (JS) — local PII masking engine.
 *
 * const { Masker } = require("cloakprompt");
 * const masker = new Masker();
 * const { maskedText, mapping } = masker.mask("Jane Doe <jane@acme.com>, card 4111 1111 1111 1111");
 * // ... send maskedText to your LLM provider ...
 * const restored = masker.unmask(llmReplyText, mapping);
 */

"use strict";

const EMAIL_RE = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
const PHONE_RE = /(?<!\d)(\+?\d{1,3}[\s.-]?)?(\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)/g;
const SSN_RE = /(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)/g;
const IPV4_RE = /(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)/g;
const CC_CANDIDATE_RE = /(?<!\d)(?:\d[ -]?){13,19}(?!\d)/g;

const API_KEY_PATTERNS = [
  /sk-ant-[A-Za-z0-9\-_]{20,}/g,
  /sk-(?!ant-)[A-Za-z0-9]{20,}/g,
  /sk-proj-[A-Za-z0-9\-_]{20,}/g,
  /AKIA[0-9A-Z]{16}/g,
  /AIza[0-9A-Za-z\-_]{35}/g,
  /ghp_[A-Za-z0-9]{36}/g,
  /xox[baprs]-[A-Za-z0-9-]{10,}/g,
  /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g,
  /Bearer\s+[A-Za-z0-9\-._~+/]{20,}=*/g,
];

const DATE_RE = /\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}\/\d{1,2}\/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})\b/g;

const STREET_SUFFIXES = "Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct|Way|Place|Pl|Terrace|Ter|Circle|Cir|Highway|Hwy|Square|Sq";
const ADDRESS_RE = new RegExp(
  `\\d{1,6}\\s+[A-Za-z0-9.-]+(?:\\s+[A-Za-z0-9.-]+){0,3}\\s+(?:${STREET_SUFFIXES})\\.?(?:\\s*,?\\s*(?:Apt|Suite|Ste|Unit|#)\\.?\\s*\\w+)?`,
  "g"
);

const NAME_STOPWORDS = new Set([
  "The", "This", "That", "These", "Those", "Please", "Thanks", "Thank",
  "Hello", "Hi", "Dear", "Regards", "Sincerely", "Best", "Monday",
  "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
  "January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December", "I", "AI",
  "API", "URL", "Inc", "LLC", "Ltd",
]);
const NAME_RE = /\b(?:[A-Z][a-z]+(?:'[A-Za-z]+)?\.?)(?:\s+(?:[A-Z][a-z]+(?:'[A-Za-z]+)?\.?)){1,2}\b/g;

function luhnOk(digits) {
  let total = 0;
  const rev = digits.split("").reverse();
  for (let i = 0; i < rev.length; i++) {
    let d = parseInt(rev[i], 10);
    if (i % 2 === 1) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    total += d;
  }
  return total % 10 === 0;
}

function findAll(re, text, label, filter) {
  const out = [];
  let m;
  const r = new RegExp(re.source, re.flags.includes("g") ? re.flags : re.flags + "g");
  while ((m = r.exec(text)) !== null) {
    if (!filter || filter(m)) {
      out.push({ start: m.index, end: m.index + m[0].length, value: m[0], label });
    }
    if (m[0].length === 0) r.lastIndex++;
  }
  return out;
}

function findMatches(text) {
  let matches = [];
  for (const pat of API_KEY_PATTERNS) matches = matches.concat(findAll(pat, text, "APIKEY"));
  matches = matches.concat(findAll(SSN_RE, text, "SSN"));
  matches = matches.concat(
    findAll(CC_CANDIDATE_RE, text, "CREDITCARD", (m) => {
      const digits = m[0].replace(/[ -]/g, "");
      return digits.length >= 13 && digits.length <= 19 && luhnOk(digits);
    })
  );
  matches = matches.concat(findAll(EMAIL_RE, text, "EMAIL"));
  matches = matches.concat(findAll(IPV4_RE, text, "IP"));
  matches = matches.concat(
    findAll(PHONE_RE, text, "PHONE", (m) => {
      const digits = m[0].replace(/\D/g, "");
      return digits.length >= 10 && digits.length <= 15;
    })
  );
  matches = matches.concat(findAll(ADDRESS_RE, text, "ADDRESS"));
  matches = matches.concat(findAll(DATE_RE, text, "DATE"));
  matches = matches.concat(
    findAll(NAME_RE, text, "PERSON", (m) => {
      const firstWord = m[0].split(" ")[0].replace(/\.$/, "");
      return !NAME_STOPWORDS.has(firstWord);
    })
  );
  return matches;
}

const PLACEHOLDER_RE = /\[([A-Z]+)_(\d+)\]/g;

class Masker {
  constructor(options = {}) {
    this.placeholderFormat = options.placeholderFormat || ((label, n) => `[${label}_${n}]`);
  }

  mask(text, sessionMapping) {
    const allMatches = findMatches(text).sort((a, b) => a.start - b.start || b.end - a.end);
    const kept = [];
    let lastEnd = -1;
    for (const m of allMatches) {
      if (m.start >= lastEnd) {
        kept.push(m);
        lastEnd = m.end;
      }
    }

    const mapping = Object.assign({}, sessionMapping || {});
    const valueToPlaceholder = {};
    for (const [ph, val] of Object.entries(mapping)) valueToPlaceholder[val] = ph;
    const counters = {};
    for (const ph of Object.keys(mapping)) {
      const pm = /^\[([A-Z]+)_(\d+)\]$/.exec(ph);
      if (pm) counters[pm[1]] = Math.max(counters[pm[1]] || 0, parseInt(pm[2], 10));
    }

    let cursor = text.length;
    const parts = [];
    for (let i = kept.length - 1; i >= 0; i--) {
      const m = kept[i];
      parts.push(text.slice(m.end, cursor));
      let placeholder = valueToPlaceholder[m.value];
      if (!placeholder) {
        counters[m.label] = (counters[m.label] || 0) + 1;
        placeholder = this.placeholderFormat(m.label, counters[m.label]);
        mapping[placeholder] = m.value;
        valueToPlaceholder[m.value] = placeholder;
      }
      parts.push(placeholder);
      cursor = m.start;
    }
    parts.push(text.slice(0, cursor));

    return { maskedText: parts.reverse().join(""), mapping, matches: kept };
  }

  unmask(text, mapping) {
    return text.replace(PLACEHOLDER_RE, (full) => (full in mapping ? mapping[full] : full));
  }
}

module.exports = { Masker, findMatches };
