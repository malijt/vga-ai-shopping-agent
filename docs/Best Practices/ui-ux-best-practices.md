# UI/UX Best Practices

A rule set for UI/UX design work — usability, information architecture, interaction design, and design systems. Paste relevant sections into your agent's instructions (`CLAUDE.md`, `.cursorrules`, system prompt, etc.) so it defaults to these patterns without needing a reminder every time. Complements `frontend-best-practices.md`, which covers the engineering side of building these interfaces.

## 1. Foundational Usability Principles
- Keep the user informed of system status at all times — loading, saved, error, in-progress — never leave them guessing what's happening.
- Match the product's language and concepts to the user's real-world vocabulary and mental models, not internal system terminology.
- Give users an easy way out of any flow (cancel, back, undo) rather than trapping them in a path they didn't intend to start.
- Stay consistent — the same action should look and behave the same way everywhere in the product, so users can apply what they've already learned.
- Prevent errors through design (disable invalid actions, confirm risky ones) rather than relying only on error messages after the fact.
- Favor recognition over recall — show options and context rather than making users remember information from a previous screen.
- Design for both efficiency and flexibility — simple by default for new users, with shortcuts or power-user paths for experienced ones.
- Keep visual design minimal and purposeful; every element on screen should earn its place, and anything that doesn't support the user's current task should go.
- When something goes wrong, help users recognize, understand, and recover from the error in plain language, not an error code.

## 2. Information Architecture & Navigation
- Organize content around users' mental models — how they think about the content — not your internal org chart or database schema.
- Keep primary navigation shallow and predictable; if common destinations take more than a few clicks to reach, the structure needs rethinking.
- Use breadcrumbs or clear location indicators for any deep hierarchy, so users always know where they are and how to get back.
- Support both browsing and search as complementary paths — some users know exactly what they want, others are exploring.
- Keep navigation placement and behavior consistent across the whole product; don't relocate the same controls between sections.
- Scale navigation complexity to the product itself — a simple utility should never make users hunt through menus for its one core action, while a genuinely complex product (multiple workflows, several user roles) needs deliberate wayfinding (persistent context, clear back paths, progress indicators) so depth doesn't turn into users getting lost.
- Validate structure with real users (card sorting, tree testing) rather than assuming your categorization is obvious to everyone else.

## 3. Visual Design & Hierarchy
- Establish a clear visual hierarchy so the eye lands on the most important thing first, then secondary and tertiary content in order.
- Use size, weight, color, and spacing — not color alone — to distinguish primary actions from secondary ones.
- Treat whitespace as an active design tool that groups related content and gives important elements room to stand out, not empty space to fill in.
- Limit the palette and type scale to a small, deliberate set of options rather than accumulating one-off colors and sizes screen by screen.
- Group related elements by proximity, similarity, and alignment so they read as a set without needing an explicit border around everything.
- Maintain sufficient contrast between text and background, and between interactive elements and their surroundings.

## 4. Avoiding Generic ("AI-Slop") Design
- Make deliberate choices tied to this specific product and audience — if a design could be dropped into any other product's brief unchanged, that's a signal to revisit it, not a sign it's safe.
- Watch for the specific visual signatures that now read as generic/templated: warm cream backgrounds paired with a high-contrast serif and a terracotta accent; near-black backgrounds with a single neon or acid-green accent; broadsheet-style layouts with hairline rules and zero border-radius everywhere. None of these are wrong in principle, but reaching for one without a reason tied to the brief is a tell.
- Use one dedicated, consistent icon set across the whole product — one library, one stroke weight, one style — instead of mixing icon packs, emoji, and stock glyphs.
- Add an icon only where it encodes real meaning (a status, an action, a category), not on every heading or card "because it looks nice" — decoration dressed up as information is still decoration.
- Choose typography and color as a deliberate pair tied to the brand and subject, not the first rounded sans-serif and gradient that comes to mind. Present 2–3 distinct direction options (a palette plus a type pairing) to stakeholders and let them choose, rather than silently shipping the safest default.
- Keep the palette small and deliberate (roughly 4–6 named colors) — every color in the system should have a reason to be there, not just exist because a gradient generator produced it.
- Treat motion and depth — parallax, scroll-triggered reveals, 3D, glassmorphism — as a real design decision to raise explicitly with the product owner. Ask whether the product and brand actually call for it, rather than defaulting to either a flat static page or effects piled on out of habit.
- If motion/depth effects are used, spend that budget on one deliberate, well-executed signature moment rather than scattering several at once — stacking parallax and 3D and glassmorphism together is itself a recognizable templated-AI tell, and paradoxically reads as less distinctive, not more.
- Apply restraint as a final check before shipping: find one decoration, animation, or flourish that could be cut without losing anything, and cut it.

## 5. Interaction Design & Feedback
- Give immediate, visible feedback for every user action — a click, tap, or submit should never leave the user wondering if it registered.
- Make interactive elements look interactive: buttons look pressable, links look like links, disabled states look disabled.
- Minimize the steps required for common, high-frequency tasks; audit any flow that takes more than a few steps for its most typical case.
- Require confirmation for destructive or hard-to-reverse actions, and offer undo wherever feasible instead of relying only on "are you sure?" dialogs.
- Use progressive disclosure — show what's needed for the current step and reveal advanced options only when relevant, instead of front-loading every choice at once.
- Keep response times fast, and use skeleton screens or progress indicators for anything that isn't near-instant so waiting feels shorter and less uncertain.

