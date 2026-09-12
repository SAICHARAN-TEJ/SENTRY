"""Scene ingestion: register Sentinel-2 L2A scenes and their band objects."""

from __future__ import annotations

from typing import Any

from backend import db

BANDS = ["B02", "B03", "B04", "B08"]
DEFAULT_SOURCE = ("sentinel-2-l2a", "s2-processing-baseline-04.00")


def register_scene(provider_product_id: str, band_object_keys: dict[str, str],
                   footprint_wkt_4326: str, sensing_time: Any, cloud_pct: float | None,
                   crs: str, resolution_m: float,
                   source_name: str = DEFAULT_SOURCE[0],
                   source_version: str = DEFAULT_SOURCE[1]) -> dict:
    """Idempotently register a scene + its 4 band objects (FR-01).

    Identity = (dataset_source, provider_product_id); band rows are refreshed
    on re-registration so object keys/checksums stay current.
    """
    source = db.query(
        "select id from dataset_sources where name = %s and version = %s",
        (source_name, source_version), one=True)
    if source is None:
        source = db.query(
            """
            insert into dataset_sources (name, version, source_type, provider, uri)
            values (%s, %s, 'satellite-l2a', 'copernicus',
                    'https://dataspace.copernicus.eu')
            returning id
            """,
            (source_name, source_version), one=True)

    scene = db.query(
        """
        insert into scenes (dataset_source_id, provider_product_id, sensing_time,
                             ingest_status, crs, resolution_m, footprint, cloud_pct)
        values (%s, %s, %s, 'ready', %s, %s, ST_GeomFromText(%s, 4326), %s)
        on conflict (dataset_source_id, provider_product_id) do update
            set sensing_time = excluded.sensing_time,
                cloud_pct = excluded.cloud_pct,
                ingest_status = 'ready'
        returning id
        """,
        (source["id"], provider_product_id, sensing_time, crs, resolution_m,
         footprint_wkt_4326, cloud_pct), one=True)

    db.execute("delete from scene_bands where scene_id = %s", (scene["id"],))
    band_ids = []
    for band in BANDS:
        row = db.query(
            """
            insert into scene_bands (scene_id, band_name, native_resolution_m,
                                    object_key, scale_factor, dtype)
            values (%s, %s, %s, %s, 0.0001, 'uint16') returning id
            """,
            (scene["id"], band, resolution_m, band_object_keys.get(band)), one=True)
        band_ids.append(row["id"])

    return {"scene_id": scene["id"], "band_ids": band_ids}
