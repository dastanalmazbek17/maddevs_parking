import { useRef, useState } from "react";

import { request } from "../../shared/api.js";
import { formatKopecks } from "../../shared/money.js";
import { formatLocal } from "../../shared/time.js";

export function Gate() {
  const [plate, setPlate] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(path) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const data = await request(path, { method: "POST", body: { plate }, auth: false });
      if (data.invoice) {
        setMessage(
          `Выезд ${formatLocal(data.visit.exited_at)}. Итого ${formatKopecks(data.invoice.total_kopecks)}.`,
        );
      } else {
        setMessage(`Место ${data.spot_code}. Заезд ${formatLocal(data.entered_at)}.`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>Шлагбаум</h1>
      <form
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <label>
          Номер
          <input value={plate} onChange={(event) => setPlate(event.target.value)} required />
        </label>
        <div className="row">
          <button type="button" disabled={busy} onClick={() => submit("/api/gate/enter/")}>
            Заезд
          </button>
          <button type="button" disabled={busy} onClick={() => submit("/api/gate/exit/")}>
            Выезд
          </button>
        </div>
      </form>
      {message ? <p>{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
