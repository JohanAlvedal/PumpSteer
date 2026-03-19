# PumpSteer Roadmap

## Guiding Principle

Focus on stability, predictability, and control quality before adding advanced features.

---

## Priority 1 – Core Stability (Must Work Well)

### 1. PI/PID Control Quality
- stable control loop
- proper anti-windup
- no oscillations
- predictable behavior

### 2. Clear Control Architecture
- PI is the main control loop
- feedforward is external bias
- brake is a bounded overlay
- no conflicting control paths

### 3. Price Behavior (Basic)
- avoid heating during expensive periods
- allow moderate heating when cheap
- no aggressive preheating by default

### 4. Forecast Integration (Basic)
- continuous bias (not binary)
- correct direction (warm → less heating, cold → more)
- moderate influence only

### 5. Debug & Observability
Must be able to explain behavior.

Key signals:
- pi_output
- price_feedforward
- forecast_feedforward
- brake_factor
- final_output

---

## Priority 2 – Smart Behavior

### 6. Tuning & Balance
- reduce double influence from price
- balance feedforward vs brake
- ensure aggressiveness scaling feels correct

### 7. Lookahead (3–6 hours)
Introduce simple forward-looking logic:

- detect long expensive periods
- detect upcoming cheap periods
- anticipate temperature changes

Goal:
- shift heating intelligently in time

---

### 8. Controlled Preheat

Preheat should only activate when:

- expensive period lasts several hours
- outdoor temperature is low
- house has thermal capacity
- cheaper period exists before

Avoid:
- aggressive heating just because price is low

---

## Priority 3 – Optimization

### 9. Adaptive Tuning (No ML)
- adjust behavior based on house response
- adapt to thermal inertia
- refine PI parameters safely

### 10. Improved Diagnostics
- comfort score
- cost efficiency indicators
- heating cycle tracking

### 11. Modularization
Split into clearer modules:

- control.py
- pricing.py
- forecast.py
- diagnostics.py

---

## Priority 4 – Future / Optional

### 12. Machine Learning (Optional)

Only consider if:

- strong baseline exists
- sufficient data is available
- clear optimization target is defined

Otherwise:
- skip ML

---

## Development Strategy

1. Implement core control
2. Test in real environment
3. Tune based on real behavior
4. Add lookahead
5. Refactor structure
6. Consider advanced features

---

## Philosophy

- Simplicity over complexity
- Control theory before AI
- Predictability over “smartness”
- Local and robust operation
