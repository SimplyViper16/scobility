import requests
import glob
import logging
import os
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime as dt
from time import sleep

default_tourney = 'itl2026'

def timestamp():
    return dt.utcnow().strftime('%Y%m%d-%H%M%S-%f')[:-3]

def setup_scrape(tourney: str = default_tourney) -> str:
    path_dst = os.path.join(f'{tourney}_data', dt.utcnow().strftime('%Y%m%d'))
    os.makedirs(path_dst, exist_ok=True)

    # Set up logging
    logging.getLogger().handlers.clear()
    log_stamp = timestamp()
    log_path = os.path.join(path_dst, f'scobility-scrape-{log_stamp}.log')
    log_fmt = logging.Formatter(
        '[%(asctime)s.%(msecs)03d] %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logging.basicConfig(
        filename=log_path,
        encoding='utf-8',
        level=logging.INFO
    )
    logging.getLogger().addHandler(logging.StreamHandler())
    for handler in logging.getLogger().handlers:
        handler.setFormatter(log_fmt)

    return path_dst

total_charts = 500

def scrape_charts(path_dst: str, tourney: str = default_tourney, workers: int = 20):
    charts = {}

    # Step 1: bulk fetch all public charts from the list endpoint
    try:
        r = requests.get(f'https://{tourney}.groovestats.com/api/chart/list')
        j = r.json()
        if j.get('success', False):
            for c in j.get('data', []):
                charts[c['id']] = c
                logging.info(f"{c['id']:4d} (list): {c.get('artist')} - \"{c.get('title')}\"")
            logging.info(f"Got {len(charts)} charts from list API.")
        else:
            logging.warning(f"Chart list API: {j.get('message', '')} — falling back to ID scan only.")
    except Exception as e:
        logging.warning(f"Chart list API failed: {e} — falling back to ID scan only.")

    # Step 2: scan the gaps between known IDs concurrently.
    # Hidden charts must live in [1, max_known_id + buffer] — no need to scan 0-10000.
    known_ids = set(charts.keys())
    scan_ceiling = max(known_ids, default=0) + 50
    ids_to_scan = [i for i in range(1, scan_ceiling + 1) if i not in known_ids]
    logging.info(f"Scanning {len(ids_to_scan)} gap IDs for hidden charts (workers={workers})...")

    def fetch_chart(i):
        try:
            r = requests.get(f'https://{tourney}.groovestats.com/api/chart/{i}')
            j = r.json()
            if j.get('success', False):
                return i, j.get('data', {})
        except Exception:
            pass
        return i, None

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for i, data in executor.map(fetch_chart, ids_to_scan):
            if data is not None:
                charts[i] = data
                logging.info(f"{i:4d} (hidden): {data.get('artist')} - \"{data.get('title')}\"")

    logging.info(f"Total charts: {len(charts)} ({len(charts) - len(known_ids)} hidden).")

    with open(os.path.join(path_dst, 'charts.json'), 'w', encoding='utf-8') as fp:
        json.dump(charts, fp)

def scrape_entrants(path_dst: str, tourney: str = default_tourney):
    p_entrants = os.path.join(path_dst, 'entrant_info')
    os.makedirs(p_entrants, exist_ok=True)

    try:
        r = requests.get(f'https://{tourney}.groovestats.com/api/entrant/leaderboard')
        j = r.json()
    except Exception as e:
        logging.error(f"Leaderboard API failed: {e}")
        return

    if not j.get('success', False):
        logging.error(f"Leaderboard API: {j.get('message', '')}")
        return

    leaderboard = j['data']['leaderboard']
    logging.info(f"Got {len(leaderboard)} players from leaderboard.")

    for entry in leaderboard:
        i = entry['id']
        logging.info(f"{i:4d}: {entry.get('name')} (ITL #{i}, GS #{entry.get('membersId', '?')})")
        with open(os.path.join(p_entrants, f'{i}.json'), 'w', encoding='utf-8') as fp:
            json.dump({'entrant': entry}, fp)

def scrape_scores(path_dst: str, tourney: str = default_tourney, workers: int = 10):
    p_scores = os.path.join(path_dst, 'song_scores')
    os.makedirs(p_scores, exist_ok=True)

    charts_json_src = os.path.join(path_dst, 'charts.json')
    if not os.path.exists(charts_json_src):
        one_level_up = os.path.split(path_dst)[0]
        charts_json_src_options = sorted([
            (os.path.getctime(fn), fn)
            for fn in [os.path.join(one_level_up, fn, 'charts.json') for fn in os.listdir(one_level_up)]
            if os.path.exists(fn)
        ], key=lambda v: -v[0])
        charts_json_src = charts_json_src_options[0][1]
    logging.info(f"Using {charts_json_src} as chart info source file")

    with open(charts_json_src, 'r', encoding='utf-8') as fp:
        charts = json.load(fp)

    abort = threading.Event()
    fails_lock = threading.Lock()
    fail_count = [0]

    def fetch_scores(c):
        if abort.is_set():
            return
        i = c.get('id', 0)
        j = {'success': False, 'message': 'No attempt made'}
        r = None
        for attempt in range(5):
            try:
                r = requests.post(
                    f'https://{tourney}.groovestats.com/api/score/chartTopScores',
                    data={'chartHash': c['hash']}
                )
                if r.status_code >= 400:
                    sleep(2 ** attempt)
                    continue
                j = r.json()
                break
            except Exception as e:
                j = {'success': False, 'message': str(e)}
                sleep(2 ** attempt)

        if not j.get('success', False):
            logging.warning(f"{i:4d} (hash {c['hash']}): {j.get('message', '')}")
            with fails_lock:
                fail_count[0] += 1
                if fail_count[0] > 20:
                    abort.set()
            return

        with fails_lock:
            fail_count[0] = 0

        chart_scores = j.get('data', {}).get('leaderboard', [])
        for s in chart_scores:
            s['chartId'] = i
        full_name = f"{c.get('artist')} - \"{c.get('title')}\""
        logging.info(f"{i:4d} (hash {c['hash']}): {full_name}, {len(chart_scores)} scores")

        with open(os.path.join(p_scores, f'{i}.json'), 'w', encoding='utf-8') as fp:
            json.dump({'scores': chart_scores}, fp)

    chart_list = list(charts.values())[:10000]
    logging.info(f"Fetching scores for {len(chart_list)} charts (workers={workers})...")
    with ThreadPoolExecutor(max_workers=workers) as executor:
        list(executor.map(fetch_scores, chart_list))

    # Write individual song info files
    p_charts = os.path.join(path_dst, 'song_info')
    os.makedirs(p_charts, exist_ok=True)
    for c in charts.values():
        i = c.get('id', 0)
        logging.info(f"{i:4d} (hash {c['hash']}): {c.get('artist')} - \"{c.get('title')}\"")
        with open(os.path.join(p_charts, f'{i}.json'), 'w', encoding='utf-8') as fp:
            json.dump({'song': c}, fp)


if __name__ == '__main__':
    only_scores = False
    tourney = sys.argv[1] if len(sys.argv) > 1 else default_tourney

    path_dst = setup_scrape(tourney)
    if not only_scores:
        scrape_charts(path_dst, tourney)
        scrape_entrants(path_dst, tourney)
    scrape_scores(path_dst, tourney)

    logging.info('Done!')