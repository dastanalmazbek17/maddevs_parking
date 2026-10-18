import { useSpots } from "./useSpots.js";

const LABEL = {
  free: "свободно",
  booked: "забронировано",
  occupied: "занято",
};

export function ParkingMap() {
  const { spots, link, error, loaded } = useSpots();

  return (
    <section>
      <h1>Схема</h1>
      <p className="status">{link === "online" ? "Связь: онлайн" : "Связь: переподключение"}</p>
      {error ? <p className="error">{error}</p> : null}
      <ul className="legend">
        {Object.entries(LABEL).map(([status, text]) => (
          <li key={status} className={status}>
            {text}
          </li>
        ))}
      </ul>
      {!loaded ? <p>Загрузка…</p> : null}
      {loaded && spots.length === 0 && !error ? <p>Мест нет.</p> : null}
      <div className="grid">
        {spots.map((spot) => (
          <article key={spot.id} className={`spot ${spot.status}`}>
            <strong>{spot.code}</strong>
            <span>{LABEL[spot.status] || spot.status}</span>
          </article>
        ))}
      </div>
    </section>
  );
}
