# Learner preferences

Teacher separates **deployment/runtime settings** from **learner-owned behavior preferences**.

Deployment settings remain environment-backed and include provider endpoints, API keys, database location, embedding configuration, timezone, and legacy proactive thresholds used before a learner establishes a preference profile.

Learner preferences are persisted by Core in SQLite and are read or changed through Core APIs. The Textual UI does not write the preference table directly.

## First-run onboarding

On first run, Teacher offers a lightweight, non-blocking onboarding panel. The learner can choose correction detail and proactive reminder cadence in human terms, or choose **Use defaults** / **Skip**. Ordinary conversation remains available while the offer is visible.

The automatic offer is persisted so it is not repeatedly shown after restart. `/preferences onboard` can explicitly reopen onboarding later without erasing an already-established policy.

## Persisted preferences

The profile currently contains:

- correction style: `light`, `normal`, `intensive`
- proactive cadence: `rare`, `normal`, `frequent`
- optional active hours and quiet hours in the configured local timezone
- practice balance: prefer review, balanced, or prefer conversation
- sound preference for future proactive audio support

Use `/preferences` to inspect the current profile, `/preferences set NAME VALUE` for later edits, and `/preferences reset` to restore documented defaults. Reset is the supported way to clear nullable active/quiet-hour windows.

## Proactive cadence policy

After the learner completes onboarding by saving choices, using defaults, or skipping, cadence becomes a deterministic learner-owned policy:

| Cadence | Review idle | Conversation idle | Daily limit | Accepted cooldown |
| --- | ---: | ---: | ---: | ---: |
| Rare | 20 min | 60 min | 1/day | 120 min |
| Normal | 10 min | 30 min | 3/day | 60 min |
| Frequent | 5 min | 15 min | 5/day | 30 min |

`proactive_snooze_minutes` remains a separate runtime setting.

For backward compatibility, an existing installation with **no completed learner preference profile** keeps using the pre-#67 environment/runtime proactive thresholds. Merely displaying the first-run onboarding offer does not change that legacy behavior. Once preferences are completed, the selected cadence is user-owned and environment overrides no longer silently change its mapping.

Explicit `/busy` and `/dnd` availability states continue to suppress proactive invitations regardless of learner preferences. Active/quiet-hour preferences add another suppression layer; they do not weaken availability rules.

Sound is persisted as a preference but audio playback is intentionally outside #67 and is handled separately.