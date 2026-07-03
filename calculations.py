"""
calculations.py
===============
Reine Berechnungslogik für den Elterngeld- & Haushaltseinkommens-Planer.

Dieses Modul ist bewusst frei von Streamlit-Abhängigkeiten, damit die
Logik unabhängig von der Oberfläche getestet werden kann.

WICHTIG: Alle Berechnungen sind vereinfachte Szenariorechnungen und
ersetzen keine Steuer- oder Rechtsberatung. Die tatsächliche
Elterngeldstelle kann abweichend rechnen.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from dateutil.relativedelta import relativedelta

# ---------------------------------------------------------------------------
# Zentrale Default-Parameter (nichts davon ist im Code "versteckt" –
# alle Werte sind im Dashboard editierbar und werden hier nur als
# Startwerte definiert).
# ---------------------------------------------------------------------------

DEFAULT_EG_PARAMS: dict[str, float | int] = {
    "ersatzrate": 0.65,          # Standard-Ersatzrate Basiselterngeld
    "basis_min": 300.0,          # Mindestbetrag Basiselterngeld
    "basis_max": 1800.0,         # Höchstbetrag Basiselterngeld
    "plus_faktor": 0.5,          # ElterngeldPlus = Faktor * Basiselterngeld
    "plus_min": 150.0,           # Mindestbetrag ElterngeldPlus
    "plus_max": 900.0,           # Höchstbetrag ElterngeldPlus
    "max_basis_lebensmonat": 14, # Basiselterngeld i. d. R. nur bis LM 14
    "max_basis_monate_elternteil": 12,
    "max_basis_monate_gesamt": 14,
    "max_parallel_basis_monate": 1,   # Parallelbezug Basiselterngeld begrenzt
    "max_wochenstunden": 32,          # zulässige Wochenstunden bei EG-Bezug
    "bonus_stunden_min": 24,          # Partnerschaftsbonus: Teilzeitkorridor
    "bonus_stunden_max": 32,
    "teilzeit_default_prozent": 50.0, # Status "Teilzeit" ohne weitere Angabe
}

MODELLE = ["Kein Elterngeld", "Basiselterngeld", "ElterngeldPlus", "Partnerschaftsbonus"]
STATUS_OPTIONEN = ["keine Arbeit", "Teilzeit", "Vollzeit"]

# Grobe Näherungsfaktoren Netto/Brutto je Steuerklasse (nur als optionale
# Schätzhilfe gedacht, KEINE echte Lohnsteuerberechnung!)
APPROX_NETTO_FAKTOR = {1: 0.63, 2: 0.66, 3: 0.72, 4: 0.63, 5: 0.52, 6: 0.48}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def clamp(value: float, lo: float, hi: float) -> float:
    """Begrenzt einen Wert auf [lo, hi]."""
    return max(lo, min(hi, value))


def eur(value: float | None) -> str:
    """Formatiert einen Betrag im deutschen Euro-Format, z. B. 1.234,56 €."""
    if value is None:
        return ""
    s = f"{value:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def overlap_days(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    """Anzahl der Tage, die sich zwei (inklusive) Zeiträume überlappen."""
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    return max(0, (end - start).days + 1)


def approx_netto_from_brutto(brutto: float, steuerklasse: int,
                             kirchensteuer: bool, kv_zusatz_prozent: float) -> float:
    """Sehr grobe Netto-Schätzung aus dem Brutto (optionale Hilfsfunktion).

    Es wird ein pauschaler Faktor je Steuerklasse verwendet und um
    Kirchensteuer sowie den halben KV-Zusatzbeitrag korrigiert.
    Dies ist ausdrücklich nur eine Näherung.
    """
    faktor = APPROX_NETTO_FAKTOR.get(int(steuerklasse), 0.63)
    netto = brutto * faktor
    if kirchensteuer:
        netto *= 0.985  # pauschaler Abschlag für Kirchensteuer
    netto -= brutto * (kv_zusatz_prozent / 100.0) / 2.0
    return max(0.0, netto)


# ---------------------------------------------------------------------------
# Lebensmonate & Kalendermonate
# ---------------------------------------------------------------------------

@dataclass
class LifeMonth:
    """Ein Lebensmonat des Kindes (z. B. 19.02. bis 18.03.)."""
    index: int
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def label(self) -> str:
        return (f"LM {self.index} ({self.start.strftime('%d.%m.%Y')}"
                f" – {self.end.strftime('%d.%m.%Y')})")


def calculate_life_months(birth_date: date, count: int) -> list[LifeMonth]:
    """Berechnet `count` Lebensmonate ab Geburtsdatum.

    Lebensmonat m: birth + (m-1) Monate  bis  birth + m Monate - 1 Tag.
    Beispiel: Geburt 19.02.2027 -> LM 1: 19.02.2027–18.03.2027.
    """
    months = []
    for m in range(1, count + 1):
        start = birth_date + relativedelta(months=m - 1)
        end = birth_date + relativedelta(months=m) - timedelta(days=1)
        months.append(LifeMonth(index=m, start=start, end=end))
    return months


def get_calendar_months(birth_date: date, horizon: int) -> list[tuple[date, date, str]]:
    """Liste der Kalendermonate (Monatsanfang, Monatsende, Label)
    ab dem Geburtsmonat über `horizon` Monate."""
    result = []
    labels_de = ["Jan", "Feb", "Mrz", "Apr", "Mai", "Jun",
                 "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
    y, m = birth_date.year, birth_date.month
    for _ in range(horizon):
        start = date(y, m, 1)
        end = date(y, m, calendar.monthrange(y, m)[1])
        result.append((start, end, f"{labels_de[m - 1]} {y}"))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return result


def map_life_months_to_calendar_months(
    life_months: list[LifeMonth],
    cal_start: date,
    cal_end: date,
) -> list[tuple[LifeMonth, float, int]]:
    """Ermittelt für einen Kalendermonat alle überlappenden Lebensmonate.

    Rückgabe: Liste von (LifeMonth, Anteil am Lebensmonat, Überlappungstage).
    Der Anteil dient der zeitanteiligen Aufteilung von Monatsbeträgen
    (z. B. Elterngeld), die je Lebensmonat gezahlt werden.
    """
    mapping = []
    for lm in life_months:
        days = overlap_days(lm.start, lm.end, cal_start, cal_end)
        if days > 0:
            mapping.append((lm, days / lm.days, days))
    return mapping


# ---------------------------------------------------------------------------
# Mutterschutz
# ---------------------------------------------------------------------------

def calculate_maternity_period(birth_date: date,
                               weeks_before: float,
                               weeks_after: float) -> tuple[date, date]:
    """Mutterschutzzeitraum: standardmäßig 6 Wochen vor bis 8 Wochen nach Geburt."""
    start = birth_date - timedelta(days=round(weeks_before * 7))
    end = birth_date + timedelta(days=round(weeks_after * 7)) - timedelta(days=1)
    return start, end


def calculate_maternity_benefits(netto_vor: float,
                                 override_monatsbetrag: float | None = None) -> float:
    """Mutterschaftsleistung je (vollem) Monat.

    Vereinfachung: Mutterschaftsgeld (Krankenkasse) + Arbeitgeberzuschuss
    ergeben zusammen näherungsweise das bisherige Netto. Ist ein echter
    Wert bekannt, kann er als Override gepflegt werden.
    """
    if override_monatsbetrag is not None and override_monatsbetrag > 0:
        return override_monatsbetrag
    return netto_vor


def maternity_life_months(life_months: list[LifeMonth], ms_end: date) -> list[int]:
    """Lebensmonate (nach Geburt), die (teilweise) im Mutterschutz liegen.

    Diese Monate gelten für die Mutter als Elterngeld-relevante Monate
    (Basiselterngeld-Monate), da Mutterschaftsleistungen angerechnet werden.
    """
    return [lm.index for lm in life_months if lm.start <= ms_end]


# ---------------------------------------------------------------------------
# Einkommen nach Geburt & Elterngeld je Lebensmonat
# ---------------------------------------------------------------------------

def calculate_parent_income_after_birth(row: dict[str, Any],
                                        netto_vor: float,
                                        eg_params: dict) -> float:
    """Netto-Arbeitseinkommen eines Elternteils in einem Lebensmonat.

    Priorität der Eingaben:
      1. fixer Monatswert ("Netto fix (€)"), falls > 0
      2. Prozentwert vom bisherigen Netto ("% vom Netto"), falls > 0
      3. Beschäftigungsstatus: keine Arbeit = 0 %, Teilzeit = Default-%,
         Vollzeit = 100 %
    """
    fix = float(row.get("Netto fix (€)") or 0.0)
    if fix > 0:
        return fix
    pct = float(row.get("% vom Netto") or 0.0)
    if pct > 0:
        return netto_vor * pct / 100.0
    status = row.get("Status") or "keine Arbeit"
    if status == "Vollzeit":
        return netto_vor
    if status == "Teilzeit":
        return netto_vor * float(eg_params["teilzeit_default_prozent"]) / 100.0
    return 0.0


def calculate_parental_allowance(modell: str,
                                 netto_vor: float,
                                 netto_nach: float,
                                 eg_params: dict) -> float:
    """Elterngeldbetrag für einen Lebensmonat.

    Basiselterngeld     = Ersatzrate * (Netto vor Geburt - Netto nach Geburt),
                          begrenzt auf [basis_min, basis_max]
    ElterngeldPlus      = plus_faktor * Basiselterngeld,
                          begrenzt auf [plus_min, plus_max]
    Partnerschaftsbonus = wie ElterngeldPlus behandelt
    """
    if modell == "Kein Elterngeld":
        return 0.0
    diff = max(0.0, netto_vor - netto_nach)
    basis = clamp(eg_params["ersatzrate"] * diff,
                  eg_params["basis_min"], eg_params["basis_max"])
    if modell == "Basiselterngeld":
        return basis
    # ElterngeldPlus & Partnerschaftsbonus
    return clamp(basis * eg_params["plus_faktor"],
                 eg_params["plus_min"], eg_params["plus_max"])


# ---------------------------------------------------------------------------
# Validierungen / Plausibilitätsprüfungen (Warnungen, keine harten Blocker)
# ---------------------------------------------------------------------------

def validate_tax_classes(stk_mutter: int, stk_vater: int) -> list[str]:
    """Prüft die Steuerklassenkombination der Ehegatten."""
    warnings = []
    combo = {stk_mutter, stk_vater}
    valid_combos = [{3, 5}, {4}, {4, 4}]
    if combo == {3, 5}:
        pass  # 3/5 ist eine zulässige Ehegattenkombination
    elif combo == {4}:
        pass  # 4/4 ebenfalls zulässig
    else:
        warnings.append(
            f"⚠️ Steuerklassenkombination {stk_mutter}/{stk_vater} ist für "
            "Ehegatten unüblich bzw. unzulässig (üblich: 3/5, 5/3 oder 4/4). "
            "Bitte prüfen."
        )
    warnings.append(
        "ℹ️ Die Steuerklasse beeinflusst das Netto und damit die Höhe des "
        "Elterngelds. Ein Steuerklassenwechsel muss i. d. R. rechtzeitig "
        "vor dem Mutterschutz erfolgen, um für die Elterngeldberechnung "
        "berücksichtigt zu werden."
    )
    return warnings


def validate_elterngeld_rules(plan_mutter: list[dict],
                              plan_vater: list[dict],
                              eg_params: dict,
                              ms_lm_mutter: list[int]) -> list[str]:
    """Prüft die Elterngeldplanung auf typische Regelverstöße.

    Gibt Warnungen zurück; die Berechnung wird dadurch nicht blockiert.
    """
    w: list[str] = []
    max_lm = int(eg_params["max_basis_lebensmonat"])
    max_parent = int(eg_params["max_basis_monate_elternteil"])
    max_total = int(eg_params["max_basis_monate_gesamt"])
    max_parallel = int(eg_params["max_parallel_basis_monate"])
    max_std = float(eg_params["max_wochenstunden"])
    b_lo = float(eg_params["bonus_stunden_min"])
    b_hi = float(eg_params["bonus_stunden_max"])

    def basis_months(plan: list[dict]) -> set[int]:
        return {int(r["Lebensmonat"]) for r in plan
                if r.get("Elterngeld-Modell") == "Basiselterngeld"}

    basis_m = basis_months(plan_mutter) | set(ms_lm_mutter)
    basis_v = basis_months(plan_vater)

    if ms_lm_mutter:
        w.append(
            "ℹ️ Die Mutterschutzmonate nach der Geburt (Lebensmonate "
            f"{', '.join(map(str, ms_lm_mutter))}) gelten für die Mutter "
            "automatisch als Basiselterngeld-Monate. Mutterschaftsleistungen "
            "werden auf das Elterngeld angerechnet."
        )

    # Basiselterngeld nur in den ersten 14 Lebensmonaten
    for name, months in (("Mutter", basis_m), ("Vater", basis_v)):
        late = sorted(m for m in months if m > max_lm)
        if late:
            w.append(
                f"⚠️ {name}: Basiselterngeld ist grundsätzlich nur in den "
                f"ersten {max_lm} Lebensmonaten möglich "
                f"(geplant in LM {', '.join(map(str, late))})."
            )

    # Max. Basiselterngeld-Monate je Elternteil
    if len(basis_m) > max_parent:
        w.append(
            f"⚠️ Mutter: {len(basis_m)} Basiselterngeld-Monate geplant "
            f"(inkl. Mutterschutz), maximal {max_parent} je Elternteil möglich."
        )
    if len(basis_v) > max_parent:
        w.append(
            f"⚠️ Vater: {len(basis_v)} Basiselterngeld-Monate geplant, "
            f"maximal {max_parent} je Elternteil möglich."
        )

    # Gesamtsumme Basiselterngeld
    total = len(basis_m) + len(basis_v)
    if total > max_total:
        w.append(
            f"⚠️ Zusammen {total} Basiselterngeld-Monate geplant, "
            f"gemeinsam sind maximal {max_total} Monate möglich."
        )

    # Parallelbezug Basiselterngeld
    parallel = sorted(basis_m & basis_v)
    if len(parallel) > max_parallel:
        w.append(
            f"⚠️ Paralleler Basiselterngeld-Bezug in LM "
            f"{', '.join(map(str, parallel))}: Parallelbezug ist nur begrenzt "
            f"(i. d. R. max. {max_parallel} Monat) möglich."
        )

    # Wochenstunden > 32 bei Elterngeldbezug
    for name, plan in (("Mutter", plan_mutter), ("Vater", plan_vater)):
        for r in plan:
            if (r.get("Elterngeld-Modell") != "Kein Elterngeld"
                    and float(r.get("Wochenstunden") or 0) > max_std):
                w.append(
                    f"⚠️ {name}, LM {r['Lebensmonat']}: "
                    f"{r['Wochenstunden']} Wochenstunden bei Elterngeldbezug "
                    f"überschreiten die zulässige Grenze von {max_std:.0f} h."
                )

    # Partnerschaftsbonus: beide gleichzeitig in Teilzeit (Korridor)
    bonus_m = {int(r["Lebensmonat"]): r for r in plan_mutter
               if r.get("Elterngeld-Modell") == "Partnerschaftsbonus"}
    bonus_v = {int(r["Lebensmonat"]): r for r in plan_vater
               if r.get("Elterngeld-Modell") == "Partnerschaftsbonus"}
    for lm in sorted(set(bonus_m) | set(bonus_v)):
        rm, rv = bonus_m.get(lm), bonus_v.get(lm)
        ok = (
            rm is not None and rv is not None
            and b_lo <= float(rm.get("Wochenstunden") or 0) <= b_hi
            and b_lo <= float(rv.get("Wochenstunden") or 0) <= b_hi
        )
        if not ok:
            w.append(
                f"⚠️ Partnerschaftsbonus in LM {lm}: warnungsfrei nur, wenn "
                f"BEIDE Eltern gleichzeitig den Bonus beziehen und jeweils "
                f"{b_lo:.0f}–{b_hi:.0f} Wochenstunden in Teilzeit arbeiten."
            )

    w.append(
        "ℹ️ Elterngeld ist steuerfrei, unterliegt aber dem "
        "Progressionsvorbehalt und kann die Steuerlast auf das übrige "
        "Einkommen erhöhen."
    )
    return w


# ---------------------------------------------------------------------------
# Kernberechnung: Kalendermonatsergebnisse & Dashboard-Tabelle
# ---------------------------------------------------------------------------

def _plan_lookup(plan: list[dict]) -> dict[int, dict]:
    return {int(r["Lebensmonat"]): r for r in plan}


def calculate_calendar_month_result(scenario: dict) -> dict:
    """Berechnet alle Kennzahlen je Kalendermonat für ein Szenario.

    Kernprinzip:
      * Eingaben (Elterngeldmodell, Status, ...) gelten je LEBENSMONAT.
      * Ausgewertet wird je KALENDERMONAT.
      * Beträge, die je Lebensmonat anfallen, werden zeitanteilig
        (nach Tagen) auf die überlappenden Kalendermonate verteilt.

    Rückgabe: dict mit 'labels' (Monatslabels) und je Kennzahl eine Liste
    von Werten, außerdem 'hinweise' (Liste von Strings je Monat) und
    'warnings' (globale Warnliste).
    """
    birth: date = scenario["birth_date"]
    horizon: int = int(scenario["horizon"])
    netto_vor_m: float = float(scenario["mother"]["netto_vor"])
    netto_vor_v: float = float(scenario["father"]["netto_vor"])
    eg = scenario["eg_params"]
    kindergeld = float(scenario["kindergeld_je_kind"]) * int(scenario["anzahl_kinder"])
    fixkosten = float(scenario.get("fixkosten", 0.0))

    plan_m = scenario["plan_mother"]
    plan_v = scenario["plan_father"]
    lookup_m = _plan_lookup(plan_m)
    lookup_v = _plan_lookup(plan_v)

    n_lm = max(len(plan_m), len(plan_v), horizon + 1)
    life_months = calculate_life_months(birth, n_lm)
    cal_months = get_calendar_months(birth, horizon)

    ms_start, ms_end = calculate_maternity_period(
        birth, scenario["ms_wochen_vor"], scenario["ms_wochen_nach"])
    ms_monatsbetrag = calculate_maternity_benefits(
        netto_vor_m, scenario.get("ms_override") or None)
    ms_lm = maternity_life_months(life_months, ms_end)

    # Vorberechnung je Lebensmonat und Elternteil
    def precompute(plan_lookup: dict[int, dict], netto_vor: float,
                   is_mother: bool) -> dict[int, dict]:
        out = {}
        for lm in life_months:
            row = plan_lookup.get(lm.index, {})
            netto_nach = calculate_parent_income_after_birth(row, netto_vor, eg)
            modell = row.get("Elterngeld-Modell", "Kein Elterngeld")
            eg_betrag = calculate_parental_allowance(modell, netto_vor,
                                                     netto_nach, eg)
            out[lm.index] = {
                "netto_nach": netto_nach,
                "modell": modell,
                "eg_betrag": eg_betrag,
                "sonstige": float(row.get("Sonstige Einnahmen (€)") or 0.0),
                "stunden": float(row.get("Wochenstunden") or 0.0),
                "bemerkung": str(row.get("Bemerkung") or ""),
            }
        return out

    pre_m = precompute(lookup_m, netto_vor_m, True)
    pre_v = precompute(lookup_v, netto_vor_v, False)

    keys = [
        "m_arbeit", "m_mutterschutz", "m_basis", "m_plus", "m_bonus",
        "m_sonstige", "m_summe",
        "v_arbeit", "v_basis", "v_plus", "v_bonus", "v_sonstige", "v_summe",
        "kindergeld", "haushalt", "diff", "diff_kum",
        "fixkosten", "ueberschuss",
    ]
    res: dict[str, list] = {k: [] for k in keys}
    res["labels"] = [c[2] for c in cal_months]
    res["hinweise"] = []

    netto_vor_gesamt = netto_vor_m + netto_vor_v
    kum = 0.0

    for cal_start, cal_end, _label in cal_months:
        vals = {k: 0.0 for k in keys}
        hinweise: list[str] = []
        # Tage im Kalendermonat: Basis für Gehalts- und Mutterschutzanteile
        # (laufende Monatsbezüge), während Elterngeld je LEBENSMONAT gezahlt
        # und daher über den Lebensmonatsanteil verteilt wird.
        days_in_cal = (cal_end - cal_start).days + 1

        # ---- Zeitraum VOR der Geburt innerhalb des ersten Kalendermonats ----
        if cal_start < birth:
            pre_end = min(cal_end, birth - timedelta(days=1))
            # Vater: normales Arbeitseinkommen anteilig
            d = overlap_days(cal_start, pre_end, cal_start, pre_end)
            vals["v_arbeit"] += netto_vor_v * d / days_in_cal
            # Mutter: Mutterschutz beginnt i. d. R. vor der Geburt
            ms_pre_days = overlap_days(cal_start, pre_end, ms_start,
                                       birth - timedelta(days=1))
            work_days = d - ms_pre_days
            vals["m_arbeit"] += netto_vor_m * work_days / days_in_cal
            vals["m_mutterschutz"] += ms_monatsbetrag * ms_pre_days / days_in_cal
            if ms_pre_days > 0:
                hinweise.append("Mutterschutz (vor Geburt)")

        # ---- Lebensmonate, die in diesen Kalendermonat fallen ----
        for lm, share, _days in map_life_months_to_calendar_months(
                life_months, cal_start, cal_end):

            # ----- Mutter -----
            pm = pre_m[lm.index]
            # Mutterschutz-Tage innerhalb dieses Lebensmonats
            ms_days_lm = overlap_days(lm.start, lm.end, birth, ms_end)
            # Anteil Mutterschutz-Tage, die zusätzlich im Kalendermonat liegen
            ms_days_cal = overlap_days(lm.start, min(lm.end, ms_end),
                                       cal_start, cal_end) if ms_days_lm else 0
            lm_days_cal = overlap_days(lm.start, lm.end, cal_start, cal_end)
            work_days_cal = lm_days_cal - ms_days_cal

            # Monatsbezüge (Gehalt, Mutterschutzleistung) auf Kalendertage
            # normieren -> konstantes Gehalt bleibt je Kalendermonat konstant
            vals["m_mutterschutz"] += ms_monatsbetrag * ms_days_cal / days_in_cal
            vals["m_arbeit"] += pm["netto_nach"] * work_days_cal / days_in_cal
            vals["m_sonstige"] += pm["sonstige"] * share

            # Elterngeld der Mutter: in Mutterschutz-Tagen wird die
            # Mutterschaftsleistung angerechnet -> vereinfachend kein
            # zusätzliches Elterngeld für diese Tage.
            eg_share = (work_days_cal / lm.days) if ms_days_lm else share
            betrag = pm["eg_betrag"] * eg_share
            if pm["modell"] == "Basiselterngeld":
                vals["m_basis"] += betrag
            elif pm["modell"] == "ElterngeldPlus":
                vals["m_plus"] += betrag
            elif pm["modell"] == "Partnerschaftsbonus":
                vals["m_bonus"] += betrag

            if ms_days_cal > 0:
                hinweise.append(f"Mutterschutz bis {ms_end.strftime('%d.%m.%Y')}"
                                if lm.index == ms_lm[-1] else "Mutterschutz")
                if pm["modell"] != "Kein Elterngeld":
                    hinweise.append("EG-Anrechnung Mutterschaftsleistung")
            if (pm["modell"] != "Kein Elterngeld"
                    and pm["stunden"] > eg["max_wochenstunden"]):
                hinweise.append(f"Mutter > {eg['max_wochenstunden']:.0f} h/Woche")
            if pm["bemerkung"]:
                hinweise.append(f"Mutter LM{lm.index}: {pm['bemerkung']}")

            # ----- Vater -----
            pv = pre_v[lm.index]
            lm_days_cal_v = overlap_days(lm.start, lm.end, cal_start, cal_end)
            vals["v_arbeit"] += pv["netto_nach"] * lm_days_cal_v / days_in_cal
            vals["v_sonstige"] += pv["sonstige"] * share
            betrag_v = pv["eg_betrag"] * share
            if pv["modell"] == "Basiselterngeld":
                vals["v_basis"] += betrag_v
            elif pv["modell"] == "ElterngeldPlus":
                vals["v_plus"] += betrag_v
            elif pv["modell"] == "Partnerschaftsbonus":
                vals["v_bonus"] += betrag_v
            if (pv["modell"] != "Kein Elterngeld"
                    and pv["stunden"] > eg["max_wochenstunden"]):
                hinweise.append(f"Vater > {eg['max_wochenstunden']:.0f} h/Woche")
            if pv["bemerkung"]:
                hinweise.append(f"Vater LM{lm.index}: {pv['bemerkung']}")

        # ---- Summen ----
        vals["m_summe"] = (vals["m_arbeit"] + vals["m_mutterschutz"]
                           + vals["m_basis"] + vals["m_plus"]
                           + vals["m_bonus"] + vals["m_sonstige"])
        vals["v_summe"] = (vals["v_arbeit"] + vals["v_basis"] + vals["v_plus"]
                           + vals["v_bonus"] + vals["v_sonstige"])
        vals["kindergeld"] = kindergeld
        vals["haushalt"] = vals["m_summe"] + vals["v_summe"] + vals["kindergeld"]
        vals["diff"] = vals["haushalt"] - netto_vor_gesamt
        kum += vals["diff"]
        vals["diff_kum"] = kum
        vals["fixkosten"] = fixkosten
        vals["ueberschuss"] = vals["haushalt"] - fixkosten

        for k in keys:
            res[k].append(vals[k])
        # Hinweise deduplizieren, Reihenfolge erhalten
        res["hinweise"].append("; ".join(dict.fromkeys(hinweise)))

    # Globale Warnungen
    res["warnings"] = (
        validate_tax_classes(scenario["stk_mutter_nach"],
                             scenario["stk_vater_nach"])
        + validate_elterngeld_rules(plan_m, plan_v, eg, ms_lm)
    )
    res["ms_zeitraum"] = (ms_start, ms_end)
    res["ms_lebensmonate"] = ms_lm
    res["life_months"] = life_months
    res["netto_vor_gesamt"] = netto_vor_gesamt
    return res


def build_dashboard_table(res: dict, scenario: dict):
    """Baut die transponierte Dashboard-Tabelle:
    Spalten = Kalendermonate, Zeilen = Kennzahlen (Euro-formatiert)."""
    import pandas as pd

    nm = scenario["mother"]["name"]
    nv = scenario["father"]["name"]
    rows = [
        (f"{nm} Arbeitseinkommen netto", "m_arbeit"),
        (f"{nm} Mutterschutzleistung", "m_mutterschutz"),
        (f"{nm} Basiselterngeld", "m_basis"),
        (f"{nm} ElterngeldPlus", "m_plus"),
        (f"{nm} Partnerschaftsbonus", "m_bonus"),
        (f"{nm} sonstige Einnahmen", "m_sonstige"),
        (f"{nm} Summe", "m_summe"),
        (f"{nv} Arbeitseinkommen netto", "v_arbeit"),
        (f"{nv} Basiselterngeld", "v_basis"),
        (f"{nv} ElterngeldPlus", "v_plus"),
        (f"{nv} Partnerschaftsbonus", "v_bonus"),
        (f"{nv} sonstige Einnahmen", "v_sonstige"),
        (f"{nv} Summe", "v_summe"),
        ("Kindergeld", "kindergeld"),
        ("Gemeinsames Netto-Arbeitseinkommen", None),  # berechnet unten
        ("Gemeinsames verfügbares Netto-Haushaltseinkommen", "haushalt"),
        ("Differenz zum gemeinsamen Netto vor Geburt", "diff"),
        ("Kumulierte Differenz seit Geburt", "diff_kum"),
        ("Fixkosten", "fixkosten"),
        ("Überschuss nach Fixkosten", "ueberschuss"),
    ]

    data: dict[str, list[str]] = {}
    arbeit_gesamt = [a + b for a, b in zip(res["m_arbeit"], res["v_arbeit"])]
    for title, key in rows:
        if key is None:
            values = arbeit_gesamt
        else:
            values = res[key]
        data[title] = [eur(v) for v in values]
    data["Hinweise / Warnungen"] = res["hinweise"]

    df = pd.DataFrame(data, index=res["labels"]).T
    df.index.name = "Kennzahl"
    return df


# ---------------------------------------------------------------------------
# Szenariovergleich
# ---------------------------------------------------------------------------

def scenario_metrics(res: dict) -> dict:
    """Vergleichskennzahlen für ein berechnetes Szenario."""
    hh = res["haushalt"]
    n = len(hh)
    idx_min = min(range(n), key=lambda i: hh[i]) if n else 0
    ueberschuss = res["ueberschuss"]
    return {
        "Summe verfügbares Einkommen": sum(hh),
        "Ø monatliches Einkommen": sum(hh) / n if n else 0.0,
        "Niedrigster Monatswert": hh[idx_min] if n else 0.0,
        "Monat mit niedrigstem Einkommen": res["labels"][idx_min] if n else "-",
        "Kumulierte Differenz zum Vor-Geburt-Netto":
            res["diff_kum"][-1] if n else 0.0,
        "Ø monatlicher Überschuss nach Fixkosten":
            sum(ueberschuss) / n if n else 0.0,
    }


def compare_scenarios(scenarios: dict[str, dict]):
    """Vergleicht mehrere Szenarien.

    Rückgabe: (metrics_df, monthly) — Kennzahlen-Tabelle (Szenarien als
    Spalten) und je Szenario die Monatsreihen für Diagramme.
    """
    import pandas as pd

    metrics: dict[str, dict] = {}
    monthly: dict[str, dict] = {}
    for name, sc in scenarios.items():
        res = calculate_calendar_month_result(sc)
        m = scenario_metrics(res)
        metrics[name] = {
            k: (eur(v) if isinstance(v, (int, float)) else v)
            for k, v in m.items()
        }
        monthly[name] = {"labels": res["labels"],
                         "haushalt": res["haushalt"],
                         "diff_kum": res["diff_kum"]}
    df = pd.DataFrame(metrics)
    df.index.name = "Kennzahl"
    return df, monthly
