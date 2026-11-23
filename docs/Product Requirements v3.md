## Before the game

### Board detection and calibration

- Use corner and edge or line detection to propose the board boundary, then obtain user confirmation. Harris corner detection provides image-point candidates; the correspondences with the physical board still need to be established. **Source:** [Harris and Stephens](https://www.bmva-archive.org.uk/bmvc/1988/avc-88-023.html).
- Obtain the board's real length and width from user input, with a configurable default of 48 × 72 inches. This is a project default. Use these dimensions with the confirmed board points to establish board-plane coordinates in physical units. **Source:** [A Plane Measuring Device](https://robots.ox.ac.uk/~vgg/publications/1997/Criminisi97/).
- Calculate a homography from the confirmed correspondences and map suitable image positions to board-plane coordinates. **Source:** [Homography-based perspective correction](https://www.mdpi.com/1424-8220/25/6/1891).
- If automatic detection fails, allow manual selection of the four board corners. Snapping to nearby detected corners should be adjustable and reversible.
- Periodically check for substantial changes in the camera-to-board relationship, using board reference points where available. Provide a manual recalibration control to confirm the board points and restore the image-to-physical-coordinate mapping.

### Configurable unit and terrain records

Provide configurable sets of initial attributes and dynamic state fields for unit registration.

- The initial Kings of War profile configuration includes type, Melee, Shooting, Defence, Attacks, Nerve, Points, Special Rules, Traits, army or side, ranged weapons, spells and selected options or artefacts.
- Optional attributes control the availability of related tools:
	- Height is enabled by default and enables the LOS tool.
	- Speed is enabled by default and enables movement-range calculation using the supported orders and rules.
	- A configurable Range field can enable a generic range calculation; it is not a default field in the Kings of War configuration.
- Default dynamic fields include Damage, Wavering, Devastated, Engaged, Routed, temporary effects and current order. 
	- The mechanism for updating these fields remains to be designed.
- Tracking records include ID, name or type, army or side, base dimensions, facing, history, visibility, confidence, box or mask, local history.
- Terrain and obstacle records include a label or type, an annotated board-plane region and relevant movement or LOS properties. Height is an optional property.

### Unit registration

- SAM 3 segmentation: **Source:** [SAM 3](https://proceedings.iclr.cc/paper_files/paper/2026/hash/e0982cbc81401df3430ee1ff780dc7a2-Abstract-Conference.html)
	- with a text prompt such as "miniature" to propose initial masks or boxes. The user confirms the intended unit boundary and assigns its label.
	- with point prompts for directly identifying a unit or correcting its segmentation. 
	- Register terrain and obstacles separately from units.
- Provide box-prompted segmentation and manual target-box selection to resolve overlapping candidates or identify missed units.
- Use available army-list information to suggest unit configuration. Base dimensions should be derived from the unit type and formation size where available, with user confirmation and overrides for exceptions. 
	- An optional PDF or text import interface may populate these configuration fields.
- Treat dice, rulers, clocks and other loose objects as clutter. 
	- Adding them as appearance negatives is optional.
	- they should not automatically become terrain obstacles or units.
- Warns:
	- Several units may share a type and appearance reference while retaining distinct identities.
	- Dimensions can be used to constrain geometric estimation and compatible matches.
	- Automatic recovery of facing remains an estimation problem.

### Appearance references

- Use a pretrained DINOv2 encoder to extract feature vectors from those crops. In the initial baseline **Source:** [DINOv2](https://arxiv.org/abs/2304.07193).
- Start with one clear reference per unit type.
	- Several units may share that type reference for type recognition.
	- Add further views, potentially including four orientations, only if needed to improve performance.
	- The gallery may grow through confirmed observations during play.
- Reference update policy:
	- Only clear observations with confirmed identities and suitable reference quality should extend the appearance gallery.
	- Preserve the original references to reduce the risk of reinforcing mistaken matches. The timing and selection policy for gallery updates remain to be evaluated.
	- Requires testing before conclusion
- Optional adaptation before a game may be investigated after establishing the frozen-encoder baseline. Evaluate any small classifier or feature-mapping module on later images excluded from registration and training, recording preparation time and any performance benefit. **Related work:** [TCG-AR](https://arxiv.org/pdf/2607.02090v1).

### Deferred exploration: 3D unit models

Creating a 3D model for each unit is deferred because of its acquisition and processing cost. If multi-view capture later becomes necessary for appearance matching, its possible use for reconstruction can be reconsidered. Any tracking benefit would require evaluation.

Possible references include [MASt3R](https://github.com/naver/mast3r), [ReconViaGen](https://github.com/GAP-LAB-CUHK-SZ/ReconViaGen) and [GTR](https://arxiv.org/html/2505.11905v1).

## During the game

### Unit tracking and identity maintenance

Track registered units and maintain their labels as positions change. Candidate approaches are:

1. **Segmentation and appearance association:** generate SAM 3 candidate regions, compare their DINOv2 features with the registered references, and associate observations across time. Following loss, regenerate candidates across the board before attempting appearance-based recovery. **Related work:** [CNOS](https://openaccess.thecvf.com/content/ICCV2023W/R6D/papers/Nguyen_CNOS_A_Strong_Baseline_for_CAD-Based_Novel_Object_Segmentation_ICCVW_2023_paper.pdf).
2. **Dense feature matching:** investigate whether local DINOv2 features can locate registered units directly in the frame. This requires an additional localisation mechanism; reference-vector similarity alone does not produce a box or mask.
3. **A lightweight tracking baseline:** try KCF for visible, continuous movement and measure its failures during rotation, hand occlusion and relocation. **References:** [KCF/CSRT tutorial](https://www.youtube.com/watch?v=8ckWnXfwpvw&t=2s); [Summoner Wars Gameplay Detection](https://github.com/jakubradziejewski/gameplay_event_detection).

Select the final approach through small video experiments. The software may update confirmed positions after a unit becomes visible and settles.

### Unit recovery

- Combine appearance, board position, size and available facing information. 
- When the active-unit roster and existing matches are reliable, restrict appearance comparisons to eligible unmatched or missing units. For example, if only units of types A, B and C are unaccounted for, compare candidates with those references. 
- Hungarian algorithm assignment may support one-to-one association, while allowing unmatched observations and uncertain identities. 

### Tray footprint and facing estimation

- Distinguish the visible unit mask from the tray's occupied region on the board plane. Figures above the board can change the visible outline without changing the base footprint.
	- A candidate method is to fit a translated and rotated rectangle of the registered dimensions to the observed unit region, maximising their overlap. Its geometric accuracy requires evaluation.
	- Rectangle fitting alone cannot distinguish front from rear, because a 180-degree rotation leaves the rectangle unchanged. 
	- the automatic method remains open.

### Interactive overlays and geometric tools

- Allow the commentator to show or hide the overlay and select units directly in the video. Once unit selected:
	- Highlight + zoom and display its detailed information
	- Show its latest displacement to support commentary.
	- (**Optional**) show all reachable units/ show all units inside the attack range
- Display unit outlines or boxes, names and relevant registered information. Different sides may use distinct colours.
- Provide separate visibility control layers for units, names, terrain, obstacles and movement ranges.
- Terrain overlays may remain non-selectable during commentary..
- Selecting two units displays a connecting line between their closest base points and the numerical distance in physical units.
	- Use the shortest distance between their board-plane footprints. For disjoint rectangular footprints, this can be computed from the minimum corner-to-edge distances in both directions. 

#### Movement ranges

Selecting a unit should display movement ranges obtained by evaluating the results of its supported movement orders.
- Enumerate or sample the permitted translations and pivots for each order, combining registered movement attributes with terrain, other unit footprints and the applicable rules.
- Keep the tray reference point for distance calculation consistent between the start and end.
- For an ordinary Kings of War unit with Speed S:
	- Advance permits forward movement up to S inches and up to two pivots of at most 90 degrees each.
	- At the Double permits forward movement up to 2S inches and one pivot of at most 90 degrees.
	- Back permits backward movement up to S/2 inches and one pivot of at most 90 degrees.
	- Sidestep permits sideways movement up to S/2 inches and one pivot of at most 90 degrees.
- Account for the registered terrain categories:
	- **Blocking Terrain:** translational movement must go around it. 
	- **Difficult Terrain:** ordinary movement may enter or cross it; At the Double treats it as Blocking Terrain unless an applicable exception, such as Pathfinder, allows passage.
	- **Obstacles:** ordinary movement may cross or end on them; At the Double treats them as Blocking Terrain. Their rule Height is 1. 
	- Others...
	- If Charge is included in the supported orders, account for Hindered status and relevant special-rule exceptions.
- If finite sampling is used, present the resulting region as an estimate. 

#### Basic LOS

- Selecting two units displays a simplified LOS estimate using board-plane geometry, facing, annotated terrain regions and registered Height information. 
- Show the result as clear, blocked or uncertain. 
- Height must be supplied during registration to enable this tool.

#### Hypothetical layouts

- Provide a what-if mode in which the commentator can freely move virtual unit copies and interact with the resulting layout. 
- Allow the commentator to recall the perform by pressing "ctrl + z".
- Allow the commentator to leave this mode and return to the live state at any time. 
- Hypothetical edits must remain separate from confirmed observations and will not be recorded as game history.

### Movement history and unit removal

- If a registered unit cannot be located, retain its ID and last confirmed position and mark it as missing or uncertain. 
- Recovery may be deferred while a relevant occluder covers it. Attempt recovery when no relevant occlusion is detected or suitable observations become available.
- request manual confirmation if recovery fails. Add new reference to the gallery after manual correction.
- **QUESTION**: plan to calculate the dynamic attributes to decide whether the unit is removed (routed). But requires commentor to perform attack action for each unit during the game. 
	- Or simply add a remove bottom. 

### Replay controls

- Maintain a global history locally or in RAM, with format \[step, target ID, target local history] (can improve it later)
- Provide a replay button that reveals a timeline slider for revisiting earlier game states and reconstruct the digital board from those records.
- Use interpolation to animate between recorded states.
- Where feasible, provide play, pause and playback-speed controls.
- Also, can be controlled by pressing "left" & "right" (previous or next move) 
- Keep historical playback separate from the current live state and hypothetical editing, and allow a return to the live state (esc).

## When detection or tracking is wrong

- Allow the user to select an affected unit and adjust its box or mask, or identify it at a new location.
- Update that unit's existing record while preserving its ID, type, history and confirmed references.
- Add a corrected observation to the gallery only after its identity and suitability as a reference have been confirmed.
- Evaluate when gallery updates should occur; a point-prompt correction does not automatically require a new gallery entry.
- Use the active-unit roster and confirmed one-to-one matches to resolve identity ambiguity. If only one eligible unit remains, assign its ID to a valid unmatched candidate. Retain an unknown identity when the roster, existing matches or candidate validity is uncertain.
- If the camera-to-board relationship changes, use the recalibration controls to restore a valid coordinate mapping.

## Testing

- Vision and identity, Geometry, Commentary tasks 
