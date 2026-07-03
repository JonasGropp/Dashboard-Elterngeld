"""
app.py
======
Streamlit-Dashboard: Gemeinsames verfügbares Netto-Haushaltseinkommen
nach Geburt eines Kindes (Elterngeld-Szenarioplaner für Jana & Jonas).

Start:  streamlit run app.py

Hinweis: Dieses Programm ersetzt keine Steuer- oder Rechtsberatung.
Ziel ist eine transparente Liquiditäts- und Szenarioplanung.
"""

from __future__ import annotations

import copy
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from calculations import (
    DEFAULT_EG_PARAMS,
    MODELLE,
    STATUS_OPTIONEN,
    approx_netto_from_brutto,
    build_dashboard_table,
    calculate_calendar_month_result,
    calculate_life_months,
    calculate_maternity_period,
    compare_scenarios,
    eur,
)

st.set_page_config(page_title="Elterngeld- & Haushaltsplaner",
                   page_icon="👶", layout="wide")

# ---------------------------------------------------------------------------
# Default-Ausgangsdaten
# ---------------------------------------------------------------------------

DEFAULTS = {
    "name_mutter": "Jana",
    "name_vater": "Jonas",
    "netto_mutter": 3095.0,
    "netto_vater": 3109.0,
    "geburtstermin": date(2027, 2, 19),
    "hochzeit": date(2026, 10, 1),
    "stk_mutter_vor": 1, "stk_mutter_nach": 5,
    "stk_vater_vor": 1, "stk_vater_nach": 3,
    "anzahl_kinder": 1,
    "kindergeld": 259.0,
    "horizont": 36,
    "ms_wochen_vor": 6.0,
    "ms_wochen_nach": 8.0,
}

PLAN_COLUMNS = ["Lebensmonat", "Zeitraum", "Elterngeld-Modell", "Status",
                "Wochenstunden", "% vom Netto", "Netto fix (€)",
                "Sonstige Einnahmen (€)", "Bemerkung"]


def default_plan_rows(parent: str, life_months) -> list[dict]:
    """Erzeugt einen sinnvollen Default-Plan (Szenario A):
    Mutter 12 Monate Basiselterngeld, Vater LM 13–14 Basiselterngeld."""
    rows = []
    for lm in life_months:
        m = lm.index
        if parent == "mother":
            if m <= 12:
                modell, status, std, pct = "Basiselterngeld", "keine Arbeit", 0.0, 0.0
            else:
                modell, status, std, pct = "Kein Elterngeld", "Teilzeit", 20.0, 50.0
        else:
            if m in (13, 14):
                modell, status, std, pct = "Basiselterngeld", "keine Arbeit", 0.0, 0.0
            else:
                modell, status, std, pct = "Kein Elterngeld", "Vollzeit", 40.0, 100.0
        rows.append({
            "Lebensmonat": m,
            "Zeitraum": f"{lm.start.strftime('%d.%m.%y')}–{lm.end.strftime('%d.%m.%y')}",
            "Elterngeld-Modell": modell,
            "Status": status,
            "Wochenstunden": std,
            "% vom Netto": pct,
            "Netto fix (€)": 0.0,
            "Sonstige Einnahmen (€)": 0.0,
            "Bemerkung": "",
        })
    return rows


