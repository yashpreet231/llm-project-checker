"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import RoadmapProgress from "@/components/RoadmapProgress";
import { ScoreRing, Spinner } from "@/components/ProgressAnimation";
import * as api from "@/lib/api";

const StudentDashboard = () => {
  const router = useRouter();
  const [state, setState] = useState(null);
  const [roadmap, setRoadmap] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const sid = sessionStorage.getItem("sessionId");

    if (!sid) {
      router.push("/");
      return;
    }

    Promise.all([
      api.getSession(sid),
      api.getRoadmap(sid).catch(() => null),
    ])
      .then(([s, r]) => {
        setState(s);
        setRoadmap(r);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner size={40} />
      </div>
    );
  }

  const curWeek = state?.current_week || 1;
  const totalWeeks = roadmap?.total_weeks || 0;
  const quizResults = state?.quiz_results || [];
  const weeklyScore = state?.weekly_score_display;

  const statCards = [
    {
      label: "Current week",
      value: totalWeeks ? `${curWeek} / ${totalWeeks}` : "—",
      color: "var(--accent)",
    },
    {
      label: "Prereqs passed",
      value: `${quizResults.filter((r) => r.passed).length} / ${
        quizResults.length
      }`,
      color: "var(--accent3)",
    },
    {
      label: "Latest score",
      value: weeklyScore != null ? `${weeklyScore}/10` : "—",
      color:
        weeklyScore >= 7
          ? "var(--accent3)"
          : weeklyScore >= 5
          ? "var(--accent2)"
          : "var(--danger)",
    },
    {
      label: "Project",
      value: state?.project?.name || "—",
      color: "var(--muted)",
    },
  ];

  return (
    <div className="flex min-h-screen">
      <Sidebar role="student" />

      <main className="flex-1 p-10 overflow-y-auto">
        {/* Header */}
        <div className="mb-10">
          <div className="text-xs uppercase tracking-widest text-accent mb-3">
            Student dashboard
          </div>

          <h1 className="text-4xl font-extrabold leading-tight">
            Welcome back.
          </h1>
        </div>

        {/* Stat Cards */}
        <div className="grid gap-3 mb-10 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
          {statCards.map((s) => (
            <div
              key={s.label}
              className="rounded-lg border p-5"
              style={{
                background: "var(--surface)",
                borderColor: "var(--border)",
              }}
            >
              <div className="text-xs uppercase tracking-wide text-muted mb-2">
                {s.label}
              </div>

              <div
                className="text-2xl font-bold"
                style={{ color: s.color }}
              >
                {s.value}
              </div>
            </div>
          ))}
        </div>

        {/* Score Ring */}
        {weeklyScore != null && (
          <div
            className="flex items-center gap-6 p-6 mb-8 rounded-xl border"
            style={{
              background: "var(--surface)",
              borderColor: "var(--border)",
            }}
          >
            <ScoreRing
              score={state.weekly_score}
              display={weeklyScore}
              size={100}
            />

            <div>
              <div className="text-xs uppercase tracking-wide text-muted mb-2">
                Last week evaluation
              </div>

              <div className="text-sm leading-relaxed">
                {state?.evaluation_feedback?.message || "—"}
              </div>

              <div className="text-xs text-muted mt-2">
                Next tip:{" "}
                {state?.evaluation_feedback?.next_week_tip || "—"}
              </div>
            </div>
          </div>
        )}

        {/* Roadmap */}
        {roadmap && (
          <>
            <div className="text-xl font-bold mb-5">Roadmap</div>
            <RoadmapProgress
              roadmap={roadmap}
              currentWeek={curWeek}
            />
          </>
        )}

        {/* Quiz History */}
        {quizResults.length > 0 && (
          <div
            className="p-6 mt-8 rounded-xl border"
            style={{
              background: "var(--surface)",
              borderColor: "var(--border)",
            }}
          >
            <div className="text-lg font-bold mb-4">
              Prerequisite history
            </div>

            {quizResults.map((r, i) => (
              <div
                key={i}
                className="flex justify-between items-center py-3"
                style={{
                  borderBottom:
                    i < quizResults.length - 1
                      ? "1px solid var(--border)"
                      : "none",
                }}
              >
                <span className="text-sm">{r.concept}</span>

                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted">
                    {r.score}/5
                  </span>

                  <span
                    className="text-[10px] uppercase px-3 py-1 rounded-full"
                    style={{
                      background: r.passed
                        ? "rgba(61,217,164,0.15)"
                        : "rgba(240,93,93,0.15)",
                      color: r.passed
                        ? "var(--accent3)"
                        : "var(--danger)",
                    }}
                  >
                    {r.passed ? "Passed" : "Retried"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
};

export default StudentDashboard;