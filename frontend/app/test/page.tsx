'use client';

import { useEffect, useState } from "react";
import { runAgent } from "../../lib/api";

export default function Page() {
  const [data, setData] = useState(null);

  useEffect(() => {
    runAgent().then(setData);
  }, []);

  return (
    <div>
      <h1>AI Output</h1>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
}