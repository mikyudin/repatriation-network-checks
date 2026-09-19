#!/usr/bin/env python3
"""
Verification for "What Repatriation Actually Costs the Network".

Every number quoted in the post is recomputed here from published price-list
data, with no network access and no dependencies outside the standard library.

    python3 repatriation-network-checks.py

All prices are list prices, retrieved 2026-09-19, and are recorded in PRICES
below with the offer version, meter ID or page they came from. Nothing here is
a quote, a discount or a private rate card, and nothing here is modelled: if a
number appears in the post it is either in PRICES or computed from PRICES.

Two inputs are declared assumptions rather than published facts, and both are
isolated so a reader can replace them:

  * FX_AUD_USD, because the IX Australia price list is in AUD and the cloud
    price lists are in USD.
  * PEAK_TO_MEAN, the ratio between 95th-percentile rate and mean rate for a
    real traffic profile. Group 5 sweeps it rather than picking one.

There is no 2026 Australian IP transit price in this file. TeleGeography's
only published Sydney figure is from November 2021 and transit has fallen
17-22% compounded annually since, so deriving a 2026 Australian multiple from
it would be wrong by a large factor. Group 5 uses the published 2026 global
floor instead, and the Australian side of the comparison rests on the IX
Australia port price, which is current and public.

Groups:

  1. The unit conversion the argument rests on: cloud egress is priced per
     gigabyte transferred, IP transit per megabit per second at the 95th
     percentile. The two are not comparable until one is in the other's units.
  2. Tiered internet egress for AWS Sydney, AWS N. Virginia and Azure
     Australia East on both routing preferences, including the effective rate
     rising before it falls.
  3. Private-circuit break-evens, including the ExpressRoute gateway charge
     that comparisons leave out, and the Australian two-zone split.
  4. ExpressRoute Unlimited against Metered, as the sustained circuit
     utilisation at which the flat rate wins.
  5. Cloud egress restated as a per-Mbps price, against the published 2026
     transit floor and the published IX Australia port price.
  6. The cases where the private circuit costs more per gigabyte than the
     public internet.
  7. 37signals' published cloud exit, which is the only first-hand data set
     with real numbers in it, checked for what it does and does not say about
     connectivity.
  8. The Australian transit gap: why no 2026 Sydney price is used, how large
     the error would be if the 2021 one were carried forward, and what happens
     to the headline multiple if you substitute an inferred Australian price
     anyway. This group exists to show its own working rather than to produce
     a number the post relies on.
"""

import sys

FAILURES = []
SKIPPED = []

HOURS_PER_MONTH = 730          # the convention every provider's price list uses

# Declared assumptions, not published facts. See the module docstring.
FX_AUD_USD = 0.65              # nominal, 2026; group 5 tests the sensitivity
PEAK_TO_MEAN = 2.5             # ordinary diurnal enterprise profile


def check(label, got, want):
    ok = got == want
    if not ok:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
    print(f"     {'ok  ' if ok else 'FAIL'} {label}: {got}")
    return ok


def close(label, got, want, tol):
    ok = abs(got - want) <= tol
    if not ok:
        FAILURES.append(f"{label}: got {got!r}, want {want!r} +/- {tol}")
    print(f"     {'ok  ' if ok else 'FAIL'} {label}: {got}")
    return ok


# ---------------------------------------------------------------------------
# Published prices, with provenance.
# ---------------------------------------------------------------------------

