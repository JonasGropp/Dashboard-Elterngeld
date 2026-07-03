"""Smoke-Tests für calculations.py (ohne Streamlit)."""
from datetime import date
from calculations import (DEFAULT_EG_PARAMS, calculate_life_months,
                          calculate_maternity_period, calculate_parental_allowance,
                          calculate_calendar_month_result, build_dashboard_table,
                          compare_scenarios, eur)

birth = date(2027, 2, 19)

# 1) Lebensmonate
lms = calculate_life_months(birth, 3)
assert lms[0].start == date(2027, 2, 19) and lms[0].end == date(2027, 3, 18), lms[0]
assert lms[1].start == date(2027, 3, 19) and lms[1].end == date(2027, 4, 18), lms[1]
print("Lebensmonate OK:", lms[0].label)

# 2) Mutterschutz 6/8 Wochen
ms_s, ms_e = calculate_maternity_period(birth, 6, 8)
assert ms_s == date(2027, 1, 8), ms_s
assert ms_e == date(2027, 4, 15), ms_e  # birth + 56d - 1
print("Mutterschutz OK:", ms_s, "-", ms_e)

# 3) Elterngeld
p = DEFAULT_EG_PARAMS
assert calculate_parental_allowance("Basiselterngeld", 3095, 0, p) == 1800  # gedeckelt
assert calculate_parental_allowance("Basiselterngeld", 2000, 0, p) == 1300
assert calculate_parental_allowance("Basiselterngeld", 2000, 1900, p) == 300  # Mindestbetrag
assert calculate_parental_allowance("ElterngeldPlus", 2000, 0, p) == 650
assert calculate_parental_allowance("Partnerschaftsbonus", 3095, 0, p) == 900  # Plus-Deckel
assert calculate_parental_allowance("Kein Elterngeld", 3095, 0, p) == 0
print("Elterngeldformeln OK")

# 4) Komplettes Szenario
def plan(parent, n):
    rows = []
    for m in range(1, n + 1):
        if parent == "m":
            modell = "Basiselterngeld" if m <= 12 else "Kein Elterngeld"
            status = "keine Arbeit" if m <= 12 else "Teilzeit"
        else:
            modell = "Basiselterngeld" if m in (13, 14) else "Kein Elterngeld"
            status = "keine Arbeit" if m in (13, 14) else "Vollzeit"
        rows.append({"Lebensmonat": m, "Elterngeld-Modell": modell,
                     "Status": status, "Wochenstunden": 0.0,
                     "% vom Netto": 0.0, "Netto fix (€)": 0.0,
                     "Sonstige Einnahmen (€)": 0.0, "Bemerkung": ""})
    return rows

sc = {
    "birth_date": birth, "horizon": 36, "anzahl_kinder": 1,
    "kindergeld_je_kind": 259.0, "hochzeit": date(2026, 10, 1),
    "stk_mutter_vor": 1, "stk_mutter_nach": 5,
    "stk_vater_vor": 1, "stk_vater_nach": 3,
    "mother": {"name": "Jana", "netto_vor": 3095.0},
    "father": {"name": "Jonas", "netto_vor": 3109.0},
    "ms_wochen_vor": 6.0, "ms_wochen_nach": 8.0, "ms_override": 0.0,
    "eg_params": dict(p), "fixkosten": 3000.0,
    "plan_mother": plan("m", 37), "plan_father": plan("v", 37),
}
res = calculate_calendar_month_result(sc)
assert len(res["labels"]) == 36 and res["labels"][0] == "Feb 2027", res["labels"][:3]

# Feb 2027: Jonas voll (3109), Jana komplett Mutterschutz (ab 08.01.) => ~3095, Kindergeld 259
feb = 0
assert abs(res["v_arbeit"][feb] - 3109) < 1e-6
assert abs(res["m_mutterschutz"][feb] - 3095) < 1e-6, res["m_mutterschutz"][feb]
assert res["m_arbeit"][feb] == 0
assert res["m_basis"][feb] == 0  # komplett angerechnet
assert res["kindergeld"][feb] == 259

# April 2027: Mutterschutz endet 15.04.; Rest LM2 (bis 18.04.) + LM3 (ab 19.04.) Basis-EG
apr = 2
assert res["m_mutterschutz"][apr] > 0 and res["m_basis"][apr] > 0
# Mai 2027: LM3-Anteil (18/30 Tage) + LM4-Anteil (13/31 Tage) je 1800 EUR
mai = 3
expected_mai = 1800 * (18 / 30) + 1800 * (13 / 31)
assert abs(res["m_basis"][mai] - expected_mai) < 1e-6, res["m_basis"][mai]
assert abs(res["haushalt"][mai] - (expected_mai + 3109 + 259)) < 1e-6
# Summe Basis-EG Mutter ueber alle Monate: LM1 voll angerechnet (MS),
# LM2: 3 von 31 Tagen ohne MS, LM3-12 voll -> 1800*(3/31) + 10*1800
expected_total = 1800 * (3 / 31) + 10 * 1800
assert abs(sum(res["m_basis"]) - expected_total) < 1e-6, sum(res["m_basis"])

# Jonas' Basis-EG in LM 13/14 (ab 19.02.2028): Mrz 2028 voll 1800
mrz28 = res["labels"].index("Mrz 2028")
# Mrz 2028 = 18/29 von LM13 + 13/31 von LM14 (2028 ist Schaltjahr)
exp_v = 1800 * (18 / 29) + 1800 * (13 / 31)
assert abs(res["v_basis"][mrz28] - exp_v) < 1e-6, res["v_basis"][mrz28]
assert res["v_arbeit"][mrz28] == 0
# Konstantes Vollzeitgehalt bleibt je Kalendermonat konstant (z.B. Jun 2028)
jun28 = res["labels"].index("Jun 2028")
assert abs(res["v_arbeit"][jun28] - 3109) < 1e-6, res["v_arbeit"][jun28]

# Kumulierte Differenz konsistent
assert abs(res["diff_kum"][-1] - sum(res["diff"])) < 1e-6
# Überschuss
assert abs(res["ueberschuss"][mai] - (res["haushalt"][mai] - 3000)) < 1e-6
print("Kalendermonatsaggregation OK")

# Warnungen: Steuerklasse 3/5 akzeptiert (keine ⚠️-Steuerwarnung)
tax_warn = [w for w in res["warnings"] if "Steuerklassenkombination" in w]
assert not tax_warn, tax_warn
# Mutterschutz-Info vorhanden
assert any("Mutterschutzmonate" in w for w in res["warnings"])
print("Validierungen OK")

# 5) Tabelle (transponiert: Kennzahlen als Zeilen, Monate als Spalten)
df = build_dashboard_table(res, sc)
assert list(df.columns)[:2] == ["Feb 2027", "Mrz 2027"]
assert "Jana Summe" in df.index and "Kindergeld" in df.index
assert df.loc["Kindergeld", "Feb 2027"] == "259,00 €"
assert "Hinweise / Warnungen" in df.index
print("Dashboard-Tabelle OK — Shape:", df.shape)
print(df.iloc[:, :3].to_string())

# 6) Szenariovergleich
dfc, monthly = compare_scenarios({"A": sc, "B": sc})
assert list(dfc.columns) == ["A", "B"]
assert "Summe verfügbares Einkommen" in dfc.index
print("Szenariovergleich OK")
print("\nALLE TESTS BESTANDEN ✔")
