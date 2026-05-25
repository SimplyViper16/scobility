"""
Populate MySQL DB from a processed scobility JSON snapshot.

Workflow:
  1. Run scobility_scrape.py  →  downloads raw JSON data from the tournament API
  2. Run scobility.py         →  computes spice ratings, produces scobility_<src>_<date>.json
  3. Run this script          →  upserts the Catalog row then loads Charts, Players,
                                  Scores, and Relationships into MySQL

Usage:
    python db_upload.py <catalog_name> <scobility_json_file> [perfect_offset] [perfect_score]

    perfect_offset  small push away from log singularity (default: 0.003, suits all ITL/GS)
    perfect_score   10000 for ITG EX, 1000000 for SMX, omit if scores are already proportional

Examples:
    python db_upload.py ITL2026 ../scobility_itl2026_20260101.json
    python db_upload.py SMX2026 ../scobility_smx2026_20260101.json 0.03 1000000
"""

import json
import os
import sys
from datetime import datetime as dt

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


def engine_construct():
    url = URL.create(
        "mysql+pymysql",
        username=os.environ["SCOBILITY_UID"],
        password=os.environ["SCOBILITY_PWD"],
        host=os.environ["SCOBILITY_SERVER"],
        database=os.environ["SCOBILITY_DATABASE"],
        port=int(os.environ.get("SCOBILITY_PORT", 3306))
    )
    return create_engine(url)


