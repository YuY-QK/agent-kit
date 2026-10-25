---
name: ui-experience
description: Design or review screens, interaction flows, component states, visual hierarchy, motion, responsiveness, localisation and accessibility. Use it for UI proposals, prototypes and UI changes; don't use it for pure business-logic changes.
---

# UI and interaction

Make the interface represent what the product can really do, and keep it clear, operable and consistent across states, screen sizes and input conditions. If the global rules say the user has no design training, propose 2–3 visual directions with your reasoning and ask the user to choose.

## Get the context

- When the task touches product boundaries, remote capabilities or high-impact actions, read the necessary parts of the project rules and the PRD.
- When you need the target screen, look up the matching screen in the prototype document (screen numbers like P01) and separate what exists, what is targeted and what is a placeholder.
- Look at the existing theme, shared components and neighbouring screens and keep the established design language; if the project has a design-system document, it wins.
- Confirm the current UI from code and tests; don't infer from the prototype that something is implemented.

## Flows and states

First settle the user's goal, entry point, primary action, information priority, way back and completion feedback. According to the risk of the feature, check:

- Normal, loading, empty, failed and retry.
- Offline, disabled, permission denied and external capability unavailable.
- Progress, cancellation, interruption and recovery for long tasks.
- Repeated taps, quick switching, going back, the app moving to the background and data refreshes.
- Explanation and confirmation for high-impact actions such as delete, overwrite, purchase and upload.

Remote, payment or experimental capabilities that aren't connected must never appear successful; either hide the entry or show a real disabled/unavailable state that explains the condition.

## Visuals and accessibility

- Express priority with hierarchy, spacing, alignment and consistent action placement rather than piling on decoration.
- Compose existing components first; add a new component only when it will really be reused.
- Check small screens, enlarged system fonts, the keyboard, safe areas, scrolling, different aspect ratios and touch-target sizes.
- Colour, sound and motion must never be the only carrier of information; key controls need semantic labels and understandable reasons when disabled.
- Motion respects the system's reduce-motion setting and avoids rapid flashing; animation callbacks must not be the only source of business state.
- User-visible text is managed centrally (using the project's localisation approach), with attention to text length and wrapping across languages.

## Implementation boundaries

The UI layer only renders state and forwards actions. It doesn't access databases, files, the network or payments directly, parse protocols, or make business decisions.

## Output

Scaled to the task, describe: the user path, relevant states, reused or new components, handling of responsiveness/localisation/accessibility, how it is verified (component tests and manual visual checks), and any differences from the PRD or prototype. When the user only asked for a UI proposal or prototype, don't change business logic.
