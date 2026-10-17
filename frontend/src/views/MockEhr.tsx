import { useEffect, useState } from "react";
import { api, type CdsCard, type Infection } from "../api/client";
import { fmtDate } from "../lib/format";
import { useFetch } from "../lib/hooks";
import { href } from "../lib/route";
import { useApp } from "../state/AppContext";

const INBOX_POLL_MS = 5000;

/**
 * V11 mock patient record (API-05): a stand-in for the hospital's own system. It knows nothing
 * about AEI's internals; it only calls the CDS Hooks services (patient-view when a record opens,
 * order-select when an antibiotic is chosen) and shows what AEI pushes to its webhook.
 */
export function MockEhr({ patientId }: { patientId?: string }) {
  const { asOf, meta } = useApp();
  const [search, setSearch] = useState(patientId ?? "");
  const examples = useFetch((signal) => api.carriers({ as_of: asOf, days: 60, limit: 5 }, signal), [asOf, meta.data_version]);
  const patient = useFetch(
    (signal) => (patientId ? api.patient(patientId, asOf, signal) : Promise.resolve(null)),
    [patientId, asOf, meta.data_version],
  );
  const [exchange, setExchange] = useState<{ request: unknown; response: unknown } | null>(null);
  const [viewCards, setViewCards] = useState<CdsCard[] | null>(null);

  useEffect(() => {
    setViewCards(null);
    if (!patientId) return;
    const body = { hook: "patient-view", hookInstance: crypto.randomUUID(), context: { patientId, userId: "Practitioner/demo" } };
    api
      .cds("aei-patient-context", body, asOf)
      .then((r) => {
        setViewCards(r.cards);
        setExchange({ request: body, response: r });
      })
      .catch(() => setViewCards([]));
  }, [patientId, asOf]);

  return (
    <div className="ehr">
      <header className="ehr-top">
        <strong>Potilaskertomus</strong> <span>· Patient record</span>
        <span className="ehr-demo">Mock hospital system (demo) · date {fmtDate(asOf)}</span>
        <a href={href({ view: "start" })}>← Back to AEI</a>
      </header>
      <div className="ehr-body">
        <aside className="ehr-side">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (search.trim()) window.location.hash = href({ view: "ehr", id: search.trim().toUpperCase() });
            }}
          >
            <label>
              Patient ID
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="P001234" />
            </label>
            <button type="submit">Open record</button>
          </form>
          <p className="ehr-hint">Recently flagged carriers (examples):</p>
          <ul>
            {(examples.data?.carriers ?? []).map((c) => (
              <li key={`${c.patient_id}-${c.phenotype}`}>
                <a href={href({ view: "ehr", id: c.patient_id })}>{c.patient_id}</a> <span className="ehr-hint">{c.first_ward}</span>
              </li>
            ))}
          </ul>
          <MockInbox patientId={patientId} />
        </aside>

        <main className="ehr-main">
          {!patientId && <p>Open a patient record to see what AEI tells the doctor.</p>}
          {patient.error && <p className="error">No such patient up to {fmtDate(asOf)}.</p>}
          {patient.data && (
            <>
              <section className="ehr-patient">
                <h1>{patient.data.patient_id}</h1>
                <p>
                  {patient.data.sex === "F" ? "Female" : "Male"}, {patient.data.age} y · {patient.data.home_area} · last
                  seen {patient.data.last_ward} {fmtDate(patient.data.last_sample)}
                </p>
              </section>

              <section className="ehr-panel">
                <h2>Notices from AEI</h2>
                <p className="ehr-hint">CDS Hooks patient-view: called when this record opened.</p>
                {viewCards === null ? (
                  <p className="ehr-hint">Asking AEI…</p>
                ) : viewCards.length === 0 ? (
                  <p className="ehr-hint">No notices: no known carriage, no alerts involving this patient.</p>
                ) : (
                  viewCards.map((c) => <Card key={c.uuid} card={c} />)
                )}
              </section>

              <OrderForm
                key={patient.data.patient_id}
                patientId={patient.data.patient_id}
                defaultWard={patient.data.last_ward}
                onExchange={setExchange}
              />

              {exchange && (
                <details className="ehr-panel">
                  <summary>Last API exchange (CDS Hooks JSON)</summary>
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

function OrderForm({
  patientId,
  defaultWard,
  onExchange,
}: {
  patientId: string;
  defaultWard: string;
  onExchange: (x: { request: unknown; response: unknown }) => void;
}) {
  const { meta, asOf } = useApp();
  const [ward, setWard] = useState(defaultWard);
  const [infection, setInfection] = useState<Infection>("uti");
  const [antibiotic, setAntibiotic] = useState("");
  const [cards, setCards] = useState<CdsCard[] | null>(null);
  const specimen = meta.infections.find((i) => i.key === infection)?.specimen;
  const choices = meta.antibiotics.filter((a) => a.code !== "FOX" && (a.reported_for === "all" || a.reported_for === specimen));

  useEffect(() => {
    if (!antibiotic) {
      setCards(null);
      return;
    }
    // A FHIR-style draft order, as a prescribing system would send it.
    const body = {
      hook: "order-select",
      hookInstance: crypto.randomUUID(),
      context: {
        patientId,
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
                medicationCodeableConcept: { text: meta.antibiotics.find((a) => a.code === antibiotic)?.name },
              },
            },
          ],
        },
      },
    };
    api.cds("aei-antibiotic-choice", body, asOf).then((r) => {
      setCards(r.cards);
      onExchange({ request: body, response: r });
    });
  }, [antibiotic, ward, infection, patientId, asOf]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <section className="ehr-panel">
      <h2>Order an antibiotic</h2>
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
      </div>
      <p className="ehr-hint">CDS Hooks order-select: called when an antibiotic is chosen.</p>
      {cards?.map((c) => <Card key={c.uuid} card={c} />)}
    </section>
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
      <p className="ehr-hint">
        <strong>Pushed by AEI</strong> (webhook inbox, {messages.length})
      </p>
      {messages.length === 0 && (
        <p className="ehr-hint">Nothing yet. Pushes arrive when new lab data comes in (AEI → Feed status).</p>
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

/** A CDS Hooks card as an EHR would render it: indicator colour, summary, detail, links. */
function Card({ card }: { card: CdsCard }) {
  return (
    <div className={`cds-card cds-${card.indicator}`}>
      <p className="cds-summary">{card.summary}</p>
      {card.detail && <Markdownish text={card.detail} />}
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