def example_plan(variant: str, parent: str, life_months) -> list[dict]:
    """Beispiel-Szenarien A/B/C als Plan-Vorlagen."""
    rows = default_plan_rows(parent, life_months)  # Basis = Szenario A
    if variant == "A":
        return rows
    for r in rows:
        m = r["Lebensmonat"]
        if variant == "B":
            if parent == "mother":
                if m <= 24:
                    r.update({"Elterngeld-Modell": "ElterngeldPlus",
                              "Status": "Teilzeit", "Wochenstunden": 20.0,
                              "% vom Netto": 50.0})
                else:
                    r.update({"Elterngeld-Modell": "Kein Elterngeld",
                              "Status": "Teilzeit", "Wochenstunden": 20.0,
                              "% vom Netto": 50.0})
            else:
                if m in (1, 2):
                    r.update({"Elterngeld-Modell": "Basiselterngeld",
                              "Status": "keine Arbeit", "Wochenstunden": 0.0,
                              "% vom Netto": 0.0})
                else:
                    r.update({"Elterngeld-Modell": "Kein Elterngeld",
                              "Status": "Vollzeit", "Wochenstunden": 40.0,
                              "% vom Netto": 100.0})
        elif variant == "C":
            # Beide Teilzeit; LM 1-8 ElterngeldPlus, LM 9-12 Partnerschaftsbonus
            if m <= 8:
                r.update({"Elterngeld-Modell": "ElterngeldPlus",
                          "Status": "Teilzeit", "Wochenstunden": 28.0,
                          "% vom Netto": 70.0})
            elif m <= 12:
                r.update({"Elterngeld-Modell": "Partnerschaftsbonus",
                          "Status": "Teilzeit", "Wochenstunden": 28.0,
                          "% vom Netto": 70.0})
            else:
                r.update({"Elterngeld-Modell": "Kein Elterngeld",
                          "Status": "Teilzeit", "Wochenstunden": 30.0,
                          "% vom Netto": 75.0})
    return rows


def sync_plan_rows(existing: list[dict], parent: str, life_months) -> list[dict]:
    """Passt einen bestehenden Plan an geänderte Lebensmonate an
    (bestehende Eingaben bleiben erhalten, Zeiträume werden aktualisiert)."""
    by_lm = {int(r["Lebensmonat"]): r for r in existing}
    fresh = default_plan_rows(parent, life_months)
    for row in fresh:
        old = by_lm.get(row["Lebensmonat"])
        if old:
            for c in PLAN_COLUMNS:
                if c != "Zeitraum":
                    row[c] = old.get(c, row[c])
    return fresh


# ---------------------------------------------------------------------------
# Session-State initialisieren
# ---------------------------------------------------------------------------

if "eg_params" not in st.session_state:
    st.session_state.eg_params = dict(DEFAULT_EG_PARAMS)
if "scenarios" not in st.session_state:
    st.session_state.scenarios = {}

st.title("👶 Elterngeld- & Haushaltseinkommens-Planer")
st.caption(
    "Szenarioplanung des gemeinsamen verfügbaren Netto-Haushaltseinkommens "
    "nach der Geburt · **keine Steuer- oder Rechtsberatung**"
)

tab_stamm, tab_eink, tab_plan, tab_erg, tab_szen, tab_ann = st.tabs([
    "1️⃣ Stammdaten", "2️⃣ Einkommen & Mutterschutz", "3️⃣ Elterngeldplanung",
    "4️⃣ Ergebnis", "5️⃣ Szenarien", "ℹ️ Annahmen",
])