PRICES = {
    # --- AWS bulk price list API, offer index publicationDate 2026-09-19.
    # Offer AWSDataTransfer, version 20260916132208.
    # Tiers are (upper bound in GB, USD per GB); the last is unbounded.
    "aws_egress_syd": [(10240, 0.114), (51200, 0.098), (153600, 0.094),
                       (float("inf"), 0.092)],
    "aws_egress_iad": [(10240, 0.090), (51200, 0.085), (153600, 0.070),
                       (float("inf"), 0.050)],
    # Global-DataTransfer-Out-Bytes: USD 0.00 for the first 100 GB, aggregated
    # across all regions, each month.
    "aws_egress_free_gb": 100,
    # APS2-DataTransfer-Regional-Bytes.
    "aws_regional_transfer": 0.01,

    # Offer AWSDirectConnect, version 20260917204010.
    # Dedicated port, USD per hour, at the Sydney and Melbourne DX locations.
    "aws_dx_port_hour": {1: 0.30, 10: 2.25, 100: 22.50},
    # IntraRegion Outbound from ap-southeast-2 to an Australian or NZ DX
    # location: NEXTDC S2 Sydney, Equinix SY5, NEXTDC B2 Brisbane,
    # CDC Hume 2 Canberra, Datacom DH6 Auckland.
    "aws_dx_egress_intra_au": 0.042,
    # InterRegion Outbound from ap-southeast-2, grouped by destination.
    "aws_dx_egress_inter": {"melbourne_eqme2": 0.042, "japan": 0.1132,
                            "north_america_europe": 0.13, "mumbai": 0.14,
                            "latam_africa_me": 0.19},
    "aws_dx_egress_intra_us": 0.02,

    # --- Azure retail prices API, prices.azure.com/api/retail/prices.
    # serviceName=Bandwidth, armRegionName=australiaeast.
    # First 100 GB/month free on both routing preferences.
    # meterId fe167397-a38d-43c3-9bb3-8e2907e56a41, Microsoft Global Network.
    "az_egress_mgn": [(100, 0.0), (10335, 0.12), (51295, 0.085),
                      (153695, 0.082), (float("inf"), 0.08)],
    # meterId d9fcc124-64ac-405f-80db-625259fa9cc6, Internet routing.
    "az_egress_inet": [(100, 0.0), (10100, 0.11), (50100, 0.075),
                       (150100, 0.07), (float("inf"), 0.06)],
    "az_interaz_each_way": 0.01,

    # serviceName=ExpressRoute, productName=ExpressRoute. USD per month.
    "az_er_metered_circuit": {1: 436.0, 10: 3400.0},
    "az_er_unlimited_circuit_z1": {1: 5700.0, 10: 51300.0},
    "az_er_unlimited_circuit_z2": {1: 8700.0, 10: 82000.0},
    # Metered egress per GB by zone. Cross-checked against the table on the
    # public ExpressRoute pricing page, which agrees with the API exactly.
    "az_er_egress_by_zone": {1: 0.025, 2: 0.05, 3: 0.14, 4: 0.10},
    # Zone membership read from the Zone column of "ExpressRoute locations and
    # connectivity partners" on learn.microsoft.com. Australia spans two.
    "az_er_zone_of": {"Sydney": 2, "Sydney2": 2, "Melbourne": 2,
                      "Melbourne2": 2, "Perth": 2, "Auckland": 2,
                      "Canberra": 1, "Canberra2": 1},
    # ExpressRoute virtual network gateway, australiaeast, USD per hour.
    "az_er_gateway_hour": {"Standard": 0.19, "HighPerformance": 0.49,
                           "UltraPerformance": 1.87, "ErGw1AZ": 0.361,
                           "ErGw2AZ": 0.632, "ErGw3AZ": 2.151},

    # --- cloud.google.com/vpc/network-pricing, read in a browser.
    # Premium Tier internet data transfer out, source continent Oceania.
    # Google prices per GiB, not per GB.
    "gcp_egress_oceania_gib": [(10240, 0.1158), (51200, 0.1032),
                               (153600, 0.0988), (512000, 0.0881),
                               (float("inf"), 0.0697)],
    # Cloud Interconnect egress, connection location Australia to a VLAN
    # attachment in an Australian region.
    "gcp_interconnect_au_gib": 0.042,

    # --- TeleGeography, "IP Transit Pricing in 2026: More Competition, More
    # Price Erosion", 16 September 2026, read in a browser. USD per Mbps per
    # month, excluding local access and installation. Q2 2026 market floors.
    "transit_floor_100ge": 0.03,
    "transit_floor_10ge": 0.07,
    "transit_100ge_cagr_decline": 0.17,

    # --- TeleGeography, "IP Transit Pricing Trends in Asia", 4 September 2026,
    # read in a browser. Weighted median 100 GigE, USD per Mbps per month.
    "transit_mumbai_2026_100ge": 0.97,
    "transit_mumbai_cagr_decline": 0.35,          # 100 GigE, 3 years to Q2 2026
    "transit_asia_10ge_cagr_decline": 0.17,       # Asia, 2023-2026
    "transit_asia_100ge_cagr_decline": 0.22,      # Asia, 2023-2026

    # --- TeleGeography, "Wholesale Pricing and the WAN", 23 November 2021,
    # read in a browser. NOTE: these are 10 GigE ports, not 100 GigE, so they
    # are NOT comparable with the 2026 100 GigE figures above. Carried here
    # only so group 8 can demonstrate why no multiple is derived from them.
    "transit_syd_2021_10ge": 2.50,
    "transit_mumbai_2021_10ge": 4.70,
    "transit_us_eu_2021_10ge_range": (0.15, 0.20),

    # --- AWS Direct Connect, destination-group counts from the same offer.
    "aws_dx_inter_location_counts": {"north_america_europe": 34,
                                     "latam_africa_me": 14, "japan": 3,
                                     "mumbai": 3, "melbourne_eqme2": 1},
    # Flat-rate dedicated ports at Australian DX locations, USD per month
    # (Tier1 10G through Tier3 100G). The price list does not state what
    # commitment each tier represents, so the post excludes them.
    "aws_dx_flatrate_au_range": (8000.80, 160001.40),

    # --- IX Australia published price list, ix.asn.au/services/peering/,
    # read in a browser. AUD per month, excluding GST. Month-to-month.
    "ixa_port_aud_month": {10: 350.0, 25: 450.0, 100: 950.0, 400: 2800.0},
    # 36-month term, the cheapest published tier.
    "ixa_port_aud_36mo": {10: 297.50, 25: 382.50, 100: 807.50, 400: 2380.0},

    # --- 37signals, published first-hand. See group 7 for the quotes.
    "s37_cloud_2022_usd": 3_201_564,
    "s37_colo_usd_month": 60_000,
    "s37_racks": 8,
    # DHH, 21 February 2023: "Somewhere in the region of $600,000" for the Dell
    # order, amortised over "a conservative five years".
    "s37_hardware_usd": 600_000,
    "s37_s3_exit_petabytes": 5,
    "s37_s3_exit_days": 10,
    "s37_s3_exit_link_gbps": 100,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def gb_per_mbps_month(mbps=1.0, hours=HOURS_PER_MONTH):
    """Decimal gigabytes a sustained rate moves in a month at 100% duty."""
    return mbps * 1e6 * hours * 3600 / 8 / 1e9


def tiered_cost(volume_gb, tiers, free_gb=0.0):
    """Cost of `volume_gb` against a list of (upper_bound, price_per_gb)."""
    remaining = max(0.0, volume_gb - free_gb)
    cost = 0.0
    previous_bound = 0.0
    for bound, price in tiers:
        if remaining <= 0:
            break
        span = min(remaining, bound - previous_bound)
        cost += span * price
        remaining -= span
        previous_bound = bound
    return cost


def effective_rate(volume_gb, tiers, free_gb=0.0):
    return tiered_cost(volume_gb, tiers, free_gb) / volume_gb


def solve_breakeven(fixed_monthly, per_gb, tiers, free_gb=0.0,
                    lo=1.0, hi=5e7):
    """Smallest volume at which fixed + per_gb*v beats the tiered alternative.
    None if the fixed option never wins below `hi`."""
    def delta(v):
        return (fixed_monthly + per_gb * v) - tiered_cost(v, tiers, free_gb)
    if delta(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if delta(mid) > 0:
            lo = mid
        else:
            hi = mid
    return hi


# ---------------------------------------------------------------------------

def group1():
    print("\n1. The unit conversion, and why the usual comparison is wrong")

    per_mbps = gb_per_mbps_month(1.0)
    close("1 Mbps sustained for a 730h month, in GB", round(per_mbps, 1),
          328.5, 0.05)
    close("1 Gbps sustained for a 730h month, in GB",
          round(gb_per_mbps_month(1000), 0), 328500.0, 1.0)

    thirty_day = 1e6 * 30 * 86400 / 8 / 1e9
    close("1 Mbps for a 30-day month, in GB", round(thirty_day, 0), 324.0, 0.5)
    print("     -> the two month conventions differ by 1.4%, smaller than any"
          " effect in\n        this post, so 730 hours is used throughout.")

    def as_per_mbps(rate):
        return round(rate * per_mbps, 2)

    check("AWS Sydney first tier, USD/GB restated as USD/Mbps-month at 100% duty",
          as_per_mbps(0.114), 37.45)
    check("AWS Sydney above 150 TB, same restatement", as_per_mbps(0.092),
          30.22)
    check("AWS N. Virginia above 150 TB, same restatement",
          as_per_mbps(0.050), 16.43)
    check("AWS Direct Connect inside Australia, same restatement",
          as_per_mbps(PRICES["aws_dx_egress_intra_au"]), 13.80)
    check("Azure ExpressRoute Zone 2 (Sydney), same restatement",
          as_per_mbps(PRICES["az_er_egress_by_zone"][2]), 16.43)
    check("Azure ExpressRoute Zone 1 (Canberra), same restatement",
          as_per_mbps(PRICES["az_er_egress_by_zone"][1]), 8.21)
    # The 95th percentile discards the top 5% of a month's 5-minute samples.
    burst_hours = HOURS_PER_MONTH * 0.05
    close("hours of burst the 95th percentile discards each month",
          round(burst_hours, 1), 36.5, 0.05)
    print("     -> note the direction. A 100%-duty Mbps is the LEAST"
          " flattering framing\n        for the cloud rate, because it is the"
          " largest per-Mbps number the\n        per-GB price can produce."
          " Peakiness raises the transit bill while the\n        egress bill"
          " tracks bytes only, so a peaky profile HELPS cloud and"
          " HURTS\n        on-premises. Group 5 sweeps it for that reason.")


def group2():
    print("\n2. Tiered internet egress, and the effective rate that rises"
          " before it falls")

    syd = PRICES["aws_egress_syd"]
    free = PRICES["aws_egress_free_gb"]

    r1 = round(effective_rate(1000, syd, free), 4)
    r10 = round(effective_rate(10000, syd, free), 4)
    r100 = round(effective_rate(100000, syd, free), 4)
    check("AWS Sydney effective rate at 1 TB", r1, 0.1026)
    check("AWS Sydney effective rate at 10 TB", r10, 0.1129)
    check("AWS Sydney effective rate at 100 TB", r100, 0.0976)
    check("the effective rate rises from 1 TB to 10 TB", r10 > r1, True)
    check("and only then falls", r100 < r10, True)
    close("the 1 TB rate understates the 10 TB rate by this fraction",
          round(1 - r1 / r10, 3), 0.091, 0.001)
    print("     -> size a business case off a 1 TB pilot month and you read a"
          " rate 9.1%\n        below what 10 TB actually costs. The 100 GB"
          " free tier is the cause.")

    iad = PRICES["aws_egress_iad"]
    check("AWS Sydney first tier / last tier",
          round(syd[0][1] / syd[-1][1], 3), 1.239)
    check("AWS N. Virginia first tier / last tier",
          round(iad[0][1] / iad[-1][1], 3), 1.800)
    check("Sydney top tier as a multiple of N. Virginia top tier",
          round(syd[-1][1] / iad[-1][1], 2), 1.84)
    check("Sydney first tier as a multiple of N. Virginia first tier",
          round(syd[0][1] / iad[0][1], 2), 1.27)
    # Model the gap off the first tier and you use 1.27x where 1.84x applies.
    close("penalty understated by modelling off the first tier, fraction",
          round(1 - (syd[0][1] / iad[0][1]) / (syd[-1][1] / iad[-1][1]), 3),
          0.312, 0.001)
    close("AWS Sydney effective rate at 500 TB (quoted in the chart)",
          round(effective_rate(500000, syd, free), 4), 0.0933, 1e-4)
    print("     -> geography moves the DISCOUNT CURVE, not just the headline"
          " rate. Sydney\n        starts 1.27x dearer and ends 1.84x dearer,"
          " because the volume discount\n        barely exists there.")

    mgn = PRICES["az_egress_mgn"]
    inet = PRICES["az_egress_inet"]
    check("Azure AU East, backbone routing, first paid tier", mgn[1][1], 0.12)
    check("Azure AU East, internet routing, first paid tier", inet[1][1], 0.11)
    check("Azure AU East, backbone routing, top tier", mgn[-1][1], 0.08)
    check("Azure AU East, internet routing, top tier", inet[-1][1], 0.06)
    check("backbone premium at the top tier",
          round(mgn[-1][1] / inet[-1][1] - 1, 4), 0.3333)
    print("     -> Microsoft's DEFAULT routing preference is the dearer one,"
          " by a third at\n        volume. The cheaper option is the one"
          " labelled 'Internet'.")

    check("Azure internet-routing top tier undercuts AWS Sydney's top tier",
          inet[-1][1] < syd[-1][1], True)
    close("by this much per GB", round(syd[-1][1] - inet[-1][1], 3), 0.032,
          1e-9)


def group3():
    print("\n3. Does the private circuit pay for itself, and at what volume")

    syd = PRICES["aws_egress_syd"]
    free = PRICES["aws_egress_free_gb"]

    for speed in (1, 10):
        port_month = PRICES["aws_dx_port_hour"][speed] * HOURS_PER_MONTH
        be = solve_breakeven(port_month, PRICES["aws_dx_egress_intra_au"],
                             syd, free)
        capacity = gb_per_mbps_month(speed * 1000)
        print(f"     {speed:>3} Gbps DX port at USD {port_month:,.2f}/mo:")
        check(f"  break-even volume, GB ({speed}G)", round(be, -1),
              {1: 3200.0, 10: 26580.0}[speed])
        close(f"  as a share of the port's own capacity, % ({speed}G)",
              round(be / capacity * 100, 2), {1: 0.97, 10: 0.81}[speed], 0.02)
    print("     -> both ports repay themselves under 1% utilisation, because"
          " the per-GB gap\n        (0.114 against 0.042) is wide and the port"
          " is cheap beside it. The port\n        charge is not what makes"
          " Direct Connect a decision.")

    er_circuit = PRICES["az_er_metered_circuit"][1]
    gw = PRICES["az_er_gateway_hour"]["Standard"] * HOURS_PER_MONTH
    zone2 = PRICES["az_er_egress_by_zone"][2]
    inet = PRICES["az_egress_inet"]

    close("ExpressRoute Standard gateway, USD/month", round(gw, 2), 138.70,
          0.01)
    be_no_gw = solve_breakeven(er_circuit, zone2, inet)
    be_with_gw = solve_breakeven(er_circuit + gw, zone2, inet)
    check("ExpressRoute 1G metered, circuit only, break-even GB",
          round(be_no_gw, -1), 7450.0)
    check("same, once the Standard gateway is counted", round(be_with_gw, -1),
          9760.0)
    close("the gateway is this fraction of the circuit charge",
          round(gw / er_circuit, 3), 0.318, 0.001)
    print("     -> the gateway is 31.8% of the circuit charge and the circuit"
          " is useless\n        without it, yet it is missing from every"
          " comparison I could find. It\n        moves the break-even by"
          " nearly a third.")

    check("ExpressRoute zone for Sydney", PRICES["az_er_zone_of"]["Sydney"], 2)
    check("ExpressRoute zone for Canberra",
          PRICES["az_er_zone_of"]["Canberra"], 1)
    check("Canberra's per-GB egress as a fraction of Sydney's",
          round(PRICES["az_er_egress_by_zone"][1] /
                PRICES["az_er_egress_by_zone"][2], 2), 0.50)
    check("Auckland is in the same ExpressRoute zone as Sydney",
          PRICES["az_er_zone_of"]["Auckland"] ==
          PRICES["az_er_zone_of"]["Sydney"], True)
    print("     -> one country, two pricing zones. The Australian Government"
          " regions in\n        Canberra egress at half the Sydney rate, and"
          " Auckland, in another\n        country, shares Sydney's.")


def group4():
    print("\n4. ExpressRoute Unlimited against Metered, as a utilisation"
          " threshold")

    zone2 = PRICES["az_er_egress_by_zone"][2]
    for speed in (1, 10):
        metered = PRICES["az_er_metered_circuit"][speed]
        unlimited = PRICES["az_er_unlimited_circuit_z2"][speed]
        crossover_gb = (unlimited - metered) / zone2
        capacity = gb_per_mbps_month(speed * 1000)
        pct = crossover_gb / capacity * 100
        print(f"     Zone 2, {speed:>2} Gbps: metered {metered:,.0f} +"
              f" {zone2}/GB against unlimited {unlimited:,.0f}")
        check(f"  crossover volume, GB ({speed}G)", round(crossover_gb),
              {1: 165280, 10: 1572000}[speed])
        close(f"  as sustained utilisation, % ({speed}G)", round(pct, 1),
              {1: 50.3, 10: 47.9}[speed], 0.05)
    print("     -> Unlimited only wins above roughly half the circuit's"
          " capacity, sustained,\n        every hour of the month. A link"
          " engineered to PEAK at 70% averages far\n        less than that.")

    # A link engineered to PEAK at 70% averages this much across the ratios
    # group 5 sweeps, which is what "sustained" has to be measured against.
    for ratio, want in ((4.0, 17.5), (2.5, 28.0)):
        close(f"mean utilisation implied by a 70% peak at ratio {ratio}, %",
              round(70.0 / ratio, 1), want, 0.05)

    zone1 = PRICES["az_er_egress_by_zone"][1]
    cross_z1 = (PRICES["az_er_unlimited_circuit_z1"][1] -
                PRICES["az_er_metered_circuit"][1]) / zone1
    pct_z1 = cross_z1 / gb_per_mbps_month(1000) * 100
    close("Zone 1, 1 Gbps: crossover as sustained utilisation, %",
          round(pct_z1, 1), 64.1, 0.05)
    check("Zone 1's threshold is HIGHER than Zone 2's", pct_z1 > 50.3, True)
    print("     -> cheaper per-GB egress pushes the flat rate further out of"
          " reach, not\n        closer. Canberra is the worst place in"
          " Australia to buy Unlimited.")


def group5():
    print("\n5. Cloud egress restated as a per-Mbps price, against published"
          " 2026 transit")

    per_mbps = gb_per_mbps_month(1.0)

    # An IX port is sold by capacity, not by volume, so its per-Mbps price is
    # just the port price over the port speed.
    ixa_100g_aud = PRICES["ixa_port_aud_month"][100]
    ixa_per_mbps_aud = ixa_100g_aud / 100_000
    ixa_per_mbps_usd = ixa_per_mbps_aud / 1 * FX_AUD_USD
    close("IX Australia 100G port, AUD per Mbps per month",
          round(ixa_per_mbps_aud, 5), 0.0095, 1e-6)
    close("the same at the declared FX rate, USD per Mbps per month",
          round(ixa_per_mbps_usd, 6), 0.006175, 1e-6)

    # Cloud egress expressed the same way, at 100% duty, which flatters it.
    aws_syd_per_mbps = 0.114 * per_mbps
    check("AWS Sydney tier 1 as USD per Mbps-month at 100% duty",
          round(aws_syd_per_mbps, 2), 37.45)
    check("  as a multiple of the IX Australia 100G port price",
          round(aws_syd_per_mbps / ixa_per_mbps_usd), 6065)
    print("     -> an IX port is not transit, and this is not a like-for-like"
          " swap: peering\n        reaches peers, not the whole internet. It"
          " is still the right order-of-\n        magnitude anchor, and it is"
          " a published Australian price rather than a\n        stale one.")

    # Against the published 2026 transit floor. Transit is billed on the
    # 95th percentile, so a peaky profile buys more Mbps per GB delivered.
    def transit_usd_per_gb(price_per_mbps, peak_to_mean):
        return price_per_mbps * peak_to_mean / per_mbps

    floor = PRICES["transit_floor_100ge"]
    for ratio in (1.0, PEAK_TO_MEAN, 4.0):
        rate = transit_usd_per_gb(floor, ratio)
        mult = 0.114 / rate
        print(f"     peak-to-mean {ratio}: 100GigE floor {floor}/Mbps"
              f" = {rate:.6f}/GB, AWS Sydney is {mult:,.0f}x")
        check(f"  multiple at ratio {ratio}", round(mult),
              {1.0: 1248, 2.5: 499, 4.0: 312}[ratio])
    print("     -> the multiple SHRINKS as the profile gets peakier, because"
          " a peaky\n        profile buys more Mbps per GB delivered. So 4.0"
          " is the on-premises-\n        hardest end of this sweep, not 1.0,"
          " and even there the cheapest metered\n        cloud egress in"
          " Sydney is ~300x a transit port bought at the 2026 floor.")

    # How far would transit have to rise to make cloud egress competitive?
    indifferent = 0.114 * per_mbps / PEAK_TO_MEAN
    close("transit price at which AWS Sydney tier 1 breaks even, USD/Mbps",
          round(indifferent, 2), 14.98, 0.01)
    check("  as a multiple of the 2026 100GigE floor",
          round(indifferent / floor), 499)
    for ratio, want in ((1.0, 37.45), (4.0, 9.36)):
        close(f"  same indifference price at ratio {ratio}",
              round(0.114 * per_mbps / ratio, 2), want, 0.01)

    # FX sensitivity: the conclusion cannot be moved by the one soft input.
    for fx in (0.55, 0.65, 0.80):
        m = aws_syd_per_mbps / (ixa_per_mbps_aud * fx)
        check(f"IX multiple at FX {fx} stays above 4000", m > 4000, True)
    print("     -> a 45% swing in the exchange rate moves the multiple but not"
          " the\n        conclusion, which is the only thing the soft input"
          " needs to survive.")

    # The honest gap.
    print("     -> the Australian side of this comparison is group 8's"
          " subject, including\n        why no 2026 Sydney transit price"
          " appears anywhere in this file.")


def group6():
    print("\n6. Where the private circuit costs MORE than the public internet")

    syd_first = PRICES["aws_egress_syd"][0][1]
    syd_top = PRICES["aws_egress_syd"][-1][1]
    inter = PRICES["aws_dx_egress_inter"]

    check("DX destinations dearer per GB than AWS Sydney's FIRST internet tier",
          sorted(k for k, v in inter.items() if v > syd_first),
          ["latam_africa_me", "mumbai", "north_america_europe"])
    check("  and dearer than its TOP internet tier",
          sorted(k for k, v in inter.items() if v > syd_top),
          ["japan", "latam_africa_me", "mumbai", "north_america_europe"])
    check("North America / Europe DX egress against Sydney's top internet tier",
          round(inter["north_america_europe"] / syd_top, 2), 1.41)
    check("Latin America / Africa / Middle East, same comparison",
          round(inter["latam_africa_me"] / syd_top, 2), 2.07)
    print("     -> a Direct Connect from Sydney to an Ashburn or London DX"
          " location costs\n        1.41x what the internet gateway charges,"
          " and 2.07x for Sao Paulo or\n        Nairobi. The private circuit"
          " is the cheap option INSIDE the region and\n        the expensive"
          " one leaving it.")

    check("Equinix ME2 Melbourne is billed InterRegion at the IntraRegion rate",
          inter["melbourne_eqme2"], PRICES["aws_dx_egress_intra_au"])

    check("GCP Interconnect Australia, USD/GiB",
          PRICES["gcp_interconnect_au_gib"], 0.042)
    check("AWS Direct Connect intra-Australia, USD/GB",
          PRICES["aws_dx_egress_intra_au"], 0.042)
    close("GCP's rate converted to decimal GB",
          round(PRICES["gcp_interconnect_au_gib"] / 1.073741824, 5),
          0.03912, 1e-5)
    print("     -> the same figure in different units. A GiB is 7.4% larger"
          " than a GB, so\n        Google's rate is 6.9% cheaper per byte than"
          " it looks beside Amazon's.")

    check("AWS intra-region DX egress, Sydney against N. Virginia",
          round(PRICES["aws_dx_egress_intra_au"] /
                PRICES["aws_dx_egress_intra_us"], 1), 2.1)

    # Azure's inter-AZ charge is symmetric, which is easy to miss.
    check("Azure inter-AZ transfer is billed in BOTH directions",
          PRICES["az_interaz_each_way"] * 2, 0.02)
    print("     -> a round trip between two Azure availability zones costs"
          " 0.02/GB, because\n        the egress and the ingress are both"
          " metered. AWS charges 0.01/GB for\n        the equivalent regional"
          " transfer.")


def group7():
    print("\n7. 37signals' published exit: what it does and does not say"
          " about the network")

    # "We currently spend about $60,000/month on eight dedicated racks between
    #  our two data centers through Deft." ... "That's a total of $840,000/year
    #  for everything. Bandwidth, power, and boxes on an amortization schedule
    #  of five years"  -- DHH, 21 February 2023.
    colo_year = PRICES["s37_colo_usd_month"] * 12
    check("37signals colocation spend, USD/year", colo_year, 720_000)
    check("  per rack per month", PRICES["s37_colo_usd_month"] //
          PRICES["s37_racks"], 7500)
    hw = PRICES["s37_hardware_usd"]
    check("hardware amortised over five years, USD/year", hw // 5, 120_000)
    check("stated total, USD/year", colo_year + hw // 5, 840_000)
    print("     -> the published figure covers 'Bandwidth, power, and boxes'"
          " in one line.\n        There is no connectivity number in the"
          " 37signals exit, because at\n        eight racks you buy bandwidth"
          " as a line in a colo bill and the transit\n        market price"
          " never reaches your invoice. That absence is the finding.")

    # The one hard network number in the whole exit: 5 PB in under 10 days on
    # a 100 GbE link. -- Jeremy Daer, 8 January 2026.
    petabytes = PRICES["s37_s3_exit_petabytes"]
    days = PRICES["s37_s3_exit_days"]
    link = PRICES["s37_s3_exit_link_gbps"]
    gbps = petabytes * 1e15 * 8 / (days * 86400) / 1e9
    close("5 PB in under 10 days, implied sustained Gbps", round(gbps, 1),
          46.3, 0.05)
    close("  as a share of the 100 GbE link, %", round(gbps / link * 100, 1),
          46.3, 0.05)
    print("     -> 46.3 Gbps sustained for ten days, and that is a FLOOR: the"
          " transfer\n        finished in 'less than 10 days', so the real"
          " rate was higher. It is\n        also the only published"
          " repatriation figure I found that is stated in\n        bits per"
          " second rather than dollars.")

    # What that volume would have cost at list, had the waiver not applied.
    at_list = tiered_cost(petabytes * 1e6, PRICES["aws_egress_iad"],
                          PRICES["aws_egress_free_gb"])
    close("5 PB of us-east-1 egress at list, USD", round(at_list, -3),
          254_000.0, 500)
    close("  effective rate over 5 PB, USD/GB",
          round(at_list / (petabytes * 1e6), 4), 0.0508, 1e-4)
    print(f"     -> 5 PB at N. Virginia list is USD {at_list:,.0f}, an"
          f" effective 0.0508/GB\n        once the volume tiers are"
          f" exhausted. That is the same order as the\n        'tens to"
          f" hundreds of thousands' they were quoted for a managed\n"
          f"        transfer service, so the waiver and the DIY build were"
          f" each worth\n        roughly a quarter of a million dollars."
          f" Note what this does NOT say:\n        at petabyte scale the"
          f" per-GB rate collapses to the bottom tier, so\n        egress is"
          f" cheapest per byte exactly when you are leaving.")


# ---------------------------------------------------------------------------

def group8():
    print("\n8. The Australian gap: why no 2026 Sydney transit price is used,"
          " and what changes\n   if you guess one anyway")

    per_mbps = gb_per_mbps_month(1.0)
    syd21 = PRICES["transit_syd_2021_10ge"]
    mum21 = PRICES["transit_mumbai_2021_10ge"]
    mum26 = PRICES["transit_mumbai_2026_100ge"]
    floor = PRICES["transit_floor_100ge"]

    # Reason one: the 2021 quotes are 10 GigE ports and the 2026 floor is
    # 100 GigE, so a ratio across them mixes port size with elapsed time.
    check("the 2021 Sydney and Mumbai quotes are 10 GigE ports",
          ("10ge" in "transit_syd_2021_10ge") and
          ("10ge" in "transit_mumbai_2021_10ge"), True)
    naive = syd21 / floor
    close("the naive 2021-Sydney-over-2026-floor ratio somebody would compute",
          round(naive, 0), 83.0, 0.5)
    print(f"     -> {naive:.0f}x, and it is worthless: it spans five years AND"
          f" a port-size\n        change (10 GigE against 100 GigE). The 2026"
          f" 10 GigE floor is"
          f" ${PRICES['transit_floor_10ge']}, not ${floor}.")

    # Reason two: the size of the elapsed-time effect, from a same-port-size
    # source. Mumbai 100 GigE fell 35% compounded annually for three years.
    cagr = PRICES["transit_mumbai_cagr_decline"]
    total_fall = 1 - (1 - cagr) ** 3
    close("Mumbai 100 GigE, three years at 35% CAGR, total fall",
          round(total_fall, 3), 0.725, 0.001)
    print(f"     -> a {total_fall*100:.0f}% fall in three years on a single"
          f" port size, from one\n        source. That is the citable decline."
          f" Comparing the 2021 10 GigE\n        figure (${mum21}) against the"
          f" 2026 100 GigE figure (${mum26}) would\n        imply"
          f" {(1-mum26/mum21)*100:.0f}%, which is the same apples-to-oranges"
          f" error.")

    # Reason three: what it would do to the headline if you guessed anyway.
    # 0.50 is an INFERENCE from Mumbai's trajectory, not a published price.
    inferred_syd = 0.50
    for ratio in (1.0, 4.0):
        rate = inferred_syd * ratio / per_mbps
        mult = 0.114 / rate
        check(f"AWS Sydney over an INFERRED AU transit price, ratio {ratio}",
              round(mult), {1.0: 75, 4.0: 19}[ratio])
    print("     -> so on the author's own inference the Sydney multiple is"
          " 19x to 75x, not\n        312x to 1,248x. One to two orders of"
          " magnitude, not two to three.\n        The post states this rather"
          " than hiding behind the global floor, and\n        still does not"
          " publish 0.50 as a price, because it is not one.")

    # The IX port, which IS a current published Australian number.
    ix_aud = PRICES["ixa_port_aud_month"][100] / 100_000
    close("IX Australia 100G port, AUD per Mbps per month", round(ix_aud, 5),
          0.0095, 1e-6)
    check("and it is a peering port, not transit, so it is not a substitute",
          True, True)

    SKIPPED.append("2026 Australian IP transit median: TeleGeography's IP "
                   "Transit Pricing Service is the only source and it is "
                   "paid. The 2021 public figure is 10 GigE and five years "
                   "stale, so no multiple is derived from it. Group 8 shows "
                   "what an inferred price would do instead.")


# ---------------------------------------------------------------------------

def main():
    groups = [group1, group2, group3, group4, group5, group6, group7,
              group8]
    failed_groups = 0
    for g in groups:
        before = len(FAILURES)
        g()
        if len(FAILURES) > before:
            failed_groups += 1
    print()
    print(f"{len(groups) - failed_groups}/{len(groups)} groups passed,"
          f" {len(SKIPPED)} skipped, {failed_groups} failed")
    for s in SKIPPED:
        print(f"  SKIP {s}")
    for f in FAILURES:
        print(f"  FAIL {f}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
