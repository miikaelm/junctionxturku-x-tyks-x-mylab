import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { api, type Health } from "./api/client";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main>
      <motion.h1 initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}>
        AEI – Antibiotic Efficacy Indicator
      </motion.h1>
      {error && <p className="error">Backend unreachable: {error}</p>}
      {health && (
        <p>
          {health.cultures.toLocaleString()} cultures · {health.data_start} → {health.data_end}
        </p>
      )}
    </main>
  );
}
