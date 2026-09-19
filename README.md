# repatriation-network-checks

Verification for **[What Cloud Repatriation Actually Costs the Network](https://mike.ydn.au/cloud-repatriation-network-cost/)**.

Companion to that post. Every figure quoted in it is recomputed here from
published price-list data. Standard library only, no dependencies, no network
access, no credentials.

```
python3 repatriation-network-checks.py
```

```
8/8 groups passed, 1 skipped, 0 failed
```

## Why this exists

Cloud egress is priced **per gigabyte transferred**. IP transit is priced
**per megabit per second at the 95th percentile**. Those are different units,
and most repatriation business cases compare them without converting. The
conversion factor is **328.5 GB per Mbps per 730-hour month**, and almost
everything in the post follows from applying it in both directions.

## Findings

Each of these is asserted by the script rather than stated.

| Finding | Figure |
|---|---|
| AWS Sydney's first egress tier, restated in the unit circuits are sold in | **$37.45 per Mbps per month** at 100% duty |
| Against the published Q2 2026 100GigE transit floor of $0.03/Mbps | **312x to 1,248x**, depending on peak-to-mean ratio |
| Against an *inferred* Australian transit price of $0.50/Mbps | **19x to 75x** |
| Australia spans two ExpressRoute pricing zones | Sydney/Melbourne/Perth/Auckland **Zone 2 at $0.05/GB**; Canberra **Zone 1 at $0.025/GB** |
| Direct Connect destination groups out of Sydney dearer per GB than the plain internet gateway | **4 of 6** (1.41x to North America and Europe, 2.07x to South America and Africa) |
| The Australian penalty is a missing volume discount, not a surcharge | Sydney falls 19% first tier to top tier; N. Virginia falls 44% |
| ExpressRoute Unlimited break-even against Metered | **50.3%** sustained utilisation on 1 Gbps Zone 2, 47.9% on 10 Gbps |
| ExpressRoute virtual network gateway, absent from every comparison found | **31.8%** of the circuit charge, and the circuit will not pass traffic without it |
| 37signals moving 5 PB off S3 in under 10 days on a 100 GbE link | **46.3 Gbps sustained**, and that is a floor |

Two results ran against expectation. Cheaper per-gigabyte zones push the
ExpressRoute Unlimited threshold *further out* rather than closer, so Canberra
is the worst place in Australia to buy the flat rate. And a private circuit is
the cheap option only inside its own region: leaving it, Direct Connect costs
more per gigabyte than the internet gateway it was meant to replace.

## Groups

1. The unit conversion, and the direction the conservatism actually runs.
   Peakiness raises the transit bill and leaves the egress bill alone, so a
   peaky profile **helps** cloud and **hurts** on-premises.
2. Tiered internet egress for AWS Sydney, AWS N. Virginia and Azure Australia
   East on both routing preferences, including the effective rate rising
   before it falls.
3. Private-circuit break-evens, including the ExpressRoute gateway charge and
   the Australian two-zone split.
4. ExpressRoute Unlimited against Metered, as a sustained-utilisation
   threshold.
5. Cloud egress restated as a per-Mbps price, swept across peak-to-mean
   ratios from 1.0 to 4.0.
6. The cases where the private circuit costs more per gigabyte than the public
   internet.
7. 37signals' published exit, checked for what it does and does not say about
   connectivity. The answer is that it says nothing: the figure is
   "Bandwidth, power, and boxes" in one line.
8. The Australian transit gap. Why no 2026 Sydney price is used, how wrong the
   2021 one would be if carried forward, and what an inferred price does to
   the headline.

## Sources

All prices are **list**, retrieved **19 September 2026**, and recorded in the
`PRICES` table with the offer version, meter ID or page they came from.

- **AWS** bulk price list API. Offer `AWSDataTransfer` version `20260916132208`,
  offer `AWSDirectConnect` version `20260917204010`, offer `AmazonVPC` version
  `20260917190528`. Public and unauthenticated; use the per-region
  `region_index.json` route, because the full offers are 59 MB and 95 MB.
- **Azure** retail prices API, `prices.azure.com/api/retail/prices`.
  `serviceName=Bandwidth` with `armRegionName=australiaeast`, and
  `serviceName=ExpressRoute`. Meter IDs are in `PRICES`.
- **Azure ExpressRoute zone membership** from the Zone column of
  *ExpressRoute locations and connectivity partners* on Microsoft Learn. The
  rate table and the zone table are on different pages, which is how it is
  possible to price Australia as Zone 3 by mistake.
- **Google Cloud** VPC network pricing. Note Google quotes per **GiB**, not GB.
- **TeleGeography**, *IP Transit Pricing in 2026* (16 September 2026) and
  *IP Transit Pricing Trends in Asia* (4 September 2026), plus
  *Wholesale Pricing and the WAN* (23 November 2021) for the historical figure
  the script declines to carry forward.
- **IX Australia** published price list.

## What this is not

- Not a quote, a discount, or a private rate card. If you have negotiated
  pricing, substitute it in `PRICES` and rerun.
- Not measured. This is arithmetic on published rates. The numbers are exact
  statements about price lists, not about any network's behaviour.
- Not a full repatriation model. There is no compute, storage, staffing or
  opportunity cost here. The claim is that the network line is mispriced in
  the public debate, not that repatriation is correct.

Two inputs are declared assumptions rather than published facts, and both are
isolated so they can be replaced: `FX_AUD_USD`, because the IX Australia price
list is in AUD and the cloud price lists are in USD, and `PEAK_TO_MEAN`, which
group 5 sweeps rather than fixing.

**There is deliberately no 2026 Australian IP transit price in this file.** The
only publicly citable Sydney figure is a **10 GigE** quote from November 2021,
and the 2026 floor is **100 GigE**, so a ratio across them folds a port-size
change into a five-year price collapse. Group 8 shows the arithmetic and the
size of the error instead of committing it.

## Licence

MIT. See [LICENSE](LICENSE).
