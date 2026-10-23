# accessnet — the step-free subway as a network, not a checklist

Step-free access to the New York subway is published, measured and planned as a
property of a station: a station either has an elevator or it does not. It is
not a property of a station. It is directional, it depends on machines that
break, and what it is worth to a rider depends on where people actually travel.
Those three facts are in three separate open datasets and nobody multiplies
them together.

This repository does. It builds the directed step-free subway graph from the
MTA's own published stopping patterns, weights every origin-destination pair by
the ridership it actually carries, and asks what each of 451 passenger
elevators is holding up.

**The headline: ranking elevators by how much step-free travel they gate is
essentially uncorrelated with ranking them by how often they break.** Spearman
rank correlation between reachability damage and mean monthly outages is
**0.088** across 407 elevators. Against unavailability it is **−0.002**.
Against entrapments, **0.072**. Against the ridership of the station the
elevator serves, **0.054**. Every signal the open data surfaces for maintenance
triage is close to orthogonal to rider harm.

And the direction the model points is specific. The single most consequential
elevator in the system by expected trips denied is EL131 at 161 St-Yankee
Stadium: the sole street-to-mezzanine machine at its complex, unavailable 38.0%
of the time over the trailing two years, gating 1.47% of all step-free travel.

---

## What the numbers say

### Counting stations understates the problem, counting pairs overstates it

| measure | value |
| --- | --- |
| station complexes | 445 |
| step-free in at least one direction | 140 (31.5%) |
| origin-destination pairs carrying flow | 177,998 |
| pairs that are step-free served | 12,744 (7.2%) |
| weekday trips in the data | 222,488,205 |
| trips that are step-free served | 67,290,715 (**30.2%**) |

Step-free stations are disproportionately busy, so counting station pairs
understates step-free coverage by a factor of **4.2** against counting the
travel those pairs carry. A pair-count analysis and a trip-weighted analysis of
the same network disagree by more than four times, and only one of them
describes what riders get.

### Accessibility is directional, and the data says so

Of 496 stations, 166 are step-free in both directions, 322 in neither, and
**8 in exactly one**. All eight carry a free-text note that corroborates the
structured directional flags, with zero contradictions:

| station | routes | note | step-free |
| --- | --- | --- | --- |
| 49 St | N R W | Uptown only | northbound |
| Wilson Av | L | Manhattan-bound only | northbound |
| 86 St | 4 5 6 | Uptown local only | northbound |
| 50 St | C E | Downtown only | southbound |
| Spring St | C E | Downtown only | southbound |
| 28 St | 6 | Downtown only | southbound |
| Court Sq-23 St | E F | Manhattan-bound only | southbound |
| Hoyt St | 2 3 | Outbound only | southbound |

Because the flags are structured, the directed model does not rest on parsing
free text. `validate_notes_against_flags` performs the cross-check and the test
suite asserts that no note contradicts the flags. Two notes
("Manhattan-bound only") are direction-ambiguous without knowing the line's
orientation and are reported as unresolved rather than forced.

One restriction the flags cannot express is carried as a caveat instead of
being dropped: 86 St's note says "Uptown local only", meaning the accessible
platform serves the local 6 but not the express 4 and 5.

### Which complexes hold up the most step-free travel

Flow lost when a single complex loses step-free access, as a share of all
step-free served trips:

| complex | borough | step-free travel gated |
| --- | --- | --- |
| Times Sq-42 St / Port Authority | Manhattan | 13.56% |
| Grand Central-42 St | Manhattan | 11.19% |
| 34 St-Herald Sq | Manhattan | 7.15% |
| 14 St-Union Sq | Manhattan | 7.05% |
| Fulton St | Manhattan | 6.22% |
| 34 St-Penn Station (A,C,E) | Manhattan | 5.48% |
| 34 St-Penn Station (1,2,3) | Manhattan | 4.83% |
| 59 St-Columbus Circle | Manhattan | 4.64% |
| Chambers St / WTC / Park Place | Manhattan | 4.49% |
| Jackson Hts-Roosevelt Av | Queens | 4.17% |

### The agency's own reliability metric is optimistic, and most optimistic where it hurts

MTA publishes accessible-platform availability aggregated by borough and
weighted by platform count. Weighting instead by the travel each platform
carries gives a lower number in **every** borough:

| borough | trip-weighted | MTA published | difference |
| --- | --- | --- | --- |
| Bronx | 91.11% | 95.10% | **−3.99 pts** |
| Manhattan | 95.29% | 98.14% | −2.85 pts |
| Brooklyn | 96.64% | 98.12% | −1.48 pts |
| Queens | 96.48% | 97.33% | −0.85 pts |

