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
| `追踪优化调研与执行计划.md` | Scoped tracking research, candidate approaches and experiment plans; dated findings and proposals must be checked against current code and later decisions. |
| `前端解耦重构计划.md` | D35 / I14 execution plan, interface boundaries, code-simplification requirements and acceptance checks; planned work is not completed functionality. |
| `待人工确认.md` | Local verification checklist. Git-ignored; do not stage or commit it. |

Store new maintained documents and final reports in `docs/`, with their
supporting figures, data, and experiment archives in a topic folder. Keep the
root project records listed above in place. Reserve `outputs/` for temporary
or reproducible generated files. Archive any important result in `docs/`
before treating it as a maintained project artifact.

The 2026-11-18 decision retires the OpenCV video client. Qt is the desktop
video client. Keep the existing video commands as Qt entry points and retain
the independent image and boundary tools. Move Terrain from Live into
Registration in a later task tracked in TODO.md.

Before substantial implementation, read this file and the relevant sections
of `项目思路.md` and `TODO.md`; inspect `git status` and the current diff before
editing. Consult the requirement and research records relevant to the task.
Use section-level reading when possible rather than loading every document
in full for each small change. Keep these records synchronized when their
requirements, implementation status or design changes. Remove temporary
handoffs only after retaining their lasting content in the appropriate record
and updating references.

Use the confirmed decisions and terminology in `待澄清列表.md` as the current
requirement baseline for tracking failure and unit recovery. Open questions
and suggested answers are not approved requirements. New explicit user
decisions take precedence and must be synchronized into these documents;
do not silently replace a recorded decision with a conversational assumption.

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

The 2026-11-10 D33 UI target is design-first: retain the existing operator
workflows and video-centered structure, redesign the interactions, and add a
separate clean audience window that automatically follows Live/Replay/What-if.
There is no manual publish/take step for mode changes. This remains a design
target (I13), not an implemented second window or what-if workflow. Review the
interaction sketches before choosing a UI framework or rebuilding the UI;
auxiliary-tool drafts and audience overlay policies still need design review.

The later 2026-11-10 D35 decision separates the application runtime before the
new UI. Follow `前端解耦重构计划.md` (I14): keep the existing UI as the first
client of a headless application boundary, preserve one authoritative match
state and serialize model operations. Simplify duplicate state, forwarding
shells and speculative defensive branches; retain frame alignment, identity,
cancellation/generation, isolated recovery and history-write protections.
The 2026-11-11 instruction explicitly starts I14 implementation in the current
working tree from checkpoint f08876d, preserving the uncommitted prototypes and
Qt-preview additions. The later instruction authorizes committing this phase
checkpoint and starting the Qt main-window/real-registration milestone.
Do not push or add test files. Keep later UI workflows outside this milestone.
The headless boundary now lives in application/app.py; frontend is its existing
client. Keep I14 open until its remaining acceptance checks are complete.
The Qt registration/basic-live client now lives in frontend/qt and uses the
same public application boundary. Keep the independent design preview intact.
The later 2026-11-11 instruction starts the Live console milestone: follow
design/ui/unit-radial-console.html for selection, fixed unit menus, read-only
unit information and the bottom query drawer. Keep source playback running
and use existing application geometry commands. Other operator workflows,
the audience window and What-if remain separate work.
The latest UI revision uses design/ui/live/unit-info-reference.png uniformly:
vertical information card on the left and semicircle menu on the right, with
whole-group bounds/scaling instead of alternate compact layouts. Distance
values belong on the current measurement line; Distance has no result drawer.
The later uncertainty UI decision moves mask/facing notices to a right-side
A/B list, separate from the unit card and video labels. Facing review lists
only suspicious, pending, failed or unknown items; ordinary recovery phase
tracking is not a persistent alert merely because its source is inferred.
Keep backend provenance/history/rule warnings and recovery thresholds intact.
The later tray optimization is authorized: gate stable masks using centroid
motion plus cheap shape/axis checks, reuse accepted geometry for noise, then
try local fitting before full fallback when refitting is required. Keep the
baseline at the last actual fit so slow motion accumulates. Never reuse across
identity/calibration/size changes, reset, missing masks or recovery targets.

The 2026-11-13 follow-up authorizes Qt migration of existing recovery review,
manual correction, B08 recalibration, unit/terrain editing and replay. Add a
red correction action to the unit menu using isolated recovery of the original
ID. Keep playback/history running. Audience/What-if remain TODO. Tray refit
frequency/latency and ineffective automatic recovery are high-priority issues.
The later 2026-11-13 P0 decision authorizes a 5% centroid-motion gate and exact
image-space mask IoU (retain 0.90), removing independent area, normalized-shape
and axis gates. Keep the last actual successful/failed attempt's mask baseline;
failed fits wait for accumulated mask change rather than retrying unchanged masks.
Use bounded asynchronous CPU tray batches, keep all model operations serial,
and retain separate mask/geometry times, same-frame geometry queries, original-frame
history and invalidation across tracking gaps, recovery, identity and calibration.
Record the removed gates for rollback. The user will run this milestone's practical
checks; do not delegate acceptance or add test files for it.