def upload(catalog_name: str, json_path: str,
           perfect_offset: float = 0.003, perfect_score: float = 10000.0):
    engine = engine_construct()

    with open(json_path, 'r', encoding='utf-8') as fp:
        data = json.load(fp)

    now = dt.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    with engine.begin() as conn:

        # ------------------------------------------------------------------ #
        # Catalog — created automatically if it doesn't exist yet             #
        # ------------------------------------------------------------------ #
        conn.execute(text("""
            INSERT INTO Catalog (name, active, perfect_offset, perfect_score)
            VALUES (:name, 1, :perfect_offset, :perfect_score)
            ON DUPLICATE KEY UPDATE
                active         = 1,
                perfect_offset = VALUES(perfect_offset),
                perfect_score  = VALUES(perfect_score),
                last_update    = NOW()
        """), {
            "name":           catalog_name,
            "perfect_offset": perfect_offset,
            "perfect_score":  perfect_score,
        })
        catalog_id = conn.execute(
            text("SELECT catalog_id FROM Catalog WHERE name = :name"),
            {"name": catalog_name}
        ).fetchone()[0]
        print(f"Catalog '{catalog_name}' → id={catalog_id} "
              f"(perfect_offset={perfect_offset}, perfect_score={perfect_score})")

        # ------------------------------------------------------------------ #
        # Charts — bulk insert, then one SELECT to build the ID map           #
        # ------------------------------------------------------------------ #
        songs = data.get('songs', [])
        print(f"\nCharts: inserting/updating {len(songs)} rows...")

        if songs:
            conn.execute(text("""
                INSERT INTO Chart
                    (catalog_id, chart_id, hash, title, subtitle, artist,
                     meter, slot, style, value, value_scoring, value_passing,
                     spice, spice_calc_time)
                VALUES
                    (:catalog_id, :chart_id, :hash, :title, :subtitle, :artist,
                     :meter, :slot, :style, :value, :value_scoring, :value_passing,
                     :spice, :spice_calc_time)
                ON DUPLICATE KEY UPDATE
                    hash            = VALUES(hash),
                    title           = VALUES(title),
                    subtitle        = VALUES(subtitle),
                    artist          = VALUES(artist),
                    meter           = VALUES(meter),
                    slot            = VALUES(slot),
                    style           = VALUES(style),
                    value           = VALUES(value),
                    value_scoring   = VALUES(value_scoring),
                    value_passing   = VALUES(value_passing),
                    spice           = VALUES(spice),
                    spice_calc_time = VALUES(spice_calc_time)
            """), [
                {
                    "catalog_id":      catalog_id,
                    "chart_id":        s['s_id'],
                    "hash":            s['hash'],
                    "title":           s.get('title'),
                    "subtitle":        s.get('subtitle'),
                    "artist":          s.get('artist'),
                    "meter":           s.get('meter'),
                    "slot":            s.get('slot'),
                    "style":           s.get('style'),
                    "value":           s.get('value'),
                    "value_scoring":   s.get('value_scoring'),
                    "value_passing":   s.get('value_passing'),
                    "spice":           s.get('spice'),
                    "spice_calc_time": now if s.get('spice') is not None else None,
                }
                for s in songs
            ])

        # One query to get all chart_id → global_chart_id mappings
        rows = conn.execute(
            text("SELECT chart_id, global_chart_id FROM Chart WHERE catalog_id = :cid"),
            {"cid": catalog_id}
        ).fetchall()
        chart_id_map = {row[0]: row[1] for row in rows}
        print(f"  {len(chart_id_map)} charts ready.")

        # ------------------------------------------------------------------ #
        # Players — bulk insert, then one SELECT to build the ID map          #
        # ------------------------------------------------------------------ #
        players = data.get('players', [])
        print(f"\nPlayers: inserting/updating {len(players)} rows...")

        if players:
            conn.execute(text("""
                INSERT INTO Player
                    (catalog_id, entrant_id, groovestats_id, name,
                     scobility, timing_power, comfort_zone, scobility_calc_time)
                VALUES
                    (:catalog_id, :entrant_id, :groovestats_id, :name,
                     :scobility, :timing_power, :comfort_zone, :scobility_calc_time)
                ON DUPLICATE KEY UPDATE
                    groovestats_id      = VALUES(groovestats_id),
                    name                = VALUES(name),
                    scobility           = VALUES(scobility),
                    timing_power        = VALUES(timing_power),
                    comfort_zone        = VALUES(comfort_zone),
                    scobility_calc_time = VALUES(scobility_calc_time)
            """), [
                {
                    "catalog_id":          catalog_id,
                    "entrant_id":          p['e_id'],
                    "groovestats_id":      p['g_id'],
                    "name":                p.get('name'),
                    "scobility":           p.get('scobility'),
                    "timing_power":        p.get('timing_power'),
                    "comfort_zone":        p.get('comfort_zone'),
                    "scobility_calc_time": now if p.get('scobility') is not None else None,
                }
                for p in players
            ])

        # One query to get all entrant_id → performance_id mappings
        rows = conn.execute(
            text("SELECT entrant_id, performance_id FROM Player WHERE catalog_id = :cid"),
            {"cid": catalog_id}
        ).fetchall()
        perf_id_map = {row[0]: row[1] for row in rows}
        print(f"  {len(perf_id_map)} players ready.")

        # ------------------------------------------------------------------ #
        # Scores — resolve IDs in Python, then bulk insert                    #
        # ------------------------------------------------------------------ #
        scores = data.get('scores', [])
        print(f"\nScores: inserting/updating {len(scores)} rows...")

        score_rows = []
        skipped = 0
        for v in scores:
            gcid = chart_id_map.get(v['s_id'])
            pid  = perf_id_map.get(v['e_id'])
            if gcid is None or pid is None:
                skipped += 1
                continue
            score_rows.append({
                "catalog_id":      catalog_id,
                "global_chart_id": gcid,
                "performance_id":  pid,
                "plays":           v.get('plays'),
                "last_played":     v.get('last_played'),
                "clear":           str(v['clear']) if v.get('clear') is not None else None,
                "score":           1 - v.get('value') if v.get('value') is not None else None,
            })

        if score_rows:
            conn.execute(text("""
                INSERT INTO Score
                    (catalog_id, global_chart_id, performance_id,
                     plays, last_played, clear, score)
                VALUES
                    (:catalog_id, :global_chart_id, :performance_id,
                     :plays, :last_played, :clear, :score)
                ON DUPLICATE KEY UPDATE
                    plays       = VALUES(plays),
                    last_played = VALUES(last_played),
                    clear       = VALUES(clear),
                    score       = VALUES(score)
            """), score_rows)

        print(f"  {len(score_rows)} scores inserted, {skipped} skipped (unknown chart or player).")

        # ------------------------------------------------------------------ #
        # Relationships — resolve IDs in Python, then bulk insert             #
        # ------------------------------------------------------------------ #
        rels = data.get('relationships', [])
        print(f"\nRelationships: inserting/updating {len(rels)} rows...")

        rel_rows = []
        skipped = 0
        for r in rels:
            x_gcid = chart_id_map.get(r['x_id'])
            y_gcid = chart_id_map.get(r['y_id'])
            if x_gcid is None or y_gcid is None:
                skipped += 1
                continue
            rel_rows.append({
                "x_id":     x_gcid,
                "y_id":     y_gcid,
                "relation": r.get('relation'),
                "strength": r.get('strength'),
            })

        if rel_rows:
            conn.execute(text("""
                INSERT INTO Relationship (x_id, y_id, relation, strength)
                VALUES (:x_id, :y_id, :relation, :strength)
                ON DUPLICATE KEY UPDATE
                    relation = VALUES(relation),
                    strength = VALUES(strength)
            """), rel_rows)

        print(f"  {len(rel_rows)} relationships inserted, {skipped} skipped.")

    print("\nUpload complete!")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: python {sys.argv[0]} <catalog_name> <scobility_json_file> [perfect_offset] [perfect_score]")
        sys.exit(1)
    kwargs = {}
    if len(sys.argv) >= 4:
        kwargs['perfect_offset'] = float(sys.argv[3])
    if len(sys.argv) >= 5:
        kwargs['perfect_score'] = float(sys.argv[4])
    upload(sys.argv[1], sys.argv[2], **kwargs)