# ---------------------------------------------------------------------------
# Tab 1: Stammdaten
# ---------------------------------------------------------------------------
with tab_stamm:
    c1, c2, c3 = st.columns(3)
    with c1:
        name_m = st.text_input("Name Mutter", DEFAULTS["name_mutter"])
        name_v = st.text_input("Name Vater", DEFAULTS["name_vater"])
        geburt = st.date_input("Geburtstermin", DEFAULTS["geburtstermin"],
                               format="DD.MM.YYYY")
        hochzeit = st.date_input("Hochzeitsdatum", DEFAULTS["hochzeit"],
                                 format="DD.MM.YYYY")
    with c2:
        horizont = st.number_input("Betrachtungszeitraum (Monate ab Geburtsmonat)",
                                   min_value=1, max_value=120,
                                   value=DEFAULTS["horizont"])
        anzahl_kinder = st.number_input("Anzahl Kinder", min_value=1,
                                        max_value=10,
                                        value=DEFAULTS["anzahl_kinder"])
        kindergeld = st.number_input("Kindergeld je Kind (€/Monat)",
                                     min_value=0.0,
                                     value=DEFAULTS["kindergeld"], step=1.0)
        fixkosten = st.number_input("Optionale monatliche Fixkosten (€)",
                                    min_value=0.0, value=0.0, step=50.0)
    with c3:
        st.markdown("**Steuerklassen**")
        stk_m_vor = st.selectbox("Mutter vor Hochzeit", [1, 2, 3, 4, 5, 6],
                                 index=0)
        stk_m_nach = st.selectbox("Mutter nach Hochzeit", [1, 2, 3, 4, 5, 6],
                                  index=4)
        stk_v_vor = st.selectbox("Vater vor Hochzeit", [1, 2, 3, 4, 5, 6],
                                 index=0)
        stk_v_nach = st.selectbox("Vater nach Hochzeit", [1, 2, 3, 4, 5, 6],
                                  index=2)

    with st.expander("⚙️ Elterngeld-Parameter (zentral konfigurierbar)"):
        p = st.session_state.eg_params
        pc1, pc2, pc3, pc4 = st.columns(4)
        p["ersatzrate"] = pc1.number_input("Ersatzrate", 0.0, 1.0,
                                           float(p["ersatzrate"]), 0.01)
        p["basis_min"] = pc1.number_input("Basiselterngeld min (€)", 0.0,
                                          value=float(p["basis_min"]))
        p["basis_max"] = pc1.number_input("Basiselterngeld max (€)", 0.0,
                                          value=float(p["basis_max"]))
        p["plus_faktor"] = pc2.number_input("ElterngeldPlus-Faktor", 0.0, 1.0,
                                            float(p["plus_faktor"]), 0.05)
        p["plus_min"] = pc2.number_input("ElterngeldPlus min (€)", 0.0,
                                         value=float(p["plus_min"]))
        p["plus_max"] = pc2.number_input("ElterngeldPlus max (€)", 0.0,
                                         value=float(p["plus_max"]))
        p["max_basis_lebensmonat"] = pc3.number_input(
            "Basiselterngeld bis Lebensmonat", 1, 60,
            int(p["max_basis_lebensmonat"]))
        p["max_basis_monate_elternteil"] = pc3.number_input(
            "Max. Basis-Monate je Elternteil", 1, 24,
            int(p["max_basis_monate_elternteil"]))
        p["max_basis_monate_gesamt"] = pc3.number_input(
            "Max. Basis-Monate gesamt", 1, 28,
            int(p["max_basis_monate_gesamt"]))
        p["max_wochenstunden"] = pc4.number_input(
            "Max. Wochenstunden bei EG-Bezug", 1.0, 60.0,
            float(p["max_wochenstunden"]))
        p["bonus_stunden_min"] = pc4.number_input(
            "Partnerschaftsbonus: Stunden min", 0.0, 60.0,
            float(p["bonus_stunden_min"]))
        p["bonus_stunden_max"] = pc4.number_input(
            "Partnerschaftsbonus: Stunden max", 0.0, 60.0,
            float(p["bonus_stunden_max"]))
        p["teilzeit_default_prozent"] = pc4.number_input(
            "Teilzeit-Default (% vom Netto)", 0.0, 100.0,
            float(p["teilzeit_default_prozent"]))

