import { useEffect, useRef, useState } from "react";

import { request } from "../../shared/api.js";
import { formatLocal, localInputToIso, toDateTimeLocal } from "../../shared/time.js";

const STATUS = {
  active: "активна",
  checked_in: "заехал",
  completed: "завершена",
  cancelled: "отменена",
  expired: "истекла",
};

function initialRange() {
  const start = new Date();
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  return { starts: toDateTimeLocal(start), ends: toDateTimeLocal(end) };
}

export function Bookings() {
  const [bookings, setBookings] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [spots, setSpots] = useState([]);
  const [page, setPage] = useState(1);
  const [hasNext, setHasNext] = useState(false);
  const [vehicle, setVehicle] = useState("");
  const [spot, setSpot] = useState("");
  const [range, setRange] = useState(initialRange);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const alive = useRef(true);
  const [cancelId, setCancelId] = useState(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  function applyPage(data, nextPage) {
    if (!alive.current) return;
    setBookings(data.results);
    setHasNext(Boolean(data.next));
    setPage(nextPage);
  }

  useEffect(() => {
    alive.current = true;
    let cancelled = false;
    Promise.all([
      request("/api/bookings/"),
      request("/api/vehicles/"),
      request("/api/spots/", { auth: false }),
    ])
      .then(([bookingPage, vehicleList, spotList]) => {
        if (cancelled) return;
        applyPage(bookingPage, 1);
        setVehicles(vehicleList);
        setSpots(spotList);
        setVehicle(vehicleList[0] ? String(vehicleList[0].id) : "");
        setSpot(spotList[0] ? String(spotList[0].id) : "");
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

  async function reload(nextPage = page) {
    const data = await request(`/api/bookings/?page=${nextPage}`);
    applyPage(data, nextPage);
  }

  async function createBooking(event) {
    event.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await request("/api/bookings/", {
        method: "POST",
        body: {
          vehicle: Number(vehicle),
          spot: Number(spot),
          starts_at: localInputToIso(range.starts),
          ends_at: localInputToIso(range.ends),
        },
      });
      await reload(1);
    } catch (err) {
      setError(err.message);
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }

  async function cancel(id) {
    if (lock.current) return;
    lock.current = true;
    setCancelId(id);
    setError("");
    try {
      await request(`/api/bookings/${id}/cancel/`, { method: "POST" });
      await reload();
    } catch (err) {
      setError(err.message);
    } finally {
      lock.current = false;
      if (alive.current) setCancelId(null);
    }
  }

  return (
    <section>
      <h1>Мои брони</h1>
      {error ? <p className="error">{error}</p> : null}
      {ready && vehicles.length === 0 ? <p>Сначала добавьте машину в профиле.</p> : null}
      <form onSubmit={createBooking}>
        <label>
          Машина
          <select value={vehicle} onChange={(event) => setVehicle(event.target.value)} required>
            {vehicles.map((item) => (
              <option key={item.id} value={item.id}>
                {item.plate}
              </option>
            ))}
          </select>
        </label>
        <label>
          Место
          <select value={spot} onChange={(event) => setSpot(event.target.value)} required>
            {spots.map((item) => (
              <option key={item.id} value={item.id}>
                {item.code}
              </option>
            ))}
          </select>
        </label>
        <label>
          Начало
          <input
            type="datetime-local"
            value={range.starts}
            onChange={(event) => setRange({ ...range, starts: event.target.value })}
            required
          />
        </label>
        <label>
          Конец
          <input
            type="datetime-local"
            value={range.ends}
            onChange={(event) => setRange({ ...range, ends: event.target.value })}
            required
          />
        </label>
        <button type="submit" disabled={busy || !ready || vehicles.length === 0}>
          Забронировать
        </button>
      </form>
      {ready && bookings.length === 0 ? <p>Броней пока нет.</p> : null}
      <ul className="list">
        {bookings.map((booking) => (
          <li key={booking.id}>
            <span>
              {booking.spot_code}, {STATUS[booking.status] || booking.status}, {formatLocal(booking.starts_at)} —{" "}
              {formatLocal(booking.ends_at)}
            </span>
            {booking.status === "active" ? (
              <button type="button" disabled={cancelId === booking.id} onClick={() => cancel(booking.id)}>
                Отмена
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {hasNext ? (
        <button type="button" disabled={busy} onClick={() => reload(page + 1).catch((err) => setError(err.message))}>
          Дальше
        </button>
      ) : null}
    </section>
  );
}
