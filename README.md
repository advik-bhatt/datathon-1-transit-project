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

**The headline: how often an elevator breaks says almost nothing about how
much step-free travel its failure blocks.** Spearman rank correlation between
reachability damage and mean monthly outages is **0.010** across 407
elevators, which is as close to no relationship as this data gets. Against
entrapments it is **0.169**. Against unavailability it is **-0.210**, a weak
*negative* relationship: the machines gating the most travel are somewhat
better maintained than average, though nowhere near enough to offset what they
carry. A crew list ordered by outage count is close to random with respect to
the trips those outages block.

> **Corrections, 2026-10-23.** An adversarial prior-art and data pass after the
> first commit changed three things. All are fixed here rather than quietly
> edited away.
>
> 1. **The directed accessible graph is not new.** Two Sigma Data Clinic's
>    archived `tsdataclinic/mta` already builds a system-wide street-to-train
>    ADA graph at platform and direction granularity from GTFS, and its
>    `elevator_importance.py` already measures existing-elevator redundancy.
>    The original claim to be first at multiplying directional accessibility by
>    redundancy was wrong. What survives is the flow weighting and what follows
>    from it.
> 2. **TransitCenter already published the core insight in print**: stations
>    have elevators in series, so one outage can disable a whole station and
>    per-equipment uptime overstates accessibility. Nobody had computed it. The
>    insight is theirs; the number is this project's.
> 3. **Two data defects, both fixed, both of which moved numbers.** The
>    agency's own `revenue_machine` flag marks 52 elevators as non-revenue
>    where reading the notes caught only 31, so 21 yard and service machines
>    were inside the model. And unavailability was the mean of monthly ratios
>    rather than hours-weighted, which understated the worst unit by 5 points.
>
> **Second correction, same day, and the largest.** The claim that the
> free-text `notes` field is "the only public description of which vertical
> segment the machine serves" was **false**. The inventory carries structured
> columns for the whole thing, populated for exactly the 430 passenger
> elevators and blank for exactly the 52 the agency flags as non-revenue:
> `elevator_direction_serviced`, `elevator_order`, three level-access flags,
> and `redundant_elevator` with the substitute's equipment code named per
> level. Scored against that published redundancy flag, the text inference
> agreed on only **45.0%** of 418 elevators, Cohen's kappa 0.105. The failure
> was systematic: collapsing a level pair such as mezzanine-to-platform into
> one segment treated every elevator sharing it at a complex as a substitute,
> when they usually serve different platforms and directions. EL298 runs
> "Park Ave & 23 St (NE corner) to uptown platform" and EL299 runs
> "(NW corner) to downtown platform"; neither can stand in for the other.
>
> The consequence was that the first version **understated the problem**:
> 115 single points of failure where the agency's own flag implies **309**,
> and 4.5% of step-free travel at risk where the corrected figure is
> **10.3%**. The structured fields are now the source of truth, the notes are
> a cross-check, and every figure below is recomputed from them.

And the direction the model points is specific. The single most consequential
elevator in the system by expected trips denied is EL228 at 34 St-Penn Station
on the A, C and E: a southbound mezzanine-to-platform machine with no recorded
substitute, gating 5.48% of all step-free travel and unavailable 13.4% of its
in-service hours, which works out to roughly 493,000 trips a year.

The next three are all at 161 St-Yankee Stadium, and together they are the
clearer story. EL131, EL134 and EL135 cover street to mezzanine and both
platform directions, none has a substitute, and they ran at 43.1%, 39.6% and
43.7% unavailability over the trailing two years. All three were also out of
service entirely for sixteen consecutive months before returning, which the
model reports separately rather than scoring as unreliability: a replacement
programme and a machine that keeps breaking are different problems.

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

### Is the headline tautological? No, and here is the test

A fair objection: reachability damage is built from passenger flow and
redundancy, while outage counts are built from availability records. Two scores
computed from disjoint columns being uncorrelated could be arithmetic rather
than a finding.

The objection is answered by testing the input independence directly. If busier
stations had systematically worse elevators, ridership would carry reliability
information and the orthogonality would be an artifact of how the scores were
built. They do not:

| | Spearman, n = 407 |
| --- | --- |
| complex ridership vs elevator unavailability | +0.042 |
| complex ridership vs mean monthly outages | -0.119 |
| complex ridership vs entrapments | -0.044 |
| complex ridership vs in-service coverage | -0.023 |