# ---------------------------------------------------------------------------
# Tab 2: Einkommen & Mutterschutz
# ---------------------------------------------------------------------------
with tab_eink:
    ec1, ec2 = st.columns(2)

    def income_block(col, label: str, default_netto: float, stk_default: int):
        """Eingabeblock je Elternteil inkl. optionaler Brutto-Näherung."""
        with col:
            st.subheader(label)
            netto = st.number_input(
                f"Ø monatliches Netto vor Geburt (€) – {label}",
                min_value=0.0, value=default_netto, step=10.0,
                key=f"netto_{label}")
            with st.expander("Optional: Brutto-Näherung & Details"):
                brutto = st.number_input("Bruttogehalt (€/Monat)", 0.0,
                                         value=0.0, step=100.0,
                                         key=f"brutto_{label}")
                stk = st.selectbox("Steuerklasse (für Näherung)",
                                   [1, 2, 3, 4, 5, 6],
                                   index=stk_default - 1, key=f"stk_{label}")
                kv = st.number_input("KV-Zusatzbeitrag (%)", 0.0, 5.0, 1.7,
                                     0.1, key=f"kv_{label}")
                kirche = st.checkbox("Kirchensteuer", key=f"ki_{label}")
                bundesland = st.text_input("Bundesland", "Bayern",
                                           key=f"bl_{label}")
                if brutto > 0:
                    approx = approx_netto_from_brutto(brutto, stk, kirche, kv)
                    st.info(f"Grobe Netto-Schätzung: **{eur(approx)}** "
                            f"({bundesland}, StKl {stk}). Bitte bei Bedarf "
                            "oben als Netto übernehmen – dies ist KEINE "
                            "echte Lohnsteuerberechnung.")
            return netto

    netto_m = income_block(ec1, f"{name_m} (Mutter)",
                           DEFAULTS["netto_mutter"], stk_m_nach)
    netto_v = income_block(ec2, f"{name_v} (Vater)",
                           DEFAULTS["netto_vater"], stk_v_nach)

    st.divider()
    st.subheader("🤱 Mutterschutz")
    mc1, mc2, mc3 = st.columns(3)
    ms_vor = mc1.number_input("Mutterschutz: Wochen vor Geburt", 0.0, 20.0,
                              DEFAULTS["ms_wochen_vor"], 1.0)
    ms_nach = mc2.number_input("Mutterschutz: Wochen nach Geburt", 0.0, 20.0,
                               DEFAULTS["ms_wochen_nach"], 1.0)
    ms_override = mc3.number_input(
        "Mutterschaftsleistung (€/Monat, 0 = Netto fortführen)",
        0.0, value=0.0, step=50.0,
        help="Standard: bisheriges Netto wird näherungsweise fortgeführt "
             "(Mutterschaftsgeld + Arbeitgeberzuschuss).")
    ms_start, ms_end = calculate_maternity_period(geburt, ms_vor, ms_nach)
    st.info(
        f"Mutterschutz: **{ms_start.strftime('%d.%m.%Y')} – "
        f"{ms_end.strftime('%d.%m.%Y')}**. Mutterschutzmonate nach der Geburt "
        f"gelten als Elterngeld-relevante Monate der Mutter; "
        f"**Mutterschaftsleistungen werden auf das Elterngeld angerechnet.**"
    )

# ---------------------------------------------------------------------------
# Tab 3: Elterngeldplanung (je Lebensmonat)
# ---------------------------------------------------------------------------
n_lm = int(horizont) + 1
life_months = calculate_life_months(geburt, n_lm)

# Pläne im Session-State halten und bei Änderungen synchronisieren
for key, parent in (("plan_mother", "mother"), ("plan_father", "father")):
    if key not in st.session_state:
        st.session_state[key] = default_plan_rows(parent, life_months)
    else:
        st.session_state[key] = sync_plan_rows(
            st.session_state[key], parent, life_months)