The gap is largest in the Bronx, which is already the worst borough on the
agency's own measure. So the published metric is not merely optimistic, it is
*differentially* optimistic in the direction that understates the
worst-served borough. The Bronx also starts from far less step-free travel to
lose: 3.3 million step-free trips originate there against Manhattan's 44.3
million.

These two numbers are not measuring identical quantities. One is
platform-minutes, the other is trips. They are two estimators of the same
underlying question, how much step-free access riders actually get, and the
sign and ordering of the gap is the finding rather than the exact magnitude.

### Simultaneous outages

Drawing each sole-on-segment elevator down independently at its own published
unavailability, 300 draws:

| | share of step-free trips lost |
| --- | --- |
| mean | 4.45% |
| median | 3.84% |
| 90th percentile | 8.94% |
| 99th percentile | 13.48% |
| worst draw | 15.53% |

Mean 2.7 elevators down at once, maximum 9. Independence is an assumption and
a questionable one, because outages cluster by weather, by maintenance
campaign and by equipment vintage. That makes this an optimistic view of the
tail and a reasonable one for the mean.

### Where elevators should go next, and the honest answer

Greedy submodular selection of 20 complexes to make step-free, maximising the
travel unlocked:

| strategy | step-free travel unlocked |
| --- | --- |
| network-aware greedy | 37.38% |
| ranked by complex ridership | 36.27% (**97.0% of greedy**) |
| random selection | 9.46% (25.3% of greedy) |

**So for choosing stations, the obvious ridership heuristic is already almost
optimal.** Network structure matters enormously against picking at random, by
roughly four times, but the ridership criterion the MTA already publishes
captures 97% of what a reachability-optimal plan achieves, and 16 of the 20
picks are the same stations. That is a negative result for the capital-planning
half of this project, and it is worth more than a flattering one: it says the
station-selection problem is largely solved by criteria already in use.

The maintenance half is where the gap is. At the complex level, reachability
damage correlates with ridership at Spearman 0.94. At the elevator level under
the segment model it falls to 0.054, because what decides an individual
machine's consequence is **redundancy**, which no published signal captures and
which exists only in a free-text inventory field.

And the network-aware plan has a problem the ridership plan shares: it is
almost entirely Manhattan.

| borough | selected | candidates | share chosen |
| --- | --- | --- | --- |
| Manhattan | 18 | 71 | 25.4% |
| Queens | 2 | 54 | 3.7% |
| Brooklyn | 0 | 118 | 0.0% |
| Bronx | 0 | 47 | 0.0% |
| Staten Island | 0 | 15 | 0.0% |

Reachability is maximised at transfer hubs, and the hubs are in Midtown and
Lower Manhattan. Any real plan has to trade this against geographic equity
explicitly, which is why `equity_split` runs as part of the output rather than
being left for someone to discover later.

### The fleet

| | |
| --- | --- |
| elevators in the inventory | 482 |
| passenger assets used in the model | 451 |
| excluded as yard, freight, relay or signal-tower machines | 31 |
| recorded out of service | 22 |
| sole server of their vertical segment | **119** |
| complexes where every segment is redundant | 48 of 133 |
| complexes with at least one single point of failure | 85 of 133 |
| past their stated service life | 242 of 482 |
| median age | 17.6 years |
| exposed to weather | 192 |

Across 83,776 equipment-months since 2015, **64.4%** contain at least one
unscheduled outage: 55.6% for elevators, 75.2% for escalators. There have been
14,109 recorded entrapments. That base rate is why this project estimates
*unavailability* rather than outage occurrence: a public model predicting
"will this unit have an outage next month" is predicting a 64% base rate, so
high accuracy on that target means very little.

---

## How it works

### The directed step-free graph

Nodes are station complexes, which is the unit riders experience, the unit the
ridership and origin-destination data key on, and the unit the equipment data
points at. Edges come from the MTA's published stopping patterns: a directed
edge from A to B on line L in direction d exists when some pattern on L calls
at A then B consecutively. Patterns operated by fewer than 50 trains over the
schedule year are dropped as special moves, which removes 19,791 of 76,077
topology rows.

A trip from `o` to `d` is step-free served when there is a direction of travel
in which the origin platform is step-free, the destination platform is
step-free, and `d` is reachable from `o` in that direction.

**Intermediate complexes do not need to be accessible**, because the rider
stays on the train. This is why the problem is reachability on a subgraph
rather than a count of accessible stations, and it is why an outage is modelled
as removing a complex *as an endpoint* and not as cutting the graph. Cutting
the graph would kill every trip passing through and invent damage no rider
experiences. `test_disabled_complex_stays_passable` pins that down.

