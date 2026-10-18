import { useEffect, useRef, useState } from "react";

import { request } from "../../shared/api.js";

export function Profile() {
  const [email, setEmail] = useState("");
  const [vehicles, setVehicles] = useState([]);
  const [plate, setPlate] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const alive = useRef(true);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  function load() {
    return request("/api/me/").then((data) => {
      if (!alive.current) return;
      setEmail(data.email);
      setVehicles(data.vehicles);
    });
  }

  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    request("/api/me/")
      .then((data) => {
        if (cancelled) return;
        setEmail(data.email);
        setVehicles(data.vehicles);
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

  async function addVehicle(event) {
    event.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await request("/api/vehicles/", { method: "POST", body: { plate } });
      setPlate("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }

  return (
    <section>
      <h1>Профиль</h1>
      {email ? <p>Почта: {email}</p> : null}
      {error ? <p className="error">{error}</p> : null}
      {ready && vehicles.length === 0 ? <p>Машин пока нет.</p> : null}
      <ul>
        {vehicles.map((vehicle) => (
          <li key={vehicle.id}>{vehicle.plate}</li>
        ))}
      </ul>
      <form onSubmit={addVehicle}>
        <label>
          Номер
          <input value={plate} onChange={(event) => setPlate(event.target.value)} required />
        </label>
        <button type="submit" disabled={busy}>
          Добавить машину
        </button>
      </form>
    </section>
  );
}
