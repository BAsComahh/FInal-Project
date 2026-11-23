# Project working agreements

## Root documents and working context

The three core project records are `待澄清列表.md` (confirmed requirements and
open decisions), `TODO.md` (implementation status and remaining work), and
`项目思路.md` (design, assumptions and evidence). Keep their responsibilities
distinct and synchronize new decisions across the relevant records. Once user
answers have been integrated, retain their source through Git history rather
than maintaining a duplicate reply file.

The root files below are maintained project records. Preserve their
decisions, evidence and open questions during refactoring or cleanup; do not
treat them as disposable handoff notes just because a task is complete.

| File | Purpose and authority |
| --- | --- |
| `AGENTS.md` | Working agreements and required development practices. |
| `README.md` | Current capabilities, startup commands and module navigation. |
| `项目思路.md` | Design rationale, assumptions, algorithms, sources and experimental evidence for the dissertation. |
| `TODO.md` | Implementation status, remaining tasks and known issues; not a source of new approved requirements. |
| `待澄清列表.md` | Confirmed tracking-failure/recovery requirements, terminology and unresolved decisions; proposed answers remain unapproved. |
| `待人工确认.md` | Local verification checklist. Git-ignored; do not stage or commit it. |

Store new maintained documents and final reports in `docs/`, with their
supporting figures, data, and experiment archives in a topic folder. Keep the
root project records listed above in place. Reserve `outputs/` for temporary
or reproducible generated files. Archive any important result in `docs/`
before treating it as a maintained project artifact. The historical tracking
research and D35/I14 plan are archived in `docs/tracking/` and `docs/frontend/`.
Use the root records for current requirements, implementation and open checks.

Install Qt through the root `requirements.txt` in a new environment. Existing
installations can still load PySide6 from `outputs/ui_preview/deps`. The tracker
setup also uses `outputs/tracking_dependencies` and `outputs/model_cache`.
Check whether the current environment uses these directories before cleaning
`outputs/`.

The 2026-11-18 decision retires the OpenCV video client. Qt is the desktop
video client. Keep the existing video commands as Qt entry points and retain
the independent image and boundary tools. Terrain editing now belongs to
unlocked Registration (moved from Live on 2026-11-21).

Before substantial implementation, read this file and the relevant sections
of `项目思路.md` and `TODO.md`; inspect `git status` and the current diff before
editing. Consult the requirement and research records relevant to the task.
Use section-level reading when possible rather than loading every document
in full for each small change. Keep these records synchronized when their
requirements, implementation status or design changes. Remove temporary
handoffs only after retaining their lasting content in the appropriate record
and updating references. Commit or push only with explicit user authorization.

Use the confirmed decisions and terminology in `待澄清列表.md` as the current
requirement baseline for tracking failure and unit recovery. Open questions
and suggested answers are not approved requirements. New explicit user
decisions take precedence and must be synchronized into these documents;
do not silently replace a recorded decision with a conversational assumption.

## Runtime and operator workflows

Frontend workflow ownership and navigation are documented in
`frontend/README.md`. Keep the shared runtime independent of the displayed
tool; initial registration, board recalibration, scene editing and geometry
queries have separate controllers. Manual recovery now has its own controller
for the EdgeTAM backend. Single-search automatic recovery and candidate review
are integrated for EdgeTAM; what-if remains unimplemented.
Do not reopen initial registration or add placeholder flows.
Replay is authorized on 2026-11-07 as a separate read-only workflow: completed
movement and rotation each form a step, ordered by their geometry end time.
It replaces the visible live view while source playback, tracking and history
recording continue; returning live must show the latest data.
Opening replay selects the latest completed step; Refresh preserves the
currently selected event, including Step 0 (confirmed 2026-11-08).

The D33 audience window is a design target. It follows the operator's
Live/Replay/What-if mode automatically. Refer to D33 and TODO I13 for current
scope and outstanding design choices.

Qt in `frontend/qt` uses the public headless boundary in `application/app.py`.
Maintain one authoritative match state and serialize model operations.
Remove duplicate state, forwarding shells and speculative defensive branches
while preserving frame alignment, identity, cancellation/generation, isolated
recovery and history-write protections. The application and frontend READMEs
describe the public interfaces and workflow ownership.

The unit menu reference is `docs/ui-archive/unit-info-reference.png`. Keep the
vertical information card on the left and the semicircle menu on the right.
Display Distance on the measurement line and use the result drawer for LOS
and Move. Trays/T controls display visibility. Geometry queries use current
accepted trays regardless of this setting.

The later 2026-11-08 coordinate decision uses original video pixels as the
canonical spatial record. Keep source anchors, frame/size and calibration
provenance; derive rectified display coordinates and millimetre rule inputs
with the appropriate mapping. Compare both motion poses under the same metric
mapping. Recalibration alone does not interrupt an action when source mappings
are compatible; actual tracking/geometry loss still interrupts it. This assumes
the agreed stable camera. Legacy replay may reconstruct derived events read-only;
do not rewrite original observations or infer motion across real gaps.

