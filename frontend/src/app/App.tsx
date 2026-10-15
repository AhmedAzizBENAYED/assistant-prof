import { t } from "../i18n";
import "./App.css";

export function App() {
  return (
    <main className="placeholder">
      <h1>{t.placeholder.title}</h1>
      <p>{t.placeholder.message}</p>
    </main>
  );
}
