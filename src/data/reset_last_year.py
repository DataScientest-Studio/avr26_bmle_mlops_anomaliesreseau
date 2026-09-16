from pathlib import Path

DATA_DIR = Path('src/data')

with open(DATA_DIR/"max_year.conf", "w") as f:
    f.write('2012')