# Price strategy notes

Initial intended strategy:
- 15-minute price slots when available
- P30 cheap / P80 expensive classification
- absolute cheap-price escape threshold
- stable daily thresholds to avoid mid-slot reclassification
- six-hour lookahead
- pre-brake is price-only
- preheat requires both upcoming expensive period and suitable cold forecast

Price strategy remains an overlay and must never replace the PI comfort loop.
