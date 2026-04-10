// frontend/api/api.js

export const runAgent = async () => {
  const res = await fetch("http://127.0.0.1:8000/run-agent", {
    method: "POST",
  });

  return res.json();
};