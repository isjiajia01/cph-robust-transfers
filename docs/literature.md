# Literature Notes

Track papers, references, and external concepts used in modeling or pipeline design.

## Realtime Transit Reliability

- title: Rejseplanen GTFS / realtime ecosystem
- authors: operational source documentation
- year: ongoing
- link: add official references when needed
- key idea:
  - static schedule structure and realtime departures should be analyzed together
- how it applies to this project:
  - static GTFS supports graph structure
  - realtime API supports delay and transfer-risk layers

## Network Robustness

- title: graph robustness under targeted vs random failures
- authors: add papers used for final write-up
- year: TBD
- link: TBD
- key idea:
  - high-centrality removals often damage connectivity faster than random failures
- how it applies to this project:
  - supports the Week 2 targeted-attack framing and evaluation design

## Transfer Risk / Delay Modeling

- title: delay quantiles, reliability ranking, and transfer-risk aggregation
- authors: add references used for thesis/reporting
- year: TBD
- link: TBD
- key idea:
  - tail delays and mode-specific reliability are more useful than mean delay alone
- how it applies to this project:
  - drives `week3_conclusions`, `risk_model`, and `router` outputs
