import os, time, csv
from datetime import datetime

def now_ts():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    def __exit__(self, exc_type, exc, tb):
        self.end = time.perf_counter()
        self.elapsed = (self.end - self.start) * 1000.0

def write_csv_header(path, header):
    with open(path, "w", newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(header)

def append_csv(path, row):
    with open(path, "a", newline='', encoding='utf-8') as f:
        csv.writer(f).writerow(row)