Ridership and reliability come from genuinely separate datasets and are
genuinely unrelated. That is an empirical fact with content, and it is what
makes the headline meaningful: damage tracks flow and redundancy, flow says
nothing about reliability, so damage cannot be recovered from a reliability
signal.

Damage against complex ridership is Spearman 0.344 under the corrected
redundancy model, up from 0.067 under the text parse. Ridership alone is
therefore a weak proxy for which elevator matters, and the missing ingredient
is exactly the redundancy the agency publishes and nobody joins to flow.

### The agency's own reliability metric is optimistic, and most optimistic where it hurts

MTA publishes accessible-platform availability aggregated by borough and
weighted by platform count. Weighting instead by the travel each platform
carries gives a lower number in **every** borough:

| borough | trip-weighted | MTA published | difference |
| --- | --- | --- | --- |
| Bronx | 75.08% | 95.10% | **-20.02 pts** |
| Queens | 89.09% | 97.33% | -8.24 pts |
| Manhattan | 90.65% | 98.14% | -7.48 pts |
| Brooklyn | 91.73% | 98.12% | -6.38 pts |

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
| mean | 10.26% |
| 90th percentile | 19.31% |
| 99th percentile | 27.04% |

Mean 7.7 elevators down at once, maximum 16. Independence is an assumption and
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
| passenger assets used in the model | 430 |
| excluded by the agency's `revenue_machine` flag | 52 |
| recorded out of service | 22 |
| out of service for more than half the trailing two years | 27 |
| single points of failure, per the agency's own flag | **309** |
| complexes where every elevator has a substitute | 11 of 133 |
| complexes with at least one single point of failure | 122 of 133 |
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

A rider needs a continuous step-free chain from street to platform, so whether
one machine's failure breaks that chain depends on redundancy. **The agency
publishes both.** `street_access`, `elevator_mezzanine_1_access`,
`elevator_mezzanine_2_access` and `elevator_platform_access` say which levels a
machine touches; `elevator_order` gives its position in the chain, one through
six; `elevator_direction_serviced` records Both for 213 elevators, Southbound
for 111 and Northbound for 106; and `redundant_elevator` marks whether a
substitute exists, naming its equipment code per level. The flag is internally
consistent: 107 of the 109 elevators marked as having a substitute name one,
and 308 of the 309 marked without one name none.

Each elevator's `(from_level, to_level)` pair now comes from those columns:

| source | elevators |
| --- | --- |
| structured level-access columns | 430 |
| non-revenue, excluded | 52 |

An elevator is a **single point of failure** when the agency records no
substitute for it. 309 of 430 are, and only 11 of 133 complexes with elevators
have a substitute for every machine.

Two damage models are still reported side by side, because the lower one now
depends on the agency's redundancy bookkeeping being right rather than on a
text parse:

- **segment** — an outage disables its complex only when that elevator is the
  substitute recorded for it. Mean 10.26% of step-free travel at risk.
- **any** — every elevator outage disables its complex. A deliberately crude
  upper bound. Mean 28.03%.

The gap between the two narrowed sharply when the redundancy source changed,
from 4.5% against 28.0% to 10.3% against 28.0%, which is what it should do: the
structured flag finds far more single points of failure than the text parse
did, so the honest estimate moves toward the upper bound.

Thirteen step-free complexes have no passenger elevator in the inventory at
all, so no elevator outage can remove them and treating them as
elevator-dependent would invent damage. Calling them ramp or grade access is an
**inference, not a published fact**: several carry real ridership, and an
inventory gap would look identical in this data. Six of them are Staten Island
Railway complexes, which are additionally absent from the subway
origin-destination matrix by construction and so carry no flow here either. The
honest statement is that the model is blind at those nodes.

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
| Elevator and Escalator Inventory | `94fv-bak7` | 759 | install dates, service life, and the structured vertical-path and redundancy columns: level-access flags, chain order, direction served, `redundant_elevator` with the substitute's code |
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
- **The redundancy figures are the agency's own bookkeeping**, not an
  independent measurement. If `redundant_elevator` is wrong or stale for a
  given machine, this model inherits that. It is internally consistent, with
  107 of 109 substitute flags naming a partner code, but it has not been
  checked against the ground truth of a rider actually being stranded, because
  no public dataset records that.
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

27 tests on a five-station synthetic network whose answers are known by hand,
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
- no free-text note contradicts the structured directional flags;
- the agency's `revenue_machine` flag overrides a passenger-looking note, and a
  revenue machine at a station whose name contains "Yards" is not excluded;