with tab_plan:
    st.markdown(
        "Elterngeldmodell, Beschäftigung und Einnahmen je **Lebensmonat** "
        f"(LM 1 = {life_months[0].start.strftime('%d.%m.%Y')} – "
        f"{life_months[0].end.strftime('%d.%m.%Y')}). "
        "Die Auswertung erfolgt anschließend je **Kalendermonat** "
        "mit tagesgenauer, zeitanteiliger Aufteilung."
    )
    bc = st.columns(4)
    if bc[0].button("Vorlage A: 12+2 Basiselterngeld"):
        st.session_state.plan_mother = example_plan("A", "mother", life_months)
        st.session_state.plan_father = example_plan("A", "father", life_months)
        st.rerun()
    if bc[1].button("Vorlage B: 24× ElterngeldPlus + 2 Basis"):
        st.session_state.plan_mother = example_plan("B", "mother", life_months)
        st.session_state.plan_father = example_plan("B", "father", life_months)
        st.rerun()
    if bc[2].button("Vorlage C: Teilzeit + Partnerschaftsbonus"):
        st.session_state.plan_mother = example_plan("C", "mother", life_months)
        st.session_state.plan_father = example_plan("C", "father", life_months)
        st.rerun()

    col_cfg = {
        "Lebensmonat": st.column_config.NumberColumn(disabled=True, width="small"),
        "Zeitraum": st.column_config.TextColumn(disabled=True),
        "Elterngeld-Modell": st.column_config.SelectboxColumn(
            options=MODELLE, required=True),
        "Status": st.column_config.SelectboxColumn(
            options=STATUS_OPTIONEN, required=True),
        "Wochenstunden": st.column_config.NumberColumn(min_value=0.0,
                                                       max_value=60.0),
        "% vom Netto": st.column_config.NumberColumn(min_value=0.0,
                                                     max_value=200.0),
        "Netto fix (€)": st.column_config.NumberColumn(min_value=0.0),
        "Sonstige Einnahmen (€)": st.column_config.NumberColumn(min_value=0.0),
    }

    st.subheader(f"Plan {name_m} (Mutter)")
    df_pm = st.data_editor(pd.DataFrame(st.session_state.plan_mother),
                           column_config=col_cfg, hide_index=True,
                           num_rows="fixed", key="editor_mother")
    st.session_state.plan_mother = df_pm.to_dict("records")

    st.subheader(f"Plan {name_v} (Vater)")
    df_pv = st.data_editor(pd.DataFrame(st.session_state.plan_father),
                           column_config=col_cfg, hide_index=True,
                           num_rows="fixed", key="editor_father")
    st.session_state.plan_father = df_pv.to_dict("records")

# ---------------------------------------------------------------------------
# Aktuelles Szenario zusammenstellen & berechnen
# ---------------------------------------------------------------------------

def current_scenario() -> dict:
    return {
        "birth_date": geburt,
        "horizon": int(horizont),
        "anzahl_kinder": int(anzahl_kinder),
        "kindergeld_je_kind": float(kindergeld),
        "hochzeit": hochzeit,
        "stk_mutter_vor": stk_m_vor, "stk_mutter_nach": stk_m_nach,
        "stk_vater_vor": stk_v_vor, "stk_vater_nach": stk_v_nach,
        "mother": {"name": name_m, "netto_vor": float(netto_m)},
        "father": {"name": name_v, "netto_vor": float(netto_v)},
        "ms_wochen_vor": float(ms_vor), "ms_wochen_nach": float(ms_nach),
        "ms_override": float(ms_override),
        "eg_params": dict(st.session_state.eg_params),
        "fixkosten": float(fixkosten),
        "plan_mother": copy.deepcopy(st.session_state.plan_mother),
        "plan_father": copy.deepcopy(st.session_state.plan_father),
    }


scenario = current_scenario()
res = calculate_calendar_month_result(scenario)

