# OpenCode V2 — G5-P9 R1.2.1 Human Owner Decision Record R1
## Limited Documentary Correction Adoption with Explicit Architecture-Decision Deferral

- **Decision ID:** `OC2-G5P9-R121-OWNER-DOC-ADOPTION-R1-20261103`
- **Decision date:** 2026-11-03 (JST)
- **Repository context:** `yohi/dotfiles-ai`
- **Fixed baseline HEAD (documentary identity only):** `cde7bc3d0e3b8812fb381aa05d248121382193c5`
- **Decision authority:** Human Owner — explicit approval in the current ChatGPT conversation, following receipt of the R1.2.1 independent static review
- **Decision class:** `OWNER_APPROVED / ADOPTED_WITH_LIMITATIONS / DOCUMENTARY_CORRECTION_ONLY`
- **Operational status:** `NO_IMPLEMENTATION / NO_RUNTIME / NO_ARCHITECTURE_ADOPTION / NO_GATE_RELEASE`
- **Storage status:** Locally generated decision artifact; **not** registered in GitHub or ChatGPT Library by this action

## 1. Owner Decision — Approved

The Human Owner **adopts only the documentary corrections contained in the byte-fixed G5-P9 R1.2.1 candidate**, within the boundaries approved for the F-001/F-002/F-003 targeted correction and evaluated in the subsequent independent limited semantic static review (`PASS_WITH_LIMITATIONS`).

**This is a limited documentary adoption, not adoption of the underlying G5-P9 architecture, root credential broker, normative contract, security gate, runtime evidence, or implementation.** Original candidate bytes are immutable; this new decision record does not edit or overwrite them.

The independent review found **Critical 0 / Major 0 / Minor 0 / Observation 1** (review-local) and accepted the scoped documentary delta. Its `PASS_WITH_LIMITATIONS` is a review verdict, not a runtime/security PASS.

## 2. Exact adopted scope

| Item | Approved documentary treatment | What is NOT approved |
|---|---|---|
| **F-001** `OC2-G5P9-R12-IR1-F-001` | The legacy architecture label `D` is separated into `D-CFA` and `D-HPX`, and final selection remains `OWNER_DECISION_REQUIRED` | No choice between architectures; no F-001 Finding Closure |
| **F-002** `OC2-G5P9-R12-IR1-F-002` | R1.2.1 trace for `G5P9-EV-REQ-018` cites B0-03/B0-08/B0-09, Host TCB / VM lifecycle, v0.49.2 version limits, and separates Cloudflare billing residual | No verified Host origin assertion, VM lifecycle control, in-flight billing cancellation, or runtime PASS |
| **F-003** `OC2-G5P9-R12-IR1-F-003` | R1.2.1 trace for `G5P9-EV-REQ-028/029` distinguishes Dynamic Routing, Auto Router, Provider Fallback, and retries with official documentary evidence | No verified Cloudflare Account routing configuration, absence of fallback, billing cap, or live policy enforcement |

The independently reviewed delta changed **one P9-OD-01 Choice cell, six D14 trace cells in three rows, and four provenance lines**. Document identity and all other bounded content were preserved: 67/67 row IDs/order, 603/603 nonedited cells, and other 64 rows × 11 columns = 704/704 matches. This record does not independently reperform the full semantic review; it relies on the identified independent review for that assessment.

## 3. Prior Human Owner decision remains effective

**Existing decision ID:** `G5-P9-OD-01-DEFERRED` (2026-11-03 JST, approved in the conversation).

Two statements **must be distinguished**:

1. **Already decided:** The Human Owner explicitly **defers** the final Architecture choice, without assigning the ambiguous legacy P9-OD-01 `D` to either candidate.
2. **Still undecided:** Whether to select `D-CFA`, `D-HPX`, or another option in a future authorized decision. `D-HPX` remains `UNVERIFIED` and is **not currently selectable**; `D-CFA` remains `CONDITIONALLY_FEASIBLE / NOT_ADOPTED`.

The R1.2.1 candidate's P9-D14 provenance statement “no decision ... was made” is interpreted narrowly as **no final Architecture selection was made during the correction task**. It does **not** negate the separate, previously approved **deferral decision**. This Owner Record is the explicit documentary bridge; it does not retroactively insert the decision ID into the fixed R1.2.1 source.

The `OWNER_DECISION_REQUIRED` marker in R1.2.1 remains in effect **for the future final choice**, not for reapproving the deferral itself.

## 4. Observation and Finding disposition

**New review Observation:** `OC2-G5P9-R121-IR1-F-001` — `Observation / OPEN_REVIEW_LOCAL / NOT_ADOPTED` (as a formal repository finding).

- **Issue:** R1.2.1 lacks the explicit `G5-P9-OD-01-DEFERRED` ID; provenance phrasing may imply that even the deferral itself has not occurred.
- **Owner response:** Observation **acknowledged and addressed by this separate decision record's clarification**, without modifying the R1.2.1 source text.
- **Status:** The review-local Observation **remains OPEN**. No Finding Closure, Severity change, Issue adoption or formal repository registration is claimed. A future separately authorized correction may incorporate the clarification in source if required; none is authorized here.

