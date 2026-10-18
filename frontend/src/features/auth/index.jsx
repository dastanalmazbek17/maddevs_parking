import { useRef, useState } from "react";

import { request, setToken } from "../../shared/api.js";

export function Auth({ onSuccess }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState("");
  const register = mode === "register";

  async function submit(event) {
    event.preventDefault();
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const path = register ? "/api/auth/register/" : "/api/auth/login/";
      const data = await request(path, {
        method: "POST",
        body: { email, password },
        auth: false,
      });
      setToken(data.token);
      onSuccess(data.token);
    } catch (err) {
      setError(err.message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  return (
    <section>
      <h1>{register ? "Регистрация" : "Вход"}</h1>
      <form onSubmit={submit}>
        <label>
          Почта
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label>
          Пароль
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={busy}>
          {register ? "Зарегистрироваться" : "Войти"}
        </button>
      </form>
      <button
        type="button"
        className="link"
        onClick={() => {
          setMode(register ? "login" : "register");
          setError("");
        }}
      >
        {register ? "Уже есть аккаунт? Войти" : "Нет аккаунта? Регистрация"}
      </button>
      {error ? <p className="error">{error}</p> : null}
    </section>
  );
}
