# Perfect entry pattern (5m / 1h)

Reference for how setups should look, so the bot stays aligned with the intended entries.

## Pattern

1. **Rejection block**
   - **Long:** Clear bearish candle(s) with a **long lower wick** — rejection of lows.
   - **Short (market maker sell model):** Rally to a high, then candle(s) with **long upper wick(s)** — rejection of highs.

2. **Entry**
   - **Within the wick on the retracement**, before the next leg (volume injection).
   - Level = fib of the **wick**:
     - **0.5** = CE (50% of wick) — balanced.
     - **0.25** = deeper in wick — tighter entry, higher RR.
     - **0.75** = shallower (closer to body) — more conservative.
   - Same idea on **5m and 1h**: 1h example = large white candle with long upper wick, entry at 0.5 or 0.25 of that wick, stop above wick, target below.

3. **Stop**
   - **Long:** Below the low of the rejection wick (small buffer).
   - **Short:** Above the high of the rejection wick (small buffer).
   - Typical risk in examples: ~6–15 points NQ.

4. **Target**
   - High RR (examples ~6:1 to 14:1). Use discretion; bot uses `target_rr` (e.g. 5) with option to aim higher.

## Config mapping

| Concept              | Config / behaviour |
|----------------------|--------------------|
| Entry level in wick  | `entry_fib_in_wick`: 0.5 (CE), 0.25 (tighter/higher RR) |
| Retest band          | `entry_zone_tolerance_points_*` — bar must overlap this to fill |
| Stop                 | Beyond wick + `stop_buffer_points_*` (and volume buffer if high vol) |
| RR                   | `target_rr` (e.g. 5); high RR = discretion |
| HTF                  | Bias only (direction); never filters setups |

## 1h market maker sell model

- Same structure: reject high → retrace into wick → short entry at fib in wick (e.g. 0.5) → stop above wick, target below.
- Logic in code is timeframe-agnostic; primary run is 5m; 1h can be used the same way if we run on 1h or use 1h RBs as context.
