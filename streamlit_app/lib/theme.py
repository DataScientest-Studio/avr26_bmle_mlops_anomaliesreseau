"""Palette Okabe-Ito (sûre pour les daltoniens) + petits helpers de mise en page.

Une couleur = un sens, identique sur toutes les pages :
  réel -> bleu, prédit -> orange, anomalie -> vermillon (réservé à ce statut),
  week-end / férié -> vert, jour ouvré -> gris, champion MLflow -> pourpre.
"""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

REEL = "#0072B2"        # bleu
PREDIT = "#E69F00"      # orange
ANOMALIE = "#D55E00"    # vermillon — statut réservé, jamais utilisé ailleurs
CHOME = "#009E73"       # vert : week-end / jour férié
OUVRE = "#9aa0a6"       # gris : jour ouvré
CHAMPION = "#CC79A7"    # pourpre rougeâtre (Okabe-Ito) : version champion
NEUTRE = "#56606b"      # texte / règles secondaires

# Mise en avant de "mes parties" dans le diagramme d'architecture.
MINE_FILL = "#d6e8f5"
TEAM_FILL = "#eeeeee"

MAX_POINTS = 5000  # plafond de points envoyés à un graphique Altair


NOTES_FILE = Path(__file__).resolve().parents[1] / "NOTES_ORATEUR.md"


#def header(title: str, minutes: float, owner: str | None = None) -> None:
#    """Titre de section + budget temps + orateur (repère pour la répétition)."""
#    st.title(title)
#    m, s = int(minutes), int(round((minutes - int(minutes)) * 60))
#    budget = f"⏱ {m} min {s:02d}" if s else f"⏱ {m} min"
#    st.caption(f"{budget}" + (f" · 🎤 {owner}" if owner else ""))

def header(title: str, *_args, **_kwargs) -> None:
    """Titre de section."""
    st.title(title)

def _notes_sections() -> dict[str, str]:
    """Découpe NOTES_ORATEUR.md en sections ``<!-- key: xxx -->``."""
    if not NOTES_FILE.is_file():
        return {}
    text = NOTES_FILE.read_text(encoding="utf-8")
    parts = re.split(r"<!--\s*key:\s*([\w-]+)\s*-->", text)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def speaker_notes(key: str) -> None:
    """Notes orateur, visibles seulement si la case est cochée dans la barre latérale."""
    if not st.session_state.get("show_notes"):
        return
    body = _notes_sections().get(key)
    if body:
        with st.expander("🎤 Notes orateur", expanded=True):
            st.markdown(body)


def stub(team_role: str, pistes: list[str]) -> None:
    """Cadre vide pour la partie d'un coéquipier : objectif → comment → conclusion."""
    st.info(f"Section à compléter par le coéquipier en charge : **{team_role}**.")
    c1, c2 = st.columns(2)
    c1.markdown("**🎯 Objectif**  \n_À compléter._")
    c2.markdown("**⚙️ Comment**  \n_À compléter._")
    with st.expander("Pistes tirées du repo (à reprendre ou supprimer)"):
        st.markdown("\n".join(f"- {p}" for p in pistes))
    st.divider()
    st.markdown("**Conclusion**  \n_À compléter._")


def story(objectif: str, comment: str) -> None:
    """Bandeau « objectif → comment » en tête de page (format archi d'abord)."""
    c1, c2 = st.columns(2)
    c1.markdown(f"**🎯 Objectif**  \n{objectif}")
    c2.markdown(f"**⚙️ Comment**  \n{comment}")
    st.divider()


def conclusion(text: str) -> None:
    """Encadré de conclusion en bas de page."""
    st.divider()
    st.success(f"**Conclusion** — {text}")


def stop_on(err: str | None, hint: str | None = None, level: str = "error") -> None:
    """Dégradation propre : affiche le message et arrête la page."""
    if err is None:
        return
    (st.error if level == "error" else st.info)(err)
    if hint:
        st.caption(hint)
    st.stop()