# ---------------------------------------------------------------------------
# Tab 4: Ergebnis (transponierte Tabelle + Diagramme)
# ---------------------------------------------------------------------------
with tab_erg:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Gemeinsames Netto vor Geburt",
              eur(res["netto_vor_gesamt"]))
    k2.metric("Ø Haushaltseinkommen/Monat",
              eur(sum(res["haushalt"]) / len(res["haushalt"])))
    k3.metric("Niedrigster Monat", eur(min(res["haushalt"])))
    k4.metric("Kumulierte Differenz (Ende)", eur(res["diff_kum"][-1]))

    st.subheader("📊 Dashboard-Tabelle (Monate = Spalten, Kennzahlen = Zeilen)")
    table = build_dashboard_table(res, scenario)
    st.dataframe(table, use_container_width=True, height=780)
    st.download_button("⬇️ Tabelle als CSV",
                       table.to_csv(sep=";").encode("utf-8-sig"),
                       "haushaltsplan.csv", "text/csv")

    if res["warnings"]:
        st.subheader("🔎 Plausibilitätsprüfungen")
        for wtext in res["warnings"]:
            (st.warning if wtext.startswith("⚠️") else st.info)(wtext)

    st.subheader("📈 Visualisierungen")
    labels = res["labels"]

    # 1) Linie: Haushaltseinkommen je Kalendermonat
    fig1 = go.Figure()
    fig1.add_scatter(x=labels, y=res["haushalt"], mode="lines+markers",
                     name="Haushaltseinkommen")
    fig1.add_hline(y=res["netto_vor_gesamt"], line_dash="dash",
                   annotation_text="Netto vor Geburt")
    fig1.update_layout(title="Gemeinsames verfügbares Netto-Haushaltseinkommen",
                       yaxis_title="€ / Monat", hovermode="x unified")
    st.plotly_chart(fig1, use_container_width=True)

    # 2) Gestapelte Balken: Zusammensetzung je Monat
    fig2 = go.Figure()
    stacks = [
        (f"Arbeitseinkommen {name_m}", res["m_arbeit"]),
        (f"Arbeitseinkommen {name_v}", res["v_arbeit"]),
        ("Mutterschutzleistung", res["m_mutterschutz"]),
        (f"Elterngeld {name_m}",
         [a + b + c for a, b, c in zip(res["m_basis"], res["m_plus"],
                                       res["m_bonus"])]),
        (f"Elterngeld {name_v}",
         [a + b + c for a, b, c in zip(res["v_basis"], res["v_plus"],
                                       res["v_bonus"])]),
        ("Kindergeld", res["kindergeld"]),
        ("Sonstige Einnahmen",
         [a + b for a, b in zip(res["m_sonstige"], res["v_sonstige"])]),
    ]
    for sname, values in stacks:
        fig2.add_bar(x=labels, y=values, name=sname)
    fig2.update_layout(barmode="stack",
                       title="Zusammensetzung des Haushaltseinkommens",
                       yaxis_title="€ / Monat", hovermode="x unified")
    st.plotly_chart(fig2, use_container_width=True)

    # 3) Linie: kumulierte Differenz
    fig3 = go.Figure()
    fig3.add_scatter(x=labels, y=res["diff_kum"], mode="lines+markers",
                     name="Kumulierte Differenz", fill="tozeroy")
    fig3.update_layout(title="Kumulierte Differenz zum Netto vor Geburt",
                       yaxis_title="€", hovermode="x unified")
    st.plotly_chart(fig3, use_container_width=True)

    # 4) Optional: Überschuss nach Fixkosten
    if scenario["fixkosten"] > 0:
        fig4 = go.Figure()
        fig4.add_bar(x=labels, y=res["ueberschuss"],
                     name="Überschuss nach Fixkosten")
        fig4.update_layout(title="Monatlicher Überschuss nach Fixkosten",
                           yaxis_title="€ / Monat")
        st.plotly_chart(fig4, use_container_width=True)

