# Native Intervals.icu workout syntax

Use the workout `description` field for both human explanation and structured steps. A structured step begins with `-`.

## Basic examples

### Easy run by pace zone

```text
Easy aerobic run. Stay relaxed and conversational.

Warmup
- 10m Z1

Main
- 35m Z2

Cooldown
- 5m Z1
```

### Repeated threshold intervals

```text
Controlled threshold work. Stop if form deteriorates.

Warmup
- 15m Z1-Z2

4x
- 8m Z4
- 2m Z1

Cooldown
- 10m Z1
```

### Cycling by FTP

```text
Aerobic ride with sweet-spot blocks.

Warmup
- 15m 55-70% FTP

3x
- 12m 88-92% FTP
- 5m 55% FTP

Cooldown
- 10m 50% FTP
```

### Heart-rate target

```text
Steady aerobic session.

- 10m 60-70% LTHR
- 40m 75-82% LTHR
- 10m 60-70% LTHR
```

## Authoring rules

- Use `m`, `s`, and `h` for duration.
- Prefer zones or percentages of known thresholds over invented absolute values.
- Match target mode to sport and available data: `PACE`, `POWER`, `HR`, or `AUTO`.
- Include warmup and cooldown for demanding sessions.
- State non-device instructions in prose before the structured steps.
- Keep the number of target changes practical for outdoor execution.
- Do not prescribe a threshold value when it is missing or stale; ask for it or use RPE/open targets.
- After upload, inspect returned duration, load, and `workout_doc`. If parsing is incomplete, revise the syntax before telling the user the draft is ready.
