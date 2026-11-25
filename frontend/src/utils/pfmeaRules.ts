// frontend/src/utils/pfmeaRules.ts
import { tr } from "../i18n/tr";

export interface FailureChain {
  effects: string[];
  causes: string[];
}

type Bi = [de: string, en: string];

// Process keywords (German and English stems, matched case-insensitively) → typical failure modes.
const VERB_PATTERNS: { match: string[]; modes: Bi[] }[] = [
  { match: ["löt", "schweiß", "solder", "weld"], modes: [["Kalte Lötstelle", "Cold solder joint"], ["Lötbrücke", "Solder bridge"], ["Zu wenig Lot", "Insufficient solder"], ["Lunker in der Lötstelle", "Voids in solder joint"]] },
  { match: ["montage", "montier", "assembl"], modes: [["Montageversatz", "Assembly misalignment"], ["Teil fehlt", "Missing part"], ["Falsches Teil verbaut", "Wrong part assembled"], ["Montage zu fest/zu lose", "Assembly too tight/too loose"]] },
  { match: ["spritzg", "inject", "molding", "moulding"], modes: [["Unvollständige Füllung", "Short shot"], ["Gratbildung", "Flash"], ["Einfallstellen", "Sink marks"], ["Lufteinschlüsse", "Air bubbles"]] },
  { match: ["lackier", "beschicht", "paint", "coat"], modes: [["Ungleichmäßige Beschichtung", "Uneven coating"], ["Fehlende Beschichtung", "Missing coating"], ["Schichtdicke zu hoch/zu niedrig", "Coating too thick/too thin"], ["Farbabweichung", "Color deviation"]] },
  { match: ["einpress", "press-fit", "press fit", "pressing"], modes: [["Einpresstiefe nicht erreicht", "Press-fit depth not reached"], ["Überlast beim Einpressen", "Press-fit overload"], ["Schräg eingepresst", "Press-fit misaligned"], ["Einpressmoment instabil", "Unstable press-fit torque"]] },
  { match: ["bestück", "placement", "mount", "smt"], modes: [["Bestückversatz", "Placement offset"], ["Bauteil fehlt", "Missing component"], ["Bauteil verpolt", "Reversed component"], ["Bestückdruck auffällig", "Abnormal placement pressure"]] },
];

const FAILURE_CHAIN_MAP: { modes: string[]; effects: Bi[]; causes: Bi[] }[] = [
  { modes: ["Bestückversatz", "Placement offset"], effects: [["Funktionsverlust der Steuerplatine", "Control board function loss"], ["Gerät startet nicht", "Unit fails to start"], ["Kundenrücksendung", "Customer return"]], causes: [["Pipettenverschleiß", "Worn placement nozzle"], ["Bestückdruck zu niedrig eingestellt", "Placement pressure set too low"], ["Kalibrierdrift der Anlage", "Equipment calibration drift"], ["Bauteilversatz im Anlieferzustand", "Incoming component offset"]] },
  { modes: ["Einpresstiefe nicht erreicht", "Press-fit depth not reached"], effects: [["Lockere Verbindung", "Loose connection"], ["Störgeräusch", "Abnormal noise"], ["Sporadischer Funktionsausfall", "Intermittent function failure"]], causes: [["Pressenhub nicht kalibriert", "Press stroke not calibrated"], ["Drift des Drucksensors", "Pressure sensor drift"], ["Maßabweichung am Zukaufteil", "Incoming dimension out of tolerance"], ["Arbeitsanweisung nicht eingehalten", "SOP not followed"]] },
  { modes: ["Kalte Lötstelle", "Cold solder joint"], effects: [["Stromkreis unterbrochen", "Open circuit"], ["Signalunterbrechung", "Signal interruption"], ["Funktionsverlust", "Function loss"]], causes: [["Löttemperatur zu niedrig", "Soldering temperature too low"], ["Lotpaste zu wenig aktiv", "Insufficient solder paste activity"], ["Bestückdruck zu gering", "Insufficient placement pressure"], ["Luftfeuchtigkeit zu hoch", "Ambient humidity too high"]] },
];

const M4_CAUSE_HINTS: Record<string, Bi[]> = {
  Man: [["Arbeitsanweisung nicht eingehalten", "SOP not followed"], ["Unzureichende Schulung", "Insufficient training"], ["Ermüdung/Unachtsamkeit", "Fatigue/carelessness"], ["Personalwechsel nicht freigegeben", "Operator change not verified"]],
  Machine: [["Kalibrierdrift der Anlage", "Equipment calibration drift"], ["Anlagenverschleiß", "Equipment wear"], ["Parameterdrift der Anlage", "Equipment parameter drift"], ["Fehlende vorbeugende Instandhaltung", "Missing preventive maintenance"]],
  Material: [["Maßabweichung am Zukaufteil", "Incoming dimension out of tolerance"], ["Falscher Werkstoff angeliefert", "Wrong incoming material"], ["Hilfsstoff abgelaufen", "Expired auxiliary material"], ["Chargen uneinheitlich", "Inconsistent batches"]],
  Environment: [["Temperatur/Feuchte außerhalb des Bereichs", "Temperature/humidity out of range"], ["Staub/Sauberkeit unzureichend", "Insufficient cleanliness/dust"], ["Elektrostatik (ESD)", "Electrostatic discharge (ESD)"], ["Unzureichende Beleuchtung", "Insufficient lighting"]],
};

export function usePfmeaRules() {
  const pick = (items: Bi[]) => items.map(([de, en]) => tr(de, en));

  const generateFailureModes = (stepFunctionText: string): string[] => {
    const text = (stepFunctionText ?? "").toLowerCase();
    const hit = VERB_PATTERNS.find(({ match }) => match.some((m) => text.includes(m)));
    return hit ? pick(hit.modes) : [];
  };

  const suggestFailureChain = (failureMode: string): FailureChain => {
    const hit = FAILURE_CHAIN_MAP.find(({ modes }) => modes.includes(failureMode));
    return hit ? { effects: pick(hit.effects), causes: pick(hit.causes) } : { effects: [], causes: [] };
  };

  const suggest4MCauses = (): Record<string, string[]> =>
    Object.fromEntries(Object.entries(M4_CAUSE_HINTS).map(([k, v]) => [k, pick(v)]));

  return { generateFailureModes, suggestFailureChain, suggest4MCauses };
}
