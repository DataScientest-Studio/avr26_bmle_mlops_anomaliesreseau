import csv
from pathlib import Path
from datetime import datetime

CONF_DIR = Path('src/data')
DATA_DIR = Path('data/raw')

def filtrer_csv_par_annee(
    fichier_source: str,
    fichier_cible: str,
    colonne_date: str,
    annee_max: int,
    format_date: str = "%Y-%m-%d",
    delimiteur: str = ";",
):
    with (
        open(fichier_source, mode="r", encoding="utf-8", newline="") as src,
        open(
            fichier_cible, mode="w", encoding="utf-8", newline=""
        ) as dest,
    ):
        lecteur = csv.DictReader(src, delimiter=delimiteur)
        ecrivain = csv.DictWriter(
            dest, fieldnames=lecteur.fieldnames, delimiter=delimiteur
        )

        ecrivain.writeheader()

        for ligne in lecteur:
            valeur_date = ligne.get(colonne_date, "").strip()
            if not valeur_date:
                continue

            try:
                # Extraction de l'année selon le format indiqué
                annee = datetime.strptime(valeur_date, format_date).year
                if annee <= annee_max:
                    ecrivain.writerow(ligne)
            except ValueError:
                # Gère les éventuelles valeurs mal formées ou en-têtes parasites
                continue

with open(CONF_DIR/"max_year.conf", "rt") as f:
    max_year = f.read()
    if not len(max_year) == 4 and not isinstance(max_year, int):
        print(f"{max_year} n'est pas une année")
        
filtrer_csv_par_annee(
    fichier_source=DATA_DIR/"full"/"eco2mix-national-cons-def.csv",
    fichier_cible=DATA_DIR/"eco2mix-national-cons-def.csv",
    colonne_date="Date",
    annee_max=int(max_year),
    format_date="%Y-%m-%d", 
    delimiteur=";", 
)

with open(CONF_DIR/"max_year.conf", "w") as f:
    f.write(str(int(max_year)+1))
