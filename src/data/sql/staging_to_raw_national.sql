-- Convertit un champ texte du staging en entier.
-- 'ND' (non disponible) et la chaîne vide deviennent NULL.
CREATE OR REPLACE FUNCTION staging.vers_int(v text) RETURNS integer
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS
$$ SELECT nullif(nullif(btrim(v), 'ND'), '')::integer $$;

INSERT INTO raw.eco2mix_national (
    date_heure, nature, perimetre,
    consommation, prevision_j1, prevision_j,
    fioul, charbon, gaz, nucleaire, eolien, solaire,
    hydraulique, pompage, bioenergies, ech_physiques, taux_co2,
    ech_comm_angleterre, ech_comm_espagne, ech_comm_italie,
    ech_comm_suisse, ech_comm_allemagne_belgique,
    fioul_tac, fioul_cogen, fioul_autres,
    gaz_tac, gaz_cogen, gaz_ccg, gaz_autres,
    hydraulique_fil_eau_eclusee, hydraulique_lacs,
    hydraulique_step_turbinage,
    bioenergies_dechets, bioenergies_biomasse, bioenergies_biogaz
)
SELECT
    date_heure::timestamptz, nature, perimetre,
    staging.vers_int(consommation), staging.vers_int(prevision_j1),
    staging.vers_int(prevision_j),
    staging.vers_int(fioul), staging.vers_int(charbon),
    staging.vers_int(gaz), staging.vers_int(nucleaire),
    staging.vers_int(eolien), staging.vers_int(solaire),
    staging.vers_int(hydraulique), staging.vers_int(pompage),
    staging.vers_int(bioenergies), staging.vers_int(ech_physiques),
    staging.vers_int(taux_co2),
    staging.vers_int(ech_comm_angleterre), staging.vers_int(ech_comm_espagne),
    staging.vers_int(ech_comm_italie), staging.vers_int(ech_comm_suisse),
    staging.vers_int(ech_comm_allemagne_belgique),
    staging.vers_int(fioul_tac), staging.vers_int(fioul_cogen),
    staging.vers_int(fioul_autres),
    staging.vers_int(gaz_tac), staging.vers_int(gaz_cogen),
    staging.vers_int(gaz_ccg), staging.vers_int(gaz_autres),
    staging.vers_int(hydraulique_fil_eau_eclusee),
    staging.vers_int(hydraulique_lacs),
    staging.vers_int(hydraulique_step_turbinage),
    staging.vers_int(bioenergies_dechets),
    staging.vers_int(bioenergies_biomasse),
    staging.vers_int(bioenergies_biogaz)
FROM staging.eco2mix_national_cons_def
WHERE heure = to_char(date_heure::timestamptz AT TIME ZONE 'Europe/Paris', 'HH24:MI')
ON CONFLICT (date_heure, nature) DO NOTHING;