Transfers are the one place open data runs out. Whether a specific in-complex
transfer between two lines is step-free is not published machine-readably. The
model assumes a transfer inside a complex is step-free when the complex is
step-free in both the arriving and departing directions. `TRANSFER_ASSUMPTION`
in `accessnet/graph.py` states this in one place so it can be cited and
tightened. It is optimistic, so it can only overstate reachability.

### Elevators as a vertical path

A rider needs a continuous step-free chain from street to platform. Whether one
machine's failure breaks that chain depends on redundancy, and the data does
not state it. What the data gives is `street_access`, a reliable structured
flag, and `notes`, free text that is the only description of which vertical
segment a machine serves. Of 451 passenger elevators, 333 mention a mezzanine
or concourse, 278 mention a platform, and 424 describe a segment at all.

Each elevator is assigned a `(from_level, to_level)` pair and a confidence:

| confidence | elevators |
| --- | --- |
| high | 341 |
| medium | 84 |
| non-passenger, excluded | 31 |
| landings-only note | 9 |
| no segment inferable | 14 |
| weak street-language evidence only | 3 |

An elevator is **critical** when it is the only passenger elevator serving its
inferred segment at its complex, and redundant otherwise.

Because this rests on a free-text parse, **two damage models are reported side
by side**, so a reader can see exactly how much the parse carries:

- **segment** — an outage disables its complex only when that elevator is the
  sole server of its segment. Mean 4.45% of step-free travel at risk.
- **any** — every elevator outage disables its complex. A deliberately crude
  upper bound. Mean 29.03%.

Thirteen step-free complexes have no elevator in the inventory at all. Those
are reached by ramp or at grade, so no elevator outage can remove them, and
treating them as elevator-dependent would invent damage.

### The optimisation that made this tractable

Network reachability does not depend on which stations are step-free. Whether a
train can get from one complex to another is a property of the graph;
accessibility only decides whether a rider can board and alight at the ends.
So reachability is computed once per direction for all 177,998 flow pairs, and
every later question becomes a boolean mask.

Before that split, the greedy capital search re-ran thousands of full graph
sweeps and took twenty minutes. After it, one evaluation is about a
millisecond and the whole search takes six seconds.
`test_reachability_masks_do_not_depend_on_accessibility` asserts the invariant
the speed-up rests on, because if it were false the optimisation would be a
silent bug rather than a speed-up.

---

## Data, all public, no API key

| dataset | id | rows | what it gives |
| --- | --- | --- | --- |
| Subway Schedules 2025 | `q9nv-uegs` | 84,404,962 | stop sequences, aggregated server-side to 56,286 pattern rows |
| Subway Stations | `39hk-dx4f` | 496 | directional ADA flags, the basis of the directed model |
| Stations and Complexes | `5f5g-n3cz` | 445 | complex identity, names, boroughs |
| Elevator and Escalator Inventory | `94fv-bak7` | 759 | install dates, service life, street access, segment notes |
| Elevator and Escalator Availability | `rc78-7x78` | 83,776 | monthly availability, outages, entrapments since 2015 |
| Accessible Platform Availability | `thh2-syn7` | 525 | the agency's own metric, the baseline to beat |
| Origin-Destination Estimate 2024 | `jsu2-fbtj` | 116,279,069 | hourly station-pair flows, aggregated server-side to 177,998 pairs |
| Subway Hourly Ridership | `wujg-7c2s`, `5wq4-mkjj` | 167.5M | complex-level ridership |
| Subway Paths | `tdmq-asac` | 111,123 | inter-station distances |

Everything comes from `data.ny.gov` over the Socrata API without an app token.

Two things about pulling it are worth knowing, because both cost time to learn:

**Aggregate queries must not be paginated.** Socrata re-evaluates a `GROUP BY`
for every page, so walking the 116-million-row origin-destination table 50,000
rows at a time costs a full aggregation per page and eventually loses the
connection. The CSV endpoint accepts a `$limit` far above the JSON page cap, so
the entire 177,998-row flow matrix arrives in one request in about 40 seconds.
`socrata.export_csv` is that path.

**Subway Paths cannot carry the network.** It looks like the natural topology
source and it is not: it populates its numeric `station_id` for the numbered
IRT lines only, leaving it null across every lettered BMT and IND line. Only
178 of 423 stations have an id. The schedule table carries `gtfs_stop_id`,
which joins directly to the accessibility table, so that is used instead.

### Known limits

- **Transfers inside a complex** are assumed step-free when the complex is
  step-free in both relevant directions. Optimistic, documented, not verified.
