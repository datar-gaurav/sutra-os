# Skill Audit Checklist

Run this periodically (monthly or after a significant agent usage period) against each skill.

## Routing quality
- [ ] Does the description start with "Load when"?
- [ ] Is the description ≤50 words?
- [ ] Is the trigger specific enough that it would NOT fire on a generic "help me" message?
- [ ] Is the trigger broad enough that it WOULD fire on the 3 most common user requests for this skill?
- [ ] Has this skill been routed at least once in the last 30 days? (if not: too narrow or not attached anywhere)
- [ ] Is this skill routed on >80% of turns for its attached agents? (if so: too broad — tighten the description)

## Body quality
- [ ] Does the body open with a one-sentence role statement (no banner)?
- [ ] Are the core rules still accurate? (APIs change, best practices evolve)
- [ ] Is the `## Gotchas` section populated with real issues encountered in production?
- [ ] Are any `{config_variable}` placeholders actually used in the body?
- [ ] Are reference files still accurate and up-to-date?

## Versioning
- [ ] Was `version` bumped when the description changed?
- [ ] Was `version` bumped when core rules changed significantly?

## Redundancy check
- [ ] Does this skill overlap significantly with another skill's description?
  - If yes: merge or tighten both descriptions to remove the overlap.
- [ ] Is there a simpler agent system-prompt tweak that would replace this skill?
  - If yes: consider deprecating.

## Deprecation criteria
Remove a skill if:
- It has not been routed in 60+ days despite being attached to active agents.
- Its functionality is now covered by a tool upgrade or base model capability.
- Its description cannot be made specific enough without breaking existing use cases.
