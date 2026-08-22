# Learning rollout policy

The thermal learner follows three gates:

1. **Collect** - update the model from qualified observations only.
2. **Shadow** - produce predictions and compare them with real outcomes without changing control.
3. **Assist** - only after validation, allow bounded timing/strength advice.

The learner must expose sample count and confidence. A model with insufficient confidence cannot influence control.

A user-visible reset must clear learned model state without resetting unrelated device configuration.