- **No event-level outage history is public.** The finest public exposure
  measure is a monthly availability fraction, so this estimates how likely a
  machine is to be down, not when. Individual outages cannot be reconstructed.
- **Independence of outages** is assumed in the Monte Carlo and is false in
  reality; the tail is therefore understated.
- **The segment parse carries real weight**, which is why both damage models are
  always reported. 26 of 451 elevators have no inferable segment.
- **The MTA's actual capital-plan station list is deliberately not scored.** The
  public counts found while building this did not reconcile with each other,
  and scoring the agency against a list that could not be verified would be
  worse than not scoring it. `score_selection` takes an explicit list, so a
  verified plan drops straight in.
- Flows are weekday estimates for calendar 2024, so weekend and seasonal
  patterns are outside the model.

---

## Reproducing

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python -m accessnet.cli fetch           # every dataset, server-side aggregated
python -m accessnet.cli accessibility   # directional audit, graph, validation
python -m accessnet.cli equipment       # vertical-path model, base rates
python -m accessnet.cli damage          # per-elevator reachability damage
python -m accessnet.cli capital --k 20  # which stations next
python -m accessnet.cli metrics         # flow-weighted vs published availability
python -m accessnet.cli figures
```

`python -m accessnet.cli all` runs the sequence. Set `ACCESSNET_DATA` to share
one cache across checkouts. Everything runs on 4 CPUs with no GPU; the full
pipeline is under two minutes once the data is cached, and the slow part is the
one-off download.

### Tests

```sh
pip install pytest && PYTHONPATH=. python -m pytest tests/ -q
```

22 tests on a five-station synthetic network whose answers are known by hand,
plus one check against the real station table. The ones that matter are the
semantic invariants:

- an inaccessible station between two accessible ones does not block travel;
- a complex disabled by an outage stays passable for riders travelling through;
- removing a complex never increases served flow, and removing an inaccessible
  complex changes nothing;
- the precomputed reachability masks never change when accessibility does;
- a station step-free in one direction only is an endpoint in that direction
  only;
- a step-free complex with no elevator cannot be harmed by an elevator outage;
- greedy marginal gains are non-increasing, as submodularity requires;
- no free-text note contradicts the structured directional flags.

---

## Repository layout

```
accessnet/
  config.py        paths, dataset ids with observed row counts
  ada.py           directional step-free parsing and note cross-check
  graph.py         the directed network and the step-free subgraph
  equipment.py     elevators as vertical segments; redundancy; exclusions
  availability.py  per-unit unavailability, base rates, asset age
  damage.py        precomputed reachability, per-asset damage, Monte Carlo
  capital.py       greedy submodular station selection and equity split
  metrics.py       flow-weighted availability against the published metric
  pipeline.py      one assembly point so every entry point agrees
  report.py        figures
  cli.py           command line
  ingest/
    socrata.py     paginated queries, and the single-request CSV export
    mta.py         the specific tables, types fixed on the way in
results/           every table in this README, as CSV or JSON
results/figures/   six figures
tests/             22 tests on a hand-checkable synthetic network
```

## Prior art

Six repositories exist on GitHub for "mta elevator outage". The closest live
project runs a step-free route search over station-and-line pairs against the
live outage feed: it answers one rider's trip question and explicitly does no
prediction and no ranking of elevators or stations by importance, and it has no
flow weighting. Another is exploratory JavaScript with no graph. A third
exposes the feeds to a language model without analysis. A fourth runs a
shortest-path search on general service status rather than accessibility.

TransitCenter's *Access Denied* counts accessible stations and reachable
station pairs with no outage dynamics, and recommended importing a weighted
scoring method that it then did not apply. The MTA's own accessible-platform
metric is borough-aggregated and platform-weighted. Its published
station-selection methodology lists six criteria, none of which is a
network-reachability term.

A public repository predicts whether an elevator will have at least one
unscheduled outage next month at 81.5% accuracy. Against the 64.4% majority
base rate measured here, that is about 17 accuracy points above always
predicting "yes", which is why this project does not pursue that target.

What is new here: multiplying directional accessibility by equipment redundancy
by actual passenger flow, and reporting what falls out, including the parts that
say the existing approach is fine.

## What would change the conclusions

- Machine-readable step-free transfer paths inside complexes would replace the
  one optimistic assumption in the reachability model.
- An archive of the real-time elevator outage feed would turn monthly
  availability into event-level exposure, which would let the Monte Carlo drop
  its independence assumption and model clustering directly.
- A verified capital-plan station list would let the agency's actual selection
  be scored on reachability gain instead of only against heuristics.
