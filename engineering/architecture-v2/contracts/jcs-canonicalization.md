# Canonical Evidence Serialization

**Status:** Contract draft for G0 review.

Evidence digests are computed over the exact UTF-8 bytes produced by a JSON Canonicalization Scheme (JCS) implementation compatible with RFC 8785. Producers must canonicalize before hashing; consumers must recompute from the decoded semantic value and compare bytes/digest.

## Rules

- Objects are serialized with lexicographically sorted property names using the JCS UTF-16 ordering rule.
- No insignificant whitespace is emitted.
- Strings use JSON escaping; Unicode characters are emitted as UTF-8 unless JSON escaping is required by the JSON grammar.
- Numbers use ECMAScript-compatible shortest round-trip serialization; negative zero is `0`.
- Arrays preserve order.
- No duplicate object names are accepted.
- The canonical output is UTF-8 JSON followed by no implicit newline.
- Hash algorithm is SHA-256 over the canonical UTF-8 bytes; the transport representation is lowercase hexadecimal.

The repository must use a reviewed library implementation rather than a hand-rolled serializer. The vectors below are contract fixtures, not an implementation claim.