The 2026-11-16 decision restores the Trays/T switch to display visibility
only (superseding the 2026-11-14 pause/snapshot-Distance exception now that
async CPU tray batches and three-layer overlay rendering resolved GUI stutter).
Background tray fitting continues uninterrupted when Trays is hidden, and
Distance/LOS/Move queries always run continuously against accepted trays
without one-shot snapshot fitting or "Not implemented" placeholders.
The latest 2026-11-14 decision retains facing implementation but disables its
runtime use by default: no DVMNet loading/checks/recovery or directed-front
continuity updates. Keep initial registration evidence; do not carry it as live
facing. Hide Missing and facing attention notices without changing internal
failure, automatic recovery, identity or query-validity protections.

The 2026-11-11 D36 follow-up separately authorized a minimal registration-only
Qt preview and accepted its feasibility. Keep it isolated in
`design/ui/registration`; it uses saved masks and sample catalogs without SAM,
reference export or production-session changes. PySide6/Qt Quick is the UI
technology direction. The preview itself did not start I14; the later explicit
instruction above starts decoupling, without a full UI migration. Native desktop interaction still requires notification and a reply.

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
unfinished motion; a separate D32 appearance estimate may select its new front.
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

The 2026-11-10 D32 trial uses DVMNet only to select a current tray front edge;
the rectangle supplies the exact angle. Both initial-F reference and current
query use source-frame masks with mean RGB background. References freeze only
after successful registration; no initial F means no inferred front. The
image-plane projection and configurable 20-degree candidate-error margin are
experimental, not calibrated confidence. Normal updates now use rectangle
continuity plus a cheap foreground check; DVMNet runs only for suspicious or
missing facing, and after accepted mask recovery. Direction-only suspicion
and failed recovery retain the previous Estimated front with pending/failed
provenance; actual tracking loss still invalidates old facing under D22.
Retries require changed appearance and a configurable minimum source-time gap.
Detector templates are runtime-only; commit proposed detector state only after
the corresponding observation is accepted. Facing-only recovery must not
replace masks/IDs or interrupt valid position actions. Model errors must not
fail tracking globally. R clears
references; B08 retains compatible source references. H03 still detects
undirected tray-axis rotation, not directed 180-degree facing changes.
External pinned assets stay in ignored cache, prepared by tools.setup_facing.

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

The scoped recovery workflow confirmed on 2026-11-02 is separate from initial
registration: reuse its UI only for failed existing instances, retain their
IDs and attributes, and preserve unaffected units. It does not reopen global
point/type editing, create replacement instance IDs, or change the table
Homography. This manual session integration is implemented for EdgeTAM; other propagation
backends retain their existing workflows.
The 2026-11-06 manual-intervention requirement also allows the operator to
mark a tracked instance as a detection error and request scoped manual
recovery directly. It does not allow silently taking another assigned unit's
identity. Ambiguous instance matches require human assignment, even with
high appearance similarity; never randomly swap physical IDs or histories.

The input unit catalog supplies types only. Assigning type A to successive
masks generates A1, A2, etc.; each type has its own counter. Do not require
predeclared instance IDs or unit counts. Start model loading when the
registration program starts, rather than waiting for the first click.

Registration edits are drafts held in memory. Persist final references only
when the user finishes registration (S, or the first playback action). Commit
once per registration, then lock point and type editing. Undoing a draft unit
releases its instance number for reuse without renumbering other units.

The 2026-11-13 registration decision defers tray fitting until type assignment
confirms the current mask. Point edits/undo invalidate only that object's tray;
binding/refitting must preserve all other accepted trays. Reconfirm the type after
editing a bound mask. Registration and Live share update_trays with an explicit
target set; per-object versions reject stale registration fits.

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

The user authorized assistant-run module and practical video checks on
2026-11-02. The later 2026-11-11 instruction limits the default cadence:
do not proactively run regressions or tests during implementation. Complete
an agreed implementation milestone first, then batch its acceptance work to
GPT-6.1 Terra with medium reasoning and an independent context. Under the
latest 2026-11-11 follow-up, the main agent directly handles small targeted
reproductions, startup failures and local fix checks using its existing
context; do not delegate these by default. This supersedes the earlier
Terra-low preference for small checks and does not expand proactive testing.
For delegated milestone acceptance, give Terra acceptance criteria, public
entry points and necessary project constraints,
without implementation explanations or suspected fault locations. It reports
reproduced failures with steps/evidence and concise coverage counts; the main
agent independently locates and fixes code. Do not start per-edit retesting
cycles; include fixes in the next agreed batch unless the user requests an
earlier check. This does not authorize new test files or desktop interaction.
For GPU checks on this machine, explicitly select and verify the
AMD Radeon RX 7900 XT; another visible GPU is AMD Radeon(TM) Graphics.
Record the physical GPU name, not just a cuda index (HIP visibility filtering
can remap indices). Sandbox GPU kernel errors have not reproduced in approved
outside-sandbox runs on the RX 7900 XT; do not infer that the app is running on
CPU or that the driver is broken from the sandbox error alone. Label deliberate
CPU checks as such. Stop and notify the user before switching to desktop
computer use, and wait for their response before operating the desktop.
