"""Google Data Commons: population and demographic statistics for denominators.

Layer 5 provider for prevalence, carrier frequency, and demographic denominators.
Does not hold cystic fibrosis or sickle cell registry data; see admission review
(cf-research/proposals/2026-10-04-datacommons-admission.md, board T-0048).
"""

from __future__ import annotations

import os

from ..http import Client
from ..record import Evidence, Status

PROVIDER = "datacommons/0.1"
SOURCE = "datacommons"
DEFAULT_VARIABLE = "Count_Person"

LIMITATION = (
    "Google Data Commons aggregate statistical observation. Provides population or demographic "
    "denominators only; not an individual-level record or clinical disease registry. Underlying source "
    "and measurement method are from Data Commons provenance."
)


def parse_observation(
    data: dict, entity: str, variable: str, question: str, url: str, year: str | None = None
) -> Evidence:
    by_var = data.get("byVariable") or {}
    var_data = by_var.get(variable) or {}
    by_entity = var_data.get("byEntity") or {}
    entity_data = by_entity.get(entity) or {}
    facets_meta = data.get("facets") or {}

    ordered_facets = entity_data.get("orderedFacets") or []
    if not ordered_facets:
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"entity": entity, "variable": variable, "year": year},
            limitations="No observations found in Data Commons for this entity and variable.",
        )

    # First facet is primary/highest ranking facet from Data Commons v2
    facet = ordered_facets[0]
    facet_id = facet.get("facetId")
    f_meta = facets_meta.get(facet_id) or {}
    observations = facet.get("observations") or []

    if not observations:
        return Evidence(
            status=Status.NOT_FOUND,
            question=question,
            source_id=SOURCE,
            url=url,
            provider=PROVIDER,
            fields={"entity": entity, "variable": variable, "year": year},
            limitations="No observation points returned for this entity in Data Commons.",
        )

    matched_obs = None
    if year:
        for obs in reversed(observations):
            obs_str = str(obs.get("date") or "")
            if obs_str == str(year) or obs_str.startswith(str(year)):
                matched_obs = obs
                break
        if not matched_obs:
            return Evidence(
                status=Status.NOT_FOUND,
                question=question,
                source_id=SOURCE,
                url=url,
                provider=PROVIDER,
                fields={
                    "entity": entity,
                    "variable": variable,
                    "year": year,
                    "available_dates": [o.get("date") for o in observations[-5:]],
                },
                limitations=f"No observation found for year {year} in Data Commons.",
            )
    else:
        # Latest observation
        matched_obs = observations[-1]

    obs_date = str(matched_obs.get("date")) if matched_obs.get("date") is not None else None
    val = matched_obs.get("value")

    method = f_meta.get("measurementMethod")
    lim_parts = [LIMITATION]
    if method:
        lim_parts.append(f"Underlying measurement method: {method}.")
    if obs_date:
        lim_parts.append(f"Observation date: {obs_date}.")
    limitations_text = " ".join(lim_parts)

    return Evidence(
        status=Status.FOUND,
        question=question,
        source_id=SOURCE,
        url=url,
        provider=PROVIDER,
        publisher_date=obs_date,
        fields={
            "entity": entity,
            "variable": variable,
            "value": val,
            "date": obs_date,
            "measurement_method": method,
            "observation_period": f_meta.get("observationPeriod"),
            "provenance_url": f_meta.get("provenanceUrl"),
            "provenance_id": f_meta.get("provenanceId"),
        },
        limitations=limitations_text,
    )


def observation(
    client: Client, entity: str, variable: str = DEFAULT_VARIABLE, year: str | None = None
) -> Evidence:
    q = f"What is {variable} for {entity}" + (f" in {year}" if year else "") + " in Data Commons?"
    key = os.environ.get("DC_API_KEY")
    if not key or key == "your_key_here":
        return Evidence(
            status=Status.BLOCKED,
            question=q,
            source_id=SOURCE,
            url=client._url(SOURCE, "observation"),
            provider=PROVIDER,
            fields={"error": "DC_API_KEY is not set in environment or .env"},
            limitations="API key required for Data Commons API (https://apikeys.datacommons.org). Add DC_API_KEY to .env.",
        )

    params = {
        "select": ["variable", "entity", "value", "date"],
        "variable.dcids": variable,
        "entity.dcids": entity,
    }
    headers = {"x-api-key": key}
    f = client.get(SOURCE, "observation", params=params, headers=headers)
    if f.status is not Status.FOUND:
        return Evidence(
            status=f.status,
            question=q,
            source_id=SOURCE,
            url=f.url,
            provider=PROVIDER,
            fields={"http_status": f.http_status, "entity": entity, "variable": variable},
            limitations="Data Commons API request failed; establishes nothing.",
        )
    return parse_observation(f.data or {}, entity, variable, q, f.url, year=year)