- the vertical path comes from the structured level flags, and a misleading
  note cannot move it;
- redundancy comes from the published `redundant_elevator` flag, and counting
  shared level pairs is shown to disagree with it;
- unavailability is hours-weighted, so a month with 80 in-service hours does
  not count as much as one with 744;
- months with no in-service hours are reported as capital outage rather than
  scored as unreliability.

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
tests/             27 tests on a hand-checkable synthetic network
```

## Prior art

Each item below was fetched and read during an adversarial verification pass.
Two of this project's original claims did not survive it.

**The hardest technical piece already existed.** Two Sigma Data Clinic's
`tsdataclinic/mta` (archived) builds a system-wide accessible graph "mapped
from street to train back to street via ADA compliant routes": it matches
elevators to platforms *and* to the lines and directions serving them, uses
GTFS to find which platforms are connected by which trains, and joins the
result into one graph. Its `elevator_importance.py` measures existing-elevator
redundancy for maintenance. So a directed, route-and-platform-level accessible
graph with a redundancy measure is prior art. The original claim here, that
nobody treats accessibility as directed and redundancy-aware, was wrong. What
`tsdataclinic/mta` does not do is weight by origin-destination flow, rank for
capital installation, or produce a time series.

**The core insight is published; the number was not.** TransitCenter's *Access
Denied* already states in print that stations "often have two or three
elevators in series, so a single outage can make the whole station
inaccessible," and that the elevator uptime figure therefore overstates
station accessibility. It also already counted step-free station pairs: 110 of
472 stations accessible, 11,990 step-free pairs against 222,312 for a stair
user, "only 5% as much trip-making opportunity." By its own text it does not
multiply measured per-equipment availability along actual chains, does not
weight by ridership, and produces no time series. The insight belongs to them.
This repository's contribution is computing it, with flow weights replacing
pair counts, which is the step TransitCenter explicitly declined.

**The outage-prediction lane is occupied**, and this project deliberately does
not enter it. `AnsChoudhary/mta-predictive-maintenance` (October 2026) is an
XGBoost next-month unscheduled-outage classifier on the same availability
table at 93% recall and 80% precision.
`jiayili6812/mta-elevator-reliability` is a random forest on the same target,
and its own README calls itself "a planning and chronic-reliability layer, not
a real-time trip tool." Neither models chains, paths or flow. Against the
64.4% majority base rate measured here, a binary next-month outage target is
close to uninformative, which is why this project estimates unavailability
instead.

**Routers, trackers and the agency's own framing.** Of the six repositories
that exist for "mta elevator outage": `forbiddenlink/stepfree` runs a step-free
route search against the live outage feed, answering one rider's trip question
with no prediction, no ranking and no flow weighting; `nevvada/can-i-get-there`
is a current-status lookup; `jeremiak/mta-elevator-outages` and
`mmmfang/mta-elevators` are exploratory; `BetaNYC/mta-mcp` wraps the feeds for
a language model; `harshit-ojha0324/nyc-transit-hub` searches general service
status rather than accessibility. `binh748/expanding-mta-accessibility` asks
this project's capital question with turnstile counts and census data,
Manhattan only, no flow and no reachability. The New York City Council's
accessibility page reports counts, a raw outage total and a top-five-by-outage
list, and defines availability as the percent of a 24-hour period a unit runs,
which is exactly the count-and-uptime framing this project argues against.

**What survives as new.**

1. **Flow-weighted step-free reachability**, where the published alternatives
   count stations, pairs, or equipment-hours. The gap is a factor of 4.2.
2. **The orthogonality result**, with the input independence measured rather
   than assumed, so it is not an artifact of how the scores were built.
3. **Trip-weighted availability set beside the agency's platform-weighted
   metric**, which shows the published number is optimistic in every borough
   and worst in the Bronx. The Bronx-Manhattan gap itself is visible in MTA's
   own figures and is not this project's to claim; the trip weighting and the
   size of the discrepancy are.
4. **The negative result on capital selection**, which says the half of the
   problem the agency's published criteria already address does not need this
   machinery.

## What would change the conclusions

- Machine-readable step-free transfer paths inside complexes would replace the
  one optimistic assumption in the reachability model.
- An archive of the real-time elevator outage feed would turn monthly
  availability into event-level exposure, which would let the Monte Carlo drop
  its independence assumption and model clustering directly.
- A verified capital-plan station list would let the agency's actual selection
  be scored on reachability gain instead of only against heuristics.
