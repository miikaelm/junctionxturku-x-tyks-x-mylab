import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { api, type CdsCard, type CdsSuggestion, type Infection, type Patient } from "../api/client";
import { fmtDate } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { ROLES } from "../lib/roles";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

const INBOX_POLL_MS = 5000;
const SELECT = "aei-antibiotic-choice";
const SIGN = "aei-antibiotic-sign";
const VIEW = "aei-patient-context";

type Tab = "overview" | "lab" | "meds";

interface Order {
  id: string;
  code: string;
  name: string;
  infection: string;
  route: string;
  dose: string;
  signed: string;
  override?: string;
}

interface Exchange {
  hook: string;
  request: unknown;
  response: unknown;
}

/**
 * V11 mock patient record (API-05), labelled as a demo. It stands in for the hospital's own
 * system and knows nothing about AEI's internals: it calls AEI's CDS Hooks services when a record
 * opens (patient-view → risk information), when an antibiotic is chosen (order-select) and when the
 * order is signed (order-sign: only warnings, with override reasons and "change to" suggestions),
 * and it shows what AEI pushes to its webhook. The ward list holds the demo patients
 * (config EHR_DEMO, docs/DEMO.md).
 */
export function MockEhr({ patientId }: { patientId?: string }) {
  const { asOf, setAsOf, meta, role } = useApp();
  const demo = meta.ehr_demo;
  const wardName = meta.wards.find((w) => w.ward_code === demo.ward)?.ward_en ?? demo.ward;
  const [search, setSearch] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const [orders, setOrders] = useState<Record<string, Order[]>>({});
  const [exchange, setExchange] = useState<Exchange | null>(null);
  const [viewCards, setViewCards] = useState<CdsCard[] | null>(null);
  const patient = useFetch(
    (signal) => (patientId ? api.patient(patientId, asOf, signal) : Promise.resolve(null)),
    [patientId, asOf, meta.data_version],
  );

  useEffect(() => {
    setViewCards(null);
    setTab("overview");
    if (!patientId) return;
    const body = { hook: "patient-view", hookInstance: crypto.randomUUID(), context: { patientId, userId: "Practitioner/demo" } };
    api
      .cds(VIEW, body, asOf)
      .then((r) => {
        setViewCards(r.cards);
        setExchange({ hook: "patient-view", request: body, response: r });
      })
      .catch(() => setViewCards([]));
  }, [patientId, asOf]);

  const p = patient.data;
  const stay = p ? currentStay(p) : null;
  const myOrders = (patientId && orders[patientId]) || [];

  return (
    <div className="ehr">
      <header className="ehr-top">
        <span className="ehr-logo" aria-hidden>
          ✚
        </span>
        <strong>Potilastieto</strong>
        <span className="ehr-sys">Patient record system</span>
        <span className="ehr-demo-badge" title="A mock of a hospital's own system, to show how AEI plugs into it">
          DEMO EHR · not a real system
        </span>
        <span className="ehr-user">
          Dr Demo · {wardName} · {fmtDate(asOf)}
        </span>
        <a href={href(ROLES[role.role].home)}>← Back to AEI</a>
      </header>

      {asOf !== demo.as_of && (
        <div className="ehr-datebar">
          The demo patients are set up for <strong>{fmtDate(demo.as_of)}</strong> (you are on {fmtDate(asOf)}).{" "}
          <button type="button" onClick={() => setAsOf(demo.as_of)}>
            Go to {fmtDate(demo.as_of)}
          </button>
        </div>
      )}

      <div className="ehr-body">
        <aside className="ehr-side">
          <h2 className="ehr-side-title">
            Ward list · {wardName} ({demo.ward})
          </h2>
          <ul className="ehr-list">
            {demo.patients.map((id) => (
              <WardListItem key={id} id={id} active={id === patientId} />
            ))}
          </ul>
          <form
            className="ehr-search"
            onSubmit={(e) => {
              e.preventDefault();
              if (search.trim()) window.location.hash = href({ view: "ehr", id: search.trim().toUpperCase() });
            }}
          >
            <label>
              Open another record
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Patient ID, e.g. P001234" />
            </label>
            <button type="submit">Open</button>
          </form>
          <MockInbox patientId={patientId} />
        </aside>

        <main className="ehr-main">
          {!patientId && <Welcome demoDate={demo.as_of} />}
          {patient.error && <p className="ehr-error">No record for {patientId} up to {fmtDate(asOf)}.</p>}
          {p && (
            <>
              <section className="ehr-banner">
                <div>
                  <h1>
                    Patient {p.patient_id}
                    <span className="ehr-banner-sub">
                      {p.sex === "F" ? "Female" : "Male"}, {p.age} y (born {p.birth_year}) · home area {p.home_area}
                    </span>
                  </h1>
                  <p>
                    {stay ? (
                      <>
                        Inpatient on <strong>{stay.ward}</strong> since {fmtDate(stay.admitted)} (day {stay.day})
                      </>
                    ) : (
                      <>Last visit {p.last_ward}, {fmtDate(p.last_sample)}</>
                    )}
                  </p>
                </div>
                <RiskBadges cards={viewCards} />
              </section>

              <section className="ehr-risk">
                <h2>Risk information</h2>
                <p className="ehr-hint">From AEI when this record opened (CDS Hooks patient-view).</p>
                {viewCards === null ? (
                  <p className="ehr-hint">Asking AEI…</p>
                ) : viewCards.length === 0 ? (
                  <p className="ehr-ok">No notices: no known resistant-bacteria carriage, no alerts involving this patient.</p>
                ) : (
                  viewCards.map((c) => <Card key={c.uuid} card={c} />)
                )}
              </section>

              <nav className="ehr-tabs" role="tablist">
                {(
                  [
                    ["overview", "Overview"],
                    ["lab", `Lab results (${p.samples.length})`],
                    ["meds", `Medication orders (${myOrders.length})`],
                  ] as [Tab, string][]
                ).map(([k, l]) => (
                  <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
                    {l}
                  </button>
                ))}
              </nav>

              {tab === "overview" && (
                <section className="ehr-panel">
                  <h2>Overview</h2>
                  <LatestResult p={p} />
                  <h3>Medication orders</h3>
                  <OrderList orders={myOrders} />
                  <button type="button" className="ehr-primary" onClick={() => setTab("meds")}>
                    + New antibiotic order
                  </button>
                </section>
              )}
              {tab === "lab" && <LabResults p={p} />}
              {tab === "meds" && (
                <section className="ehr-panel">
                  <h2>Medication orders</h2>
                  <OrderList orders={myOrders} />
                  <OrderForm
                    key={p.patient_id}
                    patient={p}
                    defaultWard={stay?.ward ?? p.last_ward}
                    onExchange={setExchange}
                    onSigned={(o) => setOrders((all) => ({ ...all, [p.patient_id]: [o, ...(all[p.patient_id] ?? [])] }))}
                  />
                </section>
              )}

              {exchange && (
                <details className="ehr-panel ehr-dev">
                  <summary>Developer view: last CDS Hooks call ({exchange.hook})</summary>
                  <pre>{JSON.stringify(exchange.request, null, 2)}</pre>
                  <pre>{JSON.stringify(exchange.response, null, 2)}</pre>
                </details>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function Welcome({ demoDate }: { demoDate: string }) {
  return (
    <section className="ehr-panel ehr-welcome">
      <h2>Mock patient record: what to try</h2>
      <p>
        This screen stands in for the hospital's own patient record. It doesn't contain AEI: it only calls AEI's
        integration services, the way a real record system would, and shows the answers as notices.
      </p>
      <ol>
        <li>Open a patient from the ward list: AEI's risk information appears (known carriage, outbreaks they are part of).</li>
        <li>
          Under <em>Medication orders</em>, choose an indication and an antibiotic: AEI checks the choice against this
          ward's resistance and the patient's own results.
        </li>
        <li>Sign the order: AEI is asked again and only interrupts when there is a reason, with alternatives to switch to.</li>
      </ol>
      <p className="ehr-hint">The ward list is set up for {fmtDate(demoDate)} (docs/DEMO.md).</p>
    </section>
  );
}

function WardListItem({ id, active }: { id: string; active: boolean }) {
  const { asOf, meta } = useApp();
  const { data } = useFetch((signal) => api.patient(id, asOf, signal), [id, asOf, meta.data_version]);
  const stay = data ? currentStay(data) : null;
  return (
    <li className={active ? "is-active" : ""}>
      <a href={href({ view: "ehr", id })}>
        <strong>{id}</strong>
        {data && (
          <span className="ehr-hint">
            {" "}
            {data.sex === "F" ? "F" : "M"} {data.age} y{stay ? ` · day ${stay.day}` : ""}
          </span>
        )}
      </a>
    </li>
  );
}

/** Small risk icons in the banner, as real record systems show carriage. */
function RiskBadges({ cards }: { cards: CdsCard[] | null }) {
  const tags = (cards ?? [])
    .map((c) => c.summary.match(/Known (\w+) carrier/)?.[1])
    .filter((t): t is string => Boolean(t));
  if (tags.length === 0) return null;
  return (
    <div className="ehr-badges" aria-label="Risk information">
      {tags.map((t) => (
        <span key={t} className="ehr-badge">
          {t}
        </span>
      ))}
    </div>
  );
}

function currentStay(p: Patient): { ward: string; admitted: string; day: number } | null {
  const s = p.samples.find((x) => x.admission_date);
  if (!s || s.date !== p.samples[0].date || !s.admission_date) return null;
  const day = Math.round((Date.parse(p.as_of) - Date.parse(s.admission_date)) / 86400000) + 1;
  return { ward: s.ward, admitted: s.admission_date, day };
}

function LatestResult({ p }: { p: Patient }) {
  const s = p.samples[0];
  return (
    <p>
      Latest culture: {fmtDate(s.date)}, {s.specimen} ({s.ward}):{" "}
      {s.isolates.length === 0
        ? s.result === "negative"
          ? "no growth"
          : s.result.replace("_", " ")
        : s.isolates.map((i) => `${i.organism}${i.phenotypes.length ? ` (${i.phenotypes.join(", ")})` : ""}`).join(", ")}
      .
    </p>
  );
}

function LabResults({ p }: { p: Patient }) {
  const { meta } = useApp();
  const name = (code: string) => meta.antibiotics.find((a) => a.code === code)?.name ?? code;
  return (
    <section className="ehr-panel">
      <h2>Microbiology results</h2>
      <table className="ehr-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Ward</th>
            <th>Specimen</th>
            <th>Result</th>
            <th>Susceptibility (S / R)</th>
          </tr>
        </thead>
        <tbody>
          {p.samples.map((s) => (
            <tr key={s.culture_id}>
              <td className="mono">{s.date}</td>
              <td>{s.ward}</td>
              <td>{s.specimen}</td>
              <td>
                {s.isolates.length === 0
                  ? s.result === "negative"
                    ? "No growth"
                    : s.result.replace("_", " ")
                  : s.isolates.map((i) => (
                      <div key={i.isolate_id}>
                        <em>{i.organism}</em> {i.quantity}
                        {i.phenotypes.map((ph) => (
                          <span key={ph} className="ehr-badge">
                            {ph}
                          </span>
                        ))}
                      </div>
                    ))}
              </td>
              <td>
                {s.isolates.map((i) => (
                  <div key={i.isolate_id} className="ehr-ast">
                    {i.resistant.map((c) => (
                      <span key={c} className="ehr-r" title={`${name(c)}: resistant`}>
                        {c} R
                      </span>
                    ))}
                    {i.susceptible.map((c) => (
                      <span key={c} className="ehr-s" title={`${name(c)}: susceptible`}>
                        {c} S
                      </span>
                    ))}
                  </div>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="ehr-hint">Lab results as the record system receives them. AEI uses the same results.</p>
    </section>
  );
}

function OrderList({ orders }: { orders: Order[] }) {
  if (orders.length === 0) return <p className="ehr-hint">No active orders.</p>;
  return (
    <ul className="ehr-orders">
      {orders.map((o) => (
        <li key={o.id}>
          <strong>{o.name}</strong> {o.dose && `· ${o.dose} `}· {o.route} · for {o.infection.toLowerCase()}{" "}
          <span className="ehr-hint">
            signed {o.signed}
            {o.override ? ` · AEI warning overridden: ${o.override}` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

function OrderForm({
  patient,
  defaultWard,
  onExchange,
  onSigned,
}: {
  patient: Patient;
  defaultWard: string;
  onExchange: (x: Exchange) => void;
  onSigned: (o: Order) => void;
}) {
  const { meta, asOf } = useApp();
  const [ward, setWard] = useState(defaultWard);
  const [infection, setInfection] = useState<Infection>("uti");
  const [antibiotic, setAntibiotic] = useState("");
  const [route, setRoute] = useState("oral");
  const [dose, setDose] = useState("");
  const [cards, setCards] = useState<CdsCard[] | null>(null);
  const [check, setCheck] = useState<CdsCard[] | null>(null);
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const specimen = meta.infections.find((i) => i.key === infection)?.specimen;
  const choices = meta.antibiotics.filter((a) => a.code !== "FOX" && (a.reported_for === "all" || a.reported_for === specimen));
  const abxName = meta.antibiotics.find((a) => a.code === antibiotic)?.name ?? "";
  const infectionLabel = meta.infections.find((i) => i.key === infection)?.label ?? infection;

  const body = (hook: string) => ({
    hook,
    hookInstance: crypto.randomUUID(),
    context: {
      patientId: patient.patient_id,
      userId: "Practitioner/demo",
      ward,
      infection,
      selections: ["MedicationRequest/draft-1"],
      draftOrders: {
        resourceType: "Bundle",
        entry: [
          {
            resource: {
              resourceType: "MedicationRequest",
              id: "draft-1",
              status: "draft",
              medicationCodeableConcept: { text: abxName, coding: [{ system: "urn:aei:antibiotic", code: antibiotic, display: abxName }] },
            },
          },
        ],
      },
    },
  });

  // order-select: every time the choice changes.
  useEffect(() => {
    setCheck(null);
    if (!antibiotic) {
      setCards(null);
      return;
    }
    setDone(null); // a new choice starts a new order; the last "signed" note stays until then
    const b = body("order-select");
    api.cds(SELECT, b, asOf).then((r) => {
      setCards(r.cards);
      onExchange({ hook: "order-select", request: b, response: r });
    });
  }, [antibiotic, ward, infection, patient.patient_id, asOf]); // eslint-disable-line react-hooks/exhaustive-deps

  const finish = (override?: string) => {
    const when = `${fmtDate(asOf)}`;
    onSigned({
      id: crypto.randomUUID(),
      code: antibiotic,
      name: abxName,
      infection: infectionLabel,
      route: route === "oral" ? "orally" : "i.v.",
      dose,
      signed: when,
      override,
    });
    setDone(override ? `Signed with an override: ${override}.` : `Signed. AEI had nothing to add.`);
    setCheck(null);
    setAntibiotic("");
    setDose("");
    setReason("");
  };

  // order-sign: AEI is asked again; only warnings come back, and none means "go ahead".
  const sign = () => {
    const b = body("order-sign");
    api.cds(SIGN, b, asOf).then((r) => {
      onExchange({ hook: "order-sign", request: b, response: r });
      if (r.cards.length === 0) finish();
      else setCheck(r.cards);
    });
  };

  const swap = (card: CdsCard, s: CdsSuggestion) => {
    const code = s.actions[0]?.resource.medicationCodeableConcept.coding[0]?.code;
    api.cdsFeedback(SIGN, [{ card: card.uuid, outcome: "accepted", acceptedSuggestions: [{ id: s.uuid }], outcomeTimestamp: new Date().toISOString() }]).catch(() => {});
    if (code) setAntibiotic(code);
  };

  const override = () => {
    const warn = check?.filter((c) => c.overrideReasons) ?? [];
    const r = warn[0]?.overrideReasons?.find((x) => x.code === reason);
    api
      .cdsFeedback(
        SIGN,
        warn.map((c) => ({ card: c.uuid, outcome: "overridden", overrideReason: { reason: r, userComment: "" }, outcomeTimestamp: new Date().toISOString() })),
      )
      .catch(() => {});
    finish(r?.display ?? "no reason given");
  };

  const standing = check?.filter((c) => c.indicator !== "info") ?? [];
  const alternatives = check?.find((c) => c.suggestions?.length);

  return (
    <div className="ehr-order">
      <h3>New antibiotic order</h3>
      <div className="ehr-form">
        <label>
          Ward
          <select value={ward} onChange={(e) => setWard(e.target.value)}>
            {meta.wards.map((w) => (
              <option key={w.ward_code} value={w.ward_code}>
                {w.ward_code} · {w.ward_en}
              </option>
            ))}
          </select>
        </label>
        <label>
          Indication
          <select value={infection} onChange={(e) => setInfection(e.target.value as Infection)}>
            {meta.infections.map((i) => (
              <option key={i.key} value={i.key}>
                {i.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Antibiotic
          <select value={antibiotic} onChange={(e) => setAntibiotic(e.target.value)}>
            <option value="">Choose…</option>
            {choices.map((a) => (
              <option key={a.code} value={a.code}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Route
          <select value={route} onChange={(e) => setRoute(e.target.value)}>
            <option value="oral">Oral</option>
            <option value="iv">Intravenous</option>
          </select>
        </label>
        <label>
          Dose and frequency
          <input value={dose} onChange={(e) => setDose(e.target.value)} placeholder="as per guideline" />
        </label>
      </div>

      {done && <p className="ehr-ok">{done}</p>}

      {antibiotic && (
        <div className="ehr-cds">
          <p className="ehr-hint">AEI checked this choice (CDS Hooks order-select):</p>
          {cards === null ? <p className="ehr-hint">Asking AEI…</p> : cards.map((c) => <Card key={c.uuid} card={c} onSwap={(s) => swap(c, s)} />)}
          <div className="ehr-actions">
            <button type="button" className="ehr-primary" onClick={sign}>
              Sign order
            </button>
            <button type="button" onClick={() => setAntibiotic("")}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <AnimatePresence>
        {check && (
          <motion.div className="ehr-modal-backdrop" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div
              className="ehr-modal"
              role="alertdialog"
              aria-label="Check before signing"
              initial={{ y: 12, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 12, opacity: 0 }}
            >
              <h3>Before you sign: {abxName}</h3>
              <p className="ehr-hint">AEI was asked again at signing (CDS Hooks order-sign).</p>
              {standing.map((c) => (
                <Card key={c.uuid} card={c} />
              ))}
              {alternatives && (
                <div className="ehr-swap">
                  <p>
                    <strong>Switch to an antibiotic without a local warning:</strong>
                  </p>
                  {alternatives.suggestions!.map((s) => (
                    <button key={s.uuid} type="button" className="ehr-primary" onClick={() => swap(alternatives, s)}>
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
              <div className="ehr-override">
                <label>
                  Or sign anyway, because:
                  <select value={reason} onChange={(e) => setReason(e.target.value)}>
                    <option value="">Choose a reason…</option>
                    {standing[0]?.overrideReasons?.map((r) => (
                      <option key={r.code} value={r.code}>
                        {r.display}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="button" disabled={!reason} onClick={override}>
                  Sign anyway
                </button>
                <button type="button" onClick={() => setCheck(null)}>
                  Back to the order
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MockInbox({ patientId }: { patientId?: string }) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setTick((v) => v + 1), INBOX_POLL_MS);
    return () => window.clearInterval(t);
  }, []);
  const { data } = useFetch((signal) => api.mockInbox(signal), [tick]);
  const messages = data?.messages ?? [];
  return (
    <div className="ehr-inbox">
      <h2 className="ehr-side-title">Messages from AEI ({messages.length})</h2>
      {messages.length === 0 && (
        <p className="ehr-hint">Nothing yet. AEI pushes new alerts and carrier flags here when new lab data arrives (webhook).</p>
      )}
      <ul>
        {messages.slice(0, 12).map((m, i) => {
          const p = m.payload;
          const pid = p.carrier?.patient_id;
          const text =
            p.event === "carrier.flagged"
              ? `${p.carrier.phenotype} carrier: ${pid}`
              : p.event === "alert.new"
                ? p.alert.title
                : p.event;
          return (
            <li key={i} className={pid && pid === patientId ? "is-this" : ""}>
              <span className="ehr-hint">{m.received.slice(11)}</span> {text}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** A CDS Hooks card as a record system would render it: indicator colour, summary, detail, links. */
function Card({ card, onSwap }: { card: CdsCard; onSwap?: (s: CdsSuggestion) => void }) {
  return (
    <div className={`cds-card cds-${card.indicator}`}>
      <p className="cds-summary">{card.summary}</p>
      {card.detail && (
        <details className="cds-detail">
          <summary>Details</summary>
          <Markdownish text={card.detail} />
        </details>
      )}
      {onSwap && card.suggestions && (
        <p className="cds-suggestions">
          {card.suggestions.map((s) => (
            <button key={s.uuid} type="button" onClick={() => onSwap(s)}>
              {s.label}
            </button>
          ))}
        </p>
      )}
      <p className="cds-source">
        {card.source.label}
        {card.links.map((l) => (
          <a key={l.url} href={l.url} target="_blank" rel="noreferrer">
            {l.label}
          </a>
        ))}
      </p>
    </div>
  );
}

/** Just enough markdown for card details: paragraphs and pipe tables. */
function Markdownish({ text }: { text: string }) {
  const blocks = text.split(/\n\n+/);
  return (
    <>
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines[0].startsWith("|")) {
          const rows = lines.filter((l) => !/^\|[-| ]+\|$/.test(l)).map((l) => l.split("|").slice(1, -1).map((c) => c.trim()));
          return (
            <table key={i} className="cds-table">
              <thead>
                <tr>
                  {rows[0].map((c, j) => (
                    <th key={j}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.slice(1).map((r, k) => (
                  <tr key={k}>
                    {r.map((c, j) => (
                      <td key={j}>{c}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }
        return <p key={i}>{b}</p>;
      })}
    </>
  );
}
