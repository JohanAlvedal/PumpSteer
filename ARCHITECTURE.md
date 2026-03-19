# PumpSteer Architecture

## Overview

PumpSteer is a Home Assistant custom integration for optimizing heat pump behavior by manipulating the outdoor temperature sensor input ("fake outdoor temperature").

The system is designed to be:
- fully local (no cloud dependency)
- predictable and debuggable
- based on control theory (PI/PID), not black-box ML

---

## Core Control Philosophy

PumpSteer uses a **PI-centered hybrid control architecture**.

The system consists of four main layers:

1. PI Controller (primary control loop)
2. Feedforward (price + forecast)
3. Brake Overlay (bounded modifier)
4. Safety Constraints (hard limits)

---

## 1. PI Controller (Primary Control)

The PI controller is the main regulator responsible for maintaining indoor comfort.

Input:
- indoor temperature
- target temperature

Output:
- base temperature offset

Responsibilities:
- maintain target temperature
- handle steady-state error
- provide stable control without oscillation

Notes:
- derivative (D) term may be present but is optional
- anti-windup is required
- PI output is always the foundation of control

---

## 2. Feedforward Layer

Feedforward adds external bias to the PI output.

### Price Feedforward
Derived from electricity price categories.

Purpose:
- reduce heating when electricity is expensive
- allow more heating when electricity is cheap

Important:
- must not depend on temperature error
- must be bounded and predictable

---

### Forecast Feedforward

Derived from future outdoor temperature trend.

Purpose:
- anticipate upcoming heating or cooling needs
- shift control slightly ahead of time

Characteristics:
- continuous (not binary)
- based on trend, average, and deviation
- must remain moderate (no aggressive behavior)

---

## 3. Brake Overlay

Brake is a bounded modifier applied after PI + feedforward.

Purpose:
- limit heating when necessary (price or temperature conditions)
- provide smooth transitions (ramp in/out)

Important:
- must NOT dominate the control loop
- must be limited in strength (e.g. max delta in °C)
- should be seen as a safety/comfort modifier

---

## 4. Safety Constraints

Hard limits applied to final output.

Examples:
- MIN_FAKE_TEMP
- MAX_FAKE_TEMP

Purpose:
- ensure system stays within safe operating range
- reflect real-world actuator limits

---

## Control Flow

1. Read sensors (indoor, outdoor, target, price, forecast)
2. Compute PI output (temperature error)
3. Compute feedforward bias:
   - price bias
   - forecast bias
4. Combine:
   base_offset = PI_output + feedforward_bias
5. Convert to fake outdoor temperature
6. Apply brake overlay (bounded)
7. Apply safety clamps
8. Output final fake outdoor temperature

---

## Design Principles

- PI is always the primary control mechanism
- Feedforward must be external (not derived from error)
- Avoid double influence from the same signal
- Prefer simple, explainable logic over complexity
- System must be debuggable at all times

---

## Non-Goals (for now)

- Full model predictive control (MPC)
- Machine learning-based control
- Cloud-based optimization

These may be explored later, but are not part of the core design.