**Three earlier Minor Findings remain OPEN:**

- `OC2-G5P9-R12-IR1-F-001` — legacy D ambiguity; final Architecture selection not resolved.
- `OC2-G5P9-R12-IR1-F-002` — documentary correction accepted, but the Finding remains OPEN pending a separately authorized closure evaluation.
- `OC2-G5P9-R12-IR1-F-003` — documentary correction accepted, but the Finding remains OPEN pending a separately authorized closure evaluation.

The independent PASS and documentary adoption do **not** automatically close any Finding.

## 5. Maintained Architecture and Gate boundaries

| Subject | Mandatory retained status |
|---|---|
| G5-P7 independent security review | `REVISION_REQUIRED` / **14 Findings OPEN** |
| G5-P8 | `BLOCKED_INSUFFICIENT_EVIDENCE` |
| G5-P9 Caller Origin Authentication | `BLOCKED` |
| Architecture B / C1 | `DESIGN_PATH_REJECTED` |
| Architecture C2 Root Broker | `DESIGN_BLOCKED` |
| Architecture A | `CONDITIONALLY_FEASIBLE / NOT_ADOPTED` |
| Architecture D-CFA | `CONDITIONALLY_FEASIBLE / NOT_ADOPTED` |
| Architecture D-HPX / E | `UNVERIFIED` |
| G5-P7 / G5-P8 / G5-P9 as architectural / implementation stages | `NOT_ADOPTED / NOT_IMPLEMENTED` |
| R1.2.1 documentary correction only | `ADOPTED_WITH_LIMITATIONS` **by this Owner decision** |

The final row does **not** supersede the non-adopted design/Gate statuses of the preceding rows.

## 6. Fixed evidence identities

| Role | Fixed object | Bytes | SHA-256 |
|---|---|---:|---|
| Target candidate ZIP | `OC2_G5_P9_R121_F001_F002_F003_HANDOFF_20261103(1).zip` | 45,244 | `2f629be26f03a037e81cd7ab95a58c9167f374a9e6a6d143ed7dfd67ffcedeae` |
| Target R1.2.1 Markdown (ZIP member) | `OC2_G5_P9_R1_2_1_F001_F002_F003_TARGETED_DOCUMENTARY_CORRECTION_CANDIDATE_20261103.md` | 91,262 | `dac0f6d63fcffbd23ad56f5c326c5fd480ad82d60a3a692f6c2dc43371007ecd` |
| Independent review Handoff ZIP | `OC2_G5_P9_R121_FRESH_INDEPENDENT_SEMANTIC_STATIC_REVIEW_R1_HANDOFF_20261103(1).zip` | 22,941 | `3813e4addf66f595f0930f3f8653d7e283a55ff5700ce038f38306620210a9d9` |
| Independent review report (ZIP member) | `OC2_G5_P9_R121_FRESH_INDEPENDENT_SEMANTIC_STATIC_DELTA_REVIEW_R1_20261103_REPORT.md` | 15,060 | `703e97935c5fe01b010c5f8b601b0675c10eba8b9abb3bdae128bf5aabb48245` |
| Review verdict | Independent limited static review | — | `PASS_WITH_LIMITATIONS` |

Fixed baseline HEAD `cde7bc3d0e3b8812fb381aa05d248121382193c5` is a documentary reference, **not** a claim that the live GitHub branch was read or updated in this Owner action. Local ZIP files and named internal Markdown were read and SHA/CRC-checked for this record. Other original inputs and actual Host/Cloudflare runtime were not revalidated in this action.

## 7. Explicitly NOT authorized

No repository or GitHub writes; no Library save; no implementation, coding-agent execution, build/test/mock/runtime/host probe; no sandbox, network, systemd, TPM2, credential or token changes; no Cloudflare Gateway/Worker/Account modifications; no paid inference; no architecture selection; no F-001/002/003 or Observation Closure; no G5-P7 14-Finding Closure; no Requirement/Security Gate/HOLD release; no automatic subsequent task.

## 8. Authority, provenance, Handoff

- **Human Owner approval:** The current conversation's explicit 「承認します」 responding to the proposal to adopt R1.2.1 *as a limited documentary correction with the Observation separately recorded*.
- **Document status:** This is the locally created written record of that approval. It does **not** purport to be a GitHub-committed, externally countersigned, or separately Library-saved Owner Decision.
- **Source preservation:** R1.2.1 candidate and both input ZIPs remain byte-identical; this decision is a separate additional file.
- **Next authorized activity:** None automatically. Human Owner may later explicitly authorize archival/Library or GitHub registration, further evidence acquisition, further targeted documentary change, a separate Finding Closure review, or a later architecture decision.
- **Next assignee:** Human Owner for any new decision; **not Codex** and not an implementation agent under the current authority.
- **Delivery qualification:** File creation and local hash validation do not establish that the user's browser successfully downloaded the file.
