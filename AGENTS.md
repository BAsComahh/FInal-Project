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
| `待人工确认.md` | Local verification checklist. Git-ignored; do not stage or commit it. |

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
queries have separate controllers. Recovery and what-if are still
unimplemented; do not add placeholder flows or reopen registration for them.
Replay is authorized on 2026-11-07 as a separate read-only workflow: completed
movement and rotation each form a step, ordered by their geometry end time.
It replaces the visible live view while source playback, tracking and history
recording continue; returning live must show the latest data.

The 2026-11-06 product target is continuous display and source playback for
all post-start workflows, including recovery, geometry tools and B08; a
stop-source fallback is not currently accepted. Existing HELD queries and
B08's paused transaction do not yet meet this target. Keep current behavior
distinct from the pending redesign; resolve the relevant CL questions first.
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

Point registration and undo take place on the initial frame before the first
playback. Starting playback locks point editing, including while paused;
explicit reset starts a new registration. Later corrections belong to future
algorithms. Avoid implementing temporal prompt rollback for this workflow.

The scoped recovery workflow confirmed on 2026-11-02 is separate from initial
registration: reuse its UI only for failed existing instances, retain their
IDs and attributes, and preserve unaffected units. It does not reopen global
point/type editing, create replacement instance IDs, or change the table
Homography. Recovery session integration is still pending, not implemented.
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
2026-11-02. For GPU checks on this machine, explicitly select and verify the
AMD Radeon RX 7900 XT; another visible GPU is AMD Radeon(TM) Graphics.
Record the physical GPU name, not just a cuda index (HIP visibility filtering
can remap indices). Sandbox GPU kernel errors have not reproduced in approved
outside-sandbox runs on the RX 7900 XT; do not infer that the app is running on
CPU or that the driver is broken from the sandbox error alone. Label deliberate
CPU checks as such. Stop and notify the user before switching to desktop
computer use, and wait for their response before operating the desktop.
