import { useEffect, useState } from "react";

import { Auth } from "./features/auth/index.jsx";
import { Bookings } from "./features/bookings/index.jsx";
import { Gate } from "./features/gate/index.jsx";
import { ParkingMap } from "./features/parking-map/index.jsx";
import { Profile } from "./features/profile/index.jsx";
import { History } from "./features/visits/index.jsx";
import { clearToken, getToken } from "./shared/api.js";

const TABS = [
  ["map", "Схема", false],
  ["gate", "Шлагбаум", false],
  ["bookings", "Мои брони", true],
  ["profile", "Профиль", true],
  ["history", "История", true],
];

export function App() {
  const [token, setToken] = useState(getToken);
  const [tab, setTab] = useState("map");

  useEffect(() => {
    function logout() {
      setToken("");
      setTab("login");
    }
    window.addEventListener("parking-logout", logout);
    return () => window.removeEventListener("parking-logout", logout);
  }, []);

  function leave() {
    clearToken();
    setToken("");
    setTab("map");
  }

  return (
    <div className="app">
      <header>
        <nav>
          {TABS.filter(([, , needsAuth]) => !needsAuth || token).map(([id, label]) => (
            <button key={id} type="button" className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
          {token ? (
            <button type="button" onClick={leave}>
              Выйти
            </button>
          ) : (
            <button type="button" className={tab === "login" ? "active" : ""} onClick={() => setTab("login")}>
              Вход
            </button>
          )}
        </nav>
      </header>
      <main>
        {tab === "map" ? <ParkingMap /> : null}
        {tab === "gate" ? <Gate /> : null}
        {tab === "login" && !token ? <Auth onSuccess={(value) => { setToken(value); setTab("profile"); }} /> : null}
        {tab === "bookings" && token ? <Bookings /> : null}
        {tab === "profile" && token ? <Profile /> : null}
        {tab === "history" && token ? <History /> : null}
      </main>
    </div>
  );
}