## 6. Forms & Input Design
- Ask for only the information you actually need right now — every additional field is a reason to abandon the form.
- Group related fields together and order them the way users naturally think about them, not your database schema's column order.
- Validate inline, as close to the field as possible, with specific messages ("Enter a valid email address") instead of a generic "Invalid input" at the top.
- Use the right control for the data — a date picker for dates, a stepper for quantities — instead of a free-text field for everything.
- Pre-fill smart defaults and remember previous input where possible, so users aren't re-entering information the system already has.
- Never clear a form, or its already-valid fields, because of one validation error elsewhere.

## 7. Accessibility & Inclusive Design
- Design for a range of abilities from the first draft, not as a retrofit after the "real" design is done.
- Never use color as the only way to convey meaning (error, status, category) — pair it with an icon, label, or pattern.
- Choose a palette with sufficient contrast built in, rather than designing first and running a contrast checker as an afterthought.
- Design touch targets large enough for reliable use (roughly 44×44pt minimum) with enough spacing that adjacent targets aren't mis-tapped.
- Design layouts that hold up under text resizing and zoom, for users who increase font size or use screen magnification.
- Design with keyboard-only and screen-reader use in mind — a logical reading/tab order, clear focus states, and meaningful labels for icons and images.

## 8. Responsive & Cross-Device Design
- Design mobile-first, then progressively add complexity and density for larger screens, rather than shrinking a desktop design down.
- Design touch interactions for mobile specifically — don't just scale down hover-dependent desktop patterns that have no touch equivalent.
- Check designs at real breakpoints, not just one "designed" size and one "mobile" size with everything in between assumed to work.
- Account for context of use: mobile users are often on the go with partial attention, so critical actions should need less precision and fewer steps than a desktop equivalent might.

## 9. Design Systems & Consistency
- Build and maintain a shared design system (components, tokens, patterns) instead of designing each screen from scratch.
- Reuse established patterns for common needs (date pickers, modals, tables) rather than inventing a new one per feature.
- Keep terminology, iconography, and interaction patterns consistent across the whole product, not just within one team's section of it.
- Document the reasoning behind a pattern, not just the pattern itself, so the next designer knows when it does and doesn't apply.
- Version the design system deliberately, and communicate breaking changes to it the same way you would for a shared code library.

## 10. User Research & Validation
- Validate designs with real, representative users through usability testing, not just internal team review.
- Test early with low-fidelity prototypes, before investing in high-fidelity visuals or working code, so major direction problems are cheap to fix.
- Use behavioral data (analytics, session recordings, heatmaps) alongside qualitative research — what users say and what they actually do often diverge.
- Treat the first design as a hypothesis, not a final answer, and plan to iterate based on what testing and real usage reveal.
- Test with people who reflect the range of your actual users (ability, device, familiarity with the product), not just people who look like your team.

## 11. Error, Empty & Edge-Case States
- Design every state a screen can be in — first-use empty state, no-results, error, loading — not just the ideal, fully-populated happy path.
- Write error messages in plain language that explain what happened and what the user can do next, not a technical code or stack trace.
- Design empty states to guide the user toward a next action ("create your first project") rather than showing a blank, dead-end screen.
- Prevent errors by design wherever possible (disable an action until its prerequisites are met) instead of only handling them after they occur.
- Design for content extremes — very long names, missing fields, unusually large numbers — not just the tidy example data used in mockups.

## 12. Onboarding & First-Time Experience
- Treat "should this product have a guided onboarding tour at all" as an explicit question to raise, not a default yes — a simple, self-explanatory product often needs none, while a feature-dense product or one built on an unfamiliar paradigm usually does. Decide based on actual product complexity, not habit.
- Get users to real value as quickly as possible; don't front-load a full feature tour before they've done anything meaningful.
- Make onboarding skippable or dismissible for returning users and anyone who wants to explore on their own.
- Prefer contextual, just-in-time guidance (a tooltip when a feature first appears) over one big upfront tutorial covering everything at once.
- Set accurate expectations during signup/setup about what's required and how long it will take, so users aren't surprised partway through.

## 13. Content & Microcopy
- Write UI text in plain, specific, actionable language — a button should say what it does ("Save changes"), not something vague ("OK").
- Use consistent terminology for the same concept everywhere in the product; don't call the same thing "Account" in one place and "Profile" in another.
- Write for scannability — short sentences, clear labels, and structure — since most users skim interface text rather than reading it closely.
- Match tone to context: reassuring and clear for errors and confirmations, concise and direct for labels and instructions.

## 14. Design Documentation & Developer Handoff
- Annotate designs with the specs developers actually need — spacing, states, breakpoints — instead of leaving them to infer values from a static image.
- Document every interactive state of a component (default, hover, focus, active, disabled, error, loading), not just its default appearance.
- Keep one source of truth for design files, with clear versioning, instead of multiple stale copies circulating across the team.
- Do a design QA pass after implementation to catch drift between the design and what actually shipped, and treat the gaps as bugs, not nitpicks.
