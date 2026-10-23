"""A small, careful Socrata client.

Two features matter for this project and neither is in the convenience
wrappers: server-side aggregation and honest pagination.

The origin-destination dataset holds 116 million rows, which is far too large
to download. But Socrata will evaluate a `$group` on the server: the full
annual station-pair flow matrix comes back from one grouped query in about 40
seconds. So the rule here is to push aggregation to the server and pull only
what is actually needed.
"""
from __future__ import annotations

import logging
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from ..config import APP_TOKEN, DOMAINS, RAW_DIR

log = logging.getLogger(__name__)

PAGE = 50_000
MAX_RETRIES = 5


def _headers() -> dict:
    return {"X-App-Token": APP_TOKEN} if APP_TOKEN else {}


def _get(url: str, params: dict, timeout: int) -> requests.Response:
    """GET with exponential backoff on transient failures."""
    delay = 2.0
    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, headers=_headers(), timeout=timeout)
        except requests.RequestException as exc:
            last = exc
        else:
            if r.status_code == 200:
                return r
            # 202 means Socrata is still materialising the query; 429/5xx are
            # transient. Anything else is a real error worth surfacing.
            if r.status_code not in (202, 429, 500, 502, 503, 504):
                raise RuntimeError(f"{url} -> HTTP {r.status_code}: {r.text[:300]}")
            last = RuntimeError(f"HTTP {r.status_code}")
        if attempt < MAX_RETRIES - 1:
            log.info("retry %d/%d after %.0fs (%s)", attempt + 1, MAX_RETRIES, delay, last)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"{url} failed after {MAX_RETRIES} attempts: {last}")


def query(domain: str, dataset: str, select: str | None = None,
          where: str | None = None, group: str | None = None,
          order: str | None = None, limit: int | None = None,
          paginate: bool = True, timeout: int = 300) -> pd.DataFrame:
    """Run one SoQL query, paging through the result when needed."""
    host = DOMAINS.get(domain, domain)
    url = f"https://{host}/resource/{dataset}.json"
    base: dict = {}
    if select:
        base["$select"] = select
    if where:
        base["$where"] = where
    if group:
        base["$group"] = group
    if order:
        base["$order"] = order

    if not paginate:
        params = dict(base, **({"$limit": limit} if limit else {}))
        return pd.DataFrame(_get(url, params, timeout).json())

    frames: list[pd.DataFrame] = []
    got = 0
    offset = 0
    page = min(PAGE, limit) if limit else PAGE
    while True:
        params = dict(base, **{"$limit": page, "$offset": offset})
        # A grouped query needs a deterministic order for paging to be stable.
        if group and not order:
            params["$order"] = group.split(",")[0].strip()
        rows = _get(url, params, timeout).json()
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        got += len(rows)
        offset += page
        log.info("%s: %d rows", dataset, got)
        if len(rows) < page or (limit and got >= limit):
            break
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    return out.head(limit) if limit else out


def export_csv(domain: str, dataset: str, select: str | None = None,
               where: str | None = None, group: str | None = None,
               order: str | None = None, limit: int = 500_000,
               timeout: int = 900) -> pd.DataFrame:
    """Pull a whole result set in ONE request from the CSV endpoint.

    This exists because paginating an aggregate query is a trap. Socrata
    re-evaluates the GROUP BY for every page, so walking the 116-million-row
    origin-destination table 50,000 rows at a time costs a full aggregation per
    page and, in practice, eventually loses the connection. The CSV endpoint
    accepts a `$limit` far above the 50,000-row JSON page cap, so the entire
    177,998-row weekday flow matrix arrives in a single response instead.
    """
    host = DOMAINS.get(domain, domain)
    url = f"https://{host}/resource/{dataset}.csv"
    params: dict = {"$limit": limit}
    if select:
        params["$select"] = select
    if where:
        params["$where"] = where
    if group:
        params["$group"] = group
    if order:
        params["$order"] = order
    r = _get(url, params, timeout)
    df = pd.read_csv(StringIO(r.text), low_memory=False)
    if len(df) >= limit:
        log.warning("%s returned exactly the limit (%d rows); results may be "
                    "truncated, raise `limit`", dataset, limit)
    return df


def count(domain: str, dataset: str, where: str | None = None,
          timeout: int = 300) -> int:
    df = query(domain, dataset, select="count(*) as n", where=where,
               paginate=False, timeout=timeout)
    if df.empty:
        return 0
    return int(df.iloc[0, 0])


def cached_query(name: str, domain: str, dataset: str, raw_dir: Path = RAW_DIR,
                 force: bool = False, via_csv: bool = False,
                 **kw) -> pd.DataFrame:
    """Query once, keep the parquet, reuse it afterwards."""
    dest = raw_dir / f"{name}.parquet"
    if dest.exists() and not force:
        log.info("have %s", dest.name)
        return pd.read_parquet(dest)
    df = export_csv(domain, dataset, **kw) if via_csv else query(domain, dataset, **kw)
    if df.empty:
        log.warning("%s returned no rows", name)
        return df
    df.to_parquet(dest, index=False)
    log.info("cached %s (%d rows)", dest.name, len(df))
    return df