The 2026-11-06 product target is continuous display and source playback for
all post-start workflows, including recovery, geometry tools and B08; a
stop-source fallback is not accepted. The 2026-11-08 implementation removes
HELD/Hold, updates geometry from live observations, and pumps rule/terrain
forms without blocking the main loop. B08 keeps playback active and assumes
a stable camera under the user's later 2026-11-08 decision; do not add camera
motion detection or automatic corner invalidation. New tracking is committed
only after isolated initialization succeeds;
cancelled results cannot replace the old session. The 2026-11-09 manual recovery
uses a SAM seed and an isolated Edge candidate, then a drag of the existing ID
confirms a targeted mask update. Original tracking/history/rules continue until
the drop; cancelling a draft leaves the original state unchanged. Only an
already-failed unit remains failed on cancellation. Clear/retry replaces temporal
prompt undo. Success clears only the target's old facing and interrupts only its
unfinished motion.
Confirmed update failures must not reset unrelated objects.
Automatic recovery searches once per newly failed instance. Only current Missing
references participate in identity conflicts; already unresolved IDs are not
silently retried. User-selected experimental defaults are cosine >= 0.85 and
runner-up margin >= 0.10, with no instance conflict or normal-mask overlap.
These are trial settings, not calibrated identity probabilities. A single
candidate without a measurable margin stays for review. Processing instances
remain internally failed but hidden from the human list; unsuccessful searches
appear in A/B. Correct confirms the current isolated candidate; No explicitly
starts one new search. Cross-frame rejected-candidate exclusion remains open.
Candidate propagation never writes valid history before acceptance. Recovery
errors must not reset unrelated objects or set global model_failed. B08, R and
close invalidate pending automatic results.
EdgeTAM is now the default propagation backend, initialized from SAM3's
registered masks; explicit SAM3 and Cutie selection remain available.

## SAM-related work

For all work involving SAM/SAM2/SAM3, verify the official approach before
choosing a design or changing implementation. This is an explicit user
requirement from 2026-10-27.

- Consult Meta's official documentation, examples and source code first.
- Also verify the documentation and source of the backend actually installed
  in this project (currently Hugging Face Transformers). Check its installed
  version; do not assume it exposes the same API as Meta's implementation.
- Prefer supported official APIs when they meet the requirement. Before
  introducing custom session management, replay, cache changes or workarounds,
  check the official prompt-editing and state-management mechanisms.
- Distinguish documented behavior, conclusions inferred from source, and our
  own implementation choices. Cite the relevant official sources when
  explaining a decision. Do not present our approach as an official requirement.
- If official guidance is absent or does not cover our case, state that and
  explain the implementation tradeoff before proceeding within the authorized
  task. This requirement does not add a routine user-approval step.

## Registration workflow

The 2026-11-14 follow-up authorizes loading completed registration archives for
repeat video checks. Restore original masks/IDs/catalog/calibration at the saved
registration frame, then initialize tracking through existing supported mask APIs.
Keep loaded registration locked, validate the matching video/frame, and publish
fresh references/history per test without changing the source archive. Loading
is an initial-session operation; an active match must be reset first.

Point registration and undo take place on the initial frame before the first
playback. Starting playback locks point editing, including while paused;
explicit reset starts a new registration. Later corrections belong to future
algorithms. Avoid implementing temporal prompt rollback for this workflow.

EdgeTAM manual recovery can correct a failed unit or a normally tracked unit
that the operator marks as a detection error. Correct only the selected
original unit ID and preserve its attributes, prior history, and unaffected
units. Keep initial registration locked and the table Homography intact.
Ambiguous instance matches require human assignment. Preserve each physical
unit's identity and history.

The input unit catalog supplies types only. Assigning type A to successive
masks generates A1, A2, etc.; each type has its own counter. Do not require
predeclared instance IDs or unit counts. Start model loading when the
registration program starts, rather than waiting for the first click.

Registration edits are drafts held in memory. Persist final references only
when the user finishes registration (S, or the first playback action). Commit
once per registration, then lock point and type editing. Undoing a draft unit
releases its instance number for reuse without renumbering other units.

## Design record for dissertation

Maintain `项目思路.md` in the project root for feature or algorithm updates.
Focus on how the project works: workflow, assumptions, algorithms, component
interfaces, relevant implementation details, tradeoffs, official sources and
meaningful experimental findings or limitations. Do not add code-review
reports, cleanup checklists, test-command logs or maintenance journals.
Record the intended design before substantial implementation and update it
to reflect the final implementation afterward. Distinguish proposed designs,
working implementations and measured accuracy; do not invent results.

## Verification

The project is exploratory. The user requested that we avoid spending effort
writing test files. Use focused inline checks and practical runs appropriate
to the change.

The main agent handles targeted reproductions, startup failures and local fix
checks directly. Module and practical video checks are allowed within the
agreed scope. Avoid proactive regression runs during implementation and
per-edit retesting cycles.
For GPU checks on this machine, explicitly select and verify the
AMD Radeon RX 7900 XT; another visible GPU is AMD Radeon(TM) Graphics.
Record the physical GPU name, not just a cuda index (HIP visibility filtering
can remap indices). Sandbox GPU kernel errors have not reproduced in approved
outside-sandbox runs on the RX 7900 XT; do not infer that the app is running on
CPU or that the driver is broken from the sandbox error alone. Label deliberate
CPU checks as such. Stop and notify the user before switching to desktop
computer use, and wait for their response before operating the desktop.
