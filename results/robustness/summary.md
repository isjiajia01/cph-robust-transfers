# Robustness Summary

## Graph Build
- Data date: `20260302`
- GTFS feed version: `gtfs_20260302`
- Nodes / edges: `36871` / `50137`
- Build params hash: `e997b3fea207`

## Read This Output
- Compare targeted vs random decay: faster targeted drop implies hub-dependent fragility.
- Read `impact_delta_lcc` as the single-node connectivity loss if that node disappears.
- Use the planning implication column as a first-pass narrative, not a final intervention recommendation.

## Random vs Targeted Checkpoints
- At `9%` removal: random LCC avg=`0.815109`, targeted LCC avg=`0.198774`
- At `15%` removal: random LCC avg=`0.600434`, targeted LCC avg=`0.014278`
- At `30%` removal: random LCC avg=`0.093734`, targeted LCC avg=`0.005461`

## Top-10 Vulnerable Hubs
- #1 `000461105500`: degree=`6`, betweenness=`44821421.816173`, impact_delta_lcc=`0.000134`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
- #2 `000823102901`: degree=`5`, betweenness=`125887240.62475`, impact_delta_lcc=`9e-05`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
- #3 `000461034600`: degree=`7`, betweenness=`60099084.926765`, impact_delta_lcc=`9e-05`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
- #4 `000631200102`: degree=`13`, betweenness=`236651059.459703`, impact_delta_lcc=`4.5e-05`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
- #5 `000551922507`: degree=`5`, betweenness=`210796614.289565`, impact_delta_lcc=`4.5e-05`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
- #6 `000607300902`: degree=`7`, betweenness=`209091509.252632`, impact_delta_lcc=`4.5e-05`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
- #7 `000621400109`: degree=`4`, betweenness=`206417416.091591`, impact_delta_lcc=`4.5e-05`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
- #8 `000621405111`: degree=`5`, betweenness=`205637550.21853`, impact_delta_lcc=`4.5e-05`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
- #9 `000621403501`: degree=`4`, betweenness=`205601447.364364`, impact_delta_lcc=`4.5e-05`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
- #10 `000621403521`: degree=`2`, betweenness=`205595302.197697`, impact_delta_lcc=`4.5e-05`, implication=Likely transfer bridge; monitor cross-line dependency and disruption spillover.
