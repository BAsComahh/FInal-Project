# Project working agreements

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