# ---------------------------------------------------------------------------
# Tab 5: Szenarien
# ---------------------------------------------------------------------------
with tab_szen:
    st.markdown("Aktuelle Eingaben als Szenario **speichern**, "
                "**duplizieren** und **vergleichen**.")
    sc1, sc2 = st.columns([2, 3])
    with sc1:
        new_name = st.text_input("Szenarioname", "Szenario A")
        if st.button("💾 Aktuelles Szenario speichern"):
            if new_name.strip():
                st.session_state.scenarios[new_name.strip()] = current_scenario()
                st.success(f"„{new_name.strip()}“ gespeichert.")
            else:
                st.error("Bitte einen Szenarionamen angeben.")
        if st.session_state.scenarios:
            dup_src = st.selectbox("Szenario duplizieren",
                                   list(st.session_state.scenarios))
            dup_name = st.text_input("Neuer Name", f"{dup_src} (Kopie)")
            if st.button("📄 Duplizieren"):
                st.session_state.scenarios[dup_name] = copy.deepcopy(
                    st.session_state.scenarios[dup_src])
                st.success(f"„{dup_name}“ angelegt.")
            del_sel = st.multiselect("Szenarien löschen",
                                     list(st.session_state.scenarios))
            if st.button("🗑️ Löschen") and del_sel:
                for n in del_sel:
                    st.session_state.scenarios.pop(n, None)
                st.rerun()

    with sc2:
        if st.session_state.scenarios:
            compare_sel = st.multiselect(
                "Szenarien vergleichen",
                list(st.session_state.scenarios),
                default=list(st.session_state.scenarios)[:3])
            if compare_sel:
                subset = {n: st.session_state.scenarios[n]
                          for n in compare_sel}
                dfc, monthly = compare_scenarios(subset)
                st.subheader("Vergleichskennzahlen")
                st.dataframe(dfc, use_container_width=True)

                figc = go.Figure()
                for n, mdata in monthly.items():
                    figc.add_scatter(x=mdata["labels"], y=mdata["haushalt"],
                                     mode="lines", name=n)
                figc.update_layout(
                    title="Haushaltseinkommen je Szenario",
                    yaxis_title="€ / Monat", hovermode="x unified")
                st.plotly_chart(figc, use_container_width=True)

                figk = go.Figure()
                for n, mdata in monthly.items():
                    figk.add_scatter(x=mdata["labels"], y=mdata["diff_kum"],
                                     mode="lines", name=n)
                figk.update_layout(
                    title="Kumulierte Differenz je Szenario",
                    yaxis_title="€", hovermode="x unified")
                st.plotly_chart(figk, use_container_width=True)
        else:
            st.info("Noch keine Szenarien gespeichert. Links speichern, "
                    "dann hier vergleichen. Tipp: Vorlagen A/B/C im Tab "
                    "„Elterngeldplanung“ laden und jeweils speichern.")

# ---------------------------------------------------------------------------
# Tab 6: Annahmen
# ---------------------------------------------------------------------------
with tab_ann:
    st.markdown(f"""
### Vereinfachte Annahmen dieses Planers

1. **Netto-Basis:** Alle Berechnungen basieren standardmäßig auf gepflegten
   **Netto-Werten**. Die optionale Brutto-Netto-Schätzung ist nur eine grobe
   Näherung und keine Lohnsteuerberechnung.
2. **Elterngeld = Szenariorechnung:** Elterngeld wird vereinfacht als
   `Ersatzrate × (Netto vor Geburt − Netto nach Geburt)` mit Mindest- und
   Höchstbeträgen berechnet. Die **tatsächliche Elterngeldstelle kann
   abweichend rechnen** (Elterngeld-Netto, Geschwisterbonus, Deckelungen bei
   Teilzeit u. a. sind nicht abgebildet).
3. **Mutterschaftsleistungen:** Mutterschaftsgeld + Arbeitgeberzuschuss werden
   vereinfacht als Fortführung des bisherigen Nettos abgebildet, sofern kein
   echter Wert gepflegt ist. Sie werden auf das Elterngeld **angerechnet** –
   im Modell wird für Mutterschutz-Tage daher kein zusätzliches Elterngeld
   angesetzt; diese Lebensmonate zählen aber als Basiselterngeld-Monate.
4. **Progressionsvorbehalt:** Elterngeld ist steuerfrei, kann aber über den
   Progressionsvorbehalt die Steuer auf das übrige Einkommen erhöhen
   (mögliche Nachzahlung ist hier **nicht** eingerechnet).
5. **Steuerklassen:** Der Wechsel zu 3/5 nach der Hochzeit ({hochzeit.strftime('%m/%Y')})
   wird nicht automatisch in Netto-Werte umgerechnet – bitte die Netto-Werte
   entsprechend der ab Mutterschutz maßgeblichen Steuerklasse pflegen.
6. **Zeitanteilige Aufteilung:** Lebensmonatsbeträge werden tagesgenau auf
   Kalendermonate verteilt; Zahlungszeitpunkte realer Überweisungen können
   abweichen.
7. **Kindergeld** wird ab dem Geburtsmonat in voller Höhe angesetzt.

> ⚠️ Dieses Programm ersetzt **keine Steuer- oder Rechtsberatung**. Ziel ist
> eine transparente Liquiditäts- und Szenarioplanung für
> {name_m} und {name_v}.
""")
