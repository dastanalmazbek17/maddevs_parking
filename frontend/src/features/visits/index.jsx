import { useEffect, useRef, useState } from "react";

import { request } from "../../shared/api.js";
import { formatKopecks } from "../../shared/money.js";
import { formatLocal } from "../../shared/time.js";

export function History() {
  const [visits, setVisits] = useState([]);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const alive = useRef(true);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  function apply(data, nextPage) {
    if (!alive.current) return;
    setVisits(data.results);
    setHasNext(Boolean(data.next));
    setPage(nextPage);
  }

  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    request("/api/visits/")
      .then((data) => {
        if (cancelled) return;
        apply(data, 1);
        setReady(true);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message);
          setReady(true);
        }
      });
    return () => {
      cancelled = true;
      alive.current = false;
    };
  }, []);

  async function more() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const data = await request(`/api/visits/?page=${page + 1}`);
      apply(data, page + 1);
    } catch (err) {
      setError(err.message);
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }

  return (
    <section>
      <h1>История</h1>
      {error ? <p className="error">{error}</p> : null}
      {ready && visits.length === 0 && !error ? <p>Визитов пока нет.</p> : null}
      <ul className="list">
        {visits.map((visit) => (
          <li key={visit.id}>
            <span>
              {visit.plate}, место {visit.spot_code}, заезд {formatLocal(visit.entered_at)}
              {visit.exited_at ? `, выезд ${formatLocal(visit.exited_at)}` : ", на парковке"}
              {visit.invoice
                ? `, счёт ${formatKopecks(visit.invoice.total_kopecks)}`
                : ""}
            </span>
          </li>
        ))}
      </ul>
      {hasNext ? (
        <button type="button" disabled={busy} onClick={more}>
          Дальше
        </button>
      ) : null}
    </section>
  );
}
