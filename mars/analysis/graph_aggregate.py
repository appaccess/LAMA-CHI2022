import pandas as pd
import csv
import json
import statistics


crawl_vers = [
    # "2019.12",
    # "2020.01",
    # "2020.02",
    "2020.03",
    "2020.04",
    "2020.05",
    "2020.06",
    "2020.08",
    "2020.10",
    "2020.11",
    "2020.12",
    "2021.02",
]


for c in crawl_vers:
    with open(f'analysis/graph/graph_{c}.json', 'r') as f:
        clusters = json.load(f)

    with open(f'analysis/graph/graph_{c}.csv', 'w', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['pkg', 'states', 'covered', 'covered_with_failure', 'remained', 'unknown', 'missing_speakable_text', 'encountered_failure', 'sum_delta', 'max_delta', 'mean_delta', 'sd_delta'])
        for app_name, app_dict in clusters.items():
            max_deltas = clusters[app_name]['max-deltas']
            max_deltas += [0] * (clusters[app_name]['max_covered'] - len(max_deltas))
            writer.writerow([
                app_name,
                clusters[app_name]['states'], 
                clusters[app_name]['all_covered'],
                clusters[app_name]['max_covered'],
                clusters[app_name]['remained'],
                len(clusters[app_name]['unknown_uuid']),
                clusters[app_name]['missing-speakable-text'], 
                clusters[app_name]['encountered-failure'],
                clusters[app_name]['max-deltas-sum'], 
                clusters[app_name]['max-deltas-max'],
                statistics.mean(max_deltas) if len(max_deltas) >= 1 else 0, 
                statistics.stdev(max_deltas) if len(max_deltas) >= 2 else 0
            ])


data = pd.DataFrame()

for c in crawl_vers:
    df = pd.read_csv(f'analysis/graph/graph_{c}.csv')
    df.insert(0, "crawl_ver", c, True)
    data = data.append(df)


data.to_csv("analysis/graph/graph_all.csv")
