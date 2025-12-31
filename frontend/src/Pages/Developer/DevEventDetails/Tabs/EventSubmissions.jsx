// EventSubmissions.jsx
import { useMemo, useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import api from "@/utils/api";
import { useNavigate } from "react-router-dom";

export default function EventSubmissions({
  rounds = [],
  loading = false,
  activeRoundId,
  setActiveRoundId,
  eventId,
}) {
  const [file, setFile] = useState(null);
  const [repo, setRepo] = useState("");
  const [video, setVideo] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [subs, setSubs] = useState(null);
  const [subsLoading, setSubsLoading] = useState(false);
  const [subsError, setSubsError] = useState(null);
  const [pdfFile, setPdfFile] = useState(null);
  const navigate = useNavigate();

  const fetchSubs = useCallback(async () => {
    if (!eventId) return;
    try {
      setSubsLoading(true);
      setSubsError(null);
      const res = await api.get(`/team/events/${eventId}/my-submissions`);
      setSubs(res.data?.data || {});
    } catch (e) {
      console.error("Failed to fetch submissions", e);
      setSubsError("Failed to sync your submissions");
    } finally {
      setSubsLoading(false);
    }
  }, [eventId]);

  useEffect(() => {
    fetchSubs();
  }, [fetchSubs]);

  const active = useMemo(
    () =>
      rounds.find((r) => (r.id || r._id) === activeRoundId) ||
      rounds[0] ||
      null,
    [rounds, activeRoundId]
  );
  const handleVivaSubmit = async () => {
  if (!pdfFile) {
    alert("Upload project report (PDF)");
    return;
  }

  setSubmitting(true);
  try {
    const fd = new FormData();
    fd.append("file", pdfFile);

    const res = await api.post(`/interview/interview-data`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    console.log(res.data);

    const { sessionId, question, questionIndex, totalQuestions } = res.data;
    console.log(sessionId)
    // Option 1: new route
    navigate(`/interview/${sessionId}`, {
  state: {
    eventId,
    teamId: subs?.teamId || null,
    teamName: subs?.teamName || null,

    firstQuestion: question,
    questionIndex,
    totalQuestions,
  },
});


   
  } catch (e) {
    alert(e?.response?.data?.detail || "Failed to start interview");
  } finally {
    setSubmitting(false);
  }
};



  const getActiveSubmission = () => {
    if (!active) return null;
    const roundId = active.id || active._id || "";
    return subs?.[roundId] || null;
  };

  if (loading)
    return (
      <div className="text-sm text-neutral-400 animate-pulse">
        Loading submissions…
      </div>
    );

  const handleSubmit = async () => {
    if (!active) return;
    const roundId = active.id || active._id;

    const existing = subs?.[roundId];
    if (existing) {
      alert("You have already submitted for this round.");
      return;
    }

    setSubmitting(true);
    try {
      if (roundId === "ppt") {
        if (!file) return alert("Upload file");

        const fd = new FormData();
        fd.append("file", file);

        await api.post(`/team/events/${eventId}/submit/ppt`, fd, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        alert("PPT submitted!");
      } else if (roundId === "repo") {
        if (!repo.trim()) return alert("Enter GitHub repo link");
        if (!video.trim()) return alert("Enter video URL");

        const body = new URLSearchParams();
        body.append("repo", repo.trim());
        body.append("video", video.trim());

        await api.post(`/team/events/${eventId}/submit/repo`, body);
        alert("Repository & video submitted!");
      } else if (roundId === "viva") {
        await api.post(`/team/events/${eventId}/submit/viva`);
        alert("Viva started!");
      }

      await fetchSubs();
    } catch (err) {
      alert(err?.response?.data?.detail || "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  const renderPPT = (sub, submittedAt, ai) => {
    const score = ai?.score?.overall_score;
    const deck = ai?.deck_summary || {};

    return (
      <div className="space-y-6">

        {/* Status */}
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-sm">
            ✓ Submitted
          </span>
          {submittedAt && (
            <span className="text-[11px] text-neutral-500">
              Submitted on {submittedAt.toLocaleString()}
            </span>
          )}
        </div>

        {/* Score Card */}
        <div className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-neutral-700">
              PPT evaluated
            </p>
            <p className="text-xs text-neutral-500">
              You cannot re-submit for this round.
            </p>
          </div>

          {score != null && (
            <div className="flex flex-col items-end">
              <span className="text-xs font-medium text-emerald-700">
                Score
              </span>
              <span className="text-3xl font-bold text-emerald-600">
                {score.toFixed(2)}
              </span>
              <span className="text-[10px] text-neutral-500">/100</span>
            </div>
          )}
        </div>

        {/* View File */}
        {sub.fileUrl && (
          <a
            href={sub.fileUrl}
            target="_blank"
            className="inline-flex px-4 py-2 text-sm font-medium rounded-xl bg-white border border-neutral-300 shadow-sm hover:bg-neutral-50 transition"
          >
            View uploaded file
          </a>
        )}

        {/* Strengths / Weakness / Fixes */}
        {(deck.strengths?.length ||
          deck.weaknesses?.length ||
          deck.recommended_fixes?.length) && (
          <div className="grid md:grid-cols-3 gap-4">
            {deck.strengths?.length > 0 && (
              <div className="rounded-xl bg-white border border-neutral-200 p-5 shadow-sm">
                <p className="text-base font-semibold text-neutral-900 mb-2">
                  Strengths
                </p>
                <ul className="list-disc pl-5 space-y-1 text-sm text-neutral-700">
                  {deck.strengths.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}

            {deck.weaknesses?.length > 0 && (
              <div className="rounded-xl bg-white border border-neutral-200 p-5 shadow-sm">
                <p className="text-base font-semibold text-neutral-900 mb-2">
                  Weaknesses
                </p>
                <ul className="list-disc pl-5 space-y-1 text-sm text-neutral-700">
                  {deck.weaknesses.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {deck.recommended_fixes?.length > 0 && (
              <div className="rounded-xl bg-white border border-neutral-200 p-5 shadow-sm">
                <p className="text-base font-semibold text-neutral-900 mb-2">
                  Recommended Fixes
                </p>
                <ul className="list-disc pl-5 space-y-1 text-sm text-neutral-700">
                  {deck.recommended_fixes.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Detailed Feedback */}
        {ai?.mentor_summary && (
          <div className="rounded-xl bg-white border border-neutral-200 p-5 shadow-sm">
            <p className="font-semibold text-base mb-3 text-neutral-900">
              Detailed Feedback
            </p>

            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              className="prose prose-custom max-w-none"
            >
              {ai.mentor_summary}
            </ReactMarkdown>
          </div>
        )}
      </div>
    );
  };


  const renderRepo = (sub, submittedAt) => {
    const ev = sub.evaluation || {};
    const finalScore =
      ev?.final_score != null ? Number(ev.final_score) : null;

    return (
      <div className="space-y-6">

        {/* Status */}
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-sm">
            ✓ Submitted
          </span>

          {submittedAt && (
            <span className="text-[11px] text-neutral-500">
              Submitted on {submittedAt.toLocaleString()}
            </span>
          )}
        </div>

        {/* Score Card */}
        <div className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-neutral-700">
              Repo & Video submitted
            </p>
            <p className="text-xs text-neutral-500">
              You cannot re-submit for this round.
            </p>
          </div>

          {finalScore != null && (
            <div className="flex flex-col items-end">
              <span className="text-xs font-medium text-emerald-700">
                Final Score
              </span>
              <span className="text-3xl font-bold text-emerald-600">
                {finalScore.toFixed(2)}
              </span>
              <span className="text-[10px] text-neutral-500">/100</span>
            </div>
          )}
        </div>

        {/* Repo + Video Links */}
        <div className="space-y-2 text-sm">
          <p>
            <strong className="text-neutral-800">Repo:</strong>{" "}
            <a
              className="text-blue-600 underline break-all"
              href={sub.repo}
              target="_blank"
            >
              {sub.repo}
            </a>
          </p>

          <p>
            <strong className="text-neutral-800">Video:</strong>{" "}
            <a
              className="text-blue-600 underline break-all"
              href={sub.video}
              target="_blank"
            >
              {sub.video}
            </a>
          </p>
        </div>

        {/* Rubric */}
        {ev.rubric && (
          <div className="rounded-xl bg-white border border-neutral-200 p-5 shadow-sm">
            <p className="text-base font-semibold text-neutral-900 mb-2">
              Grade: {ev.rubric.grade}
            </p>
            <p className="text-sm text-neutral-700">
              {ev.rubric.summary}
            </p>
          </div>
        )}

        {/* Mentor Summary (Markdown) */}
        {sub.mentor_summary_markdown && (
          <div className="rounded-xl bg-white border border-neutral-200 p-5 shadow-sm">
            <p className="font-semibold text-base mb-3 text-neutral-900">
              Detailed Reviewer Feedback
            </p>

            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              className="prose prose-custom max-w-none"
            >
              {sub.mentor_summary_markdown}
            </ReactMarkdown>
          </div>
        )}

        {/* Rewrite Suggestions */}
        {sub.rewrite_suggestions_markdown && (
          <div className="rounded-xl bg-white border border-neutral-200 p-5 shadow-sm">
            <p className="font-semibold text-base mb-3 text-neutral-900">
              Rewrite Suggestions
            </p>

            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              className="prose prose-custom max-w-none"
            >
              {sub.rewrite_suggestions_markdown}
            </ReactMarkdown>
          </div>
        )}
      </div>
    );
  };

 
  const renderSubmittedState = (roundId, submission) => {
    const submittedAt = submission?.submittedAt
      ? new Date(submission.submittedAt)
      : null;

    const ai = submission?.aiResult || null;

    if (roundId === "ppt") return renderPPT(submission, submittedAt, ai);
    if (roundId === "repo") return renderRepo(submission, submittedAt);

    if (roundId === "viva")
      return (
        <div className="space-y-4">
          <span className="inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-sm">
            ✓ Viva started
          </span>
          <p className="text-sm text-neutral-700">
            Interview session initiated. Judges will proceed.
          </p>
        </div>
      );

    return (
      <div className="text-sm text-neutral-500">Unknown round type</div>
    );
  };


  const renderUI = () => {
    if (!active)
      return <p className="text-sm text-neutral-500">No rounds defined</p>;

    const roundId = active.id || active._id || "";
    const submission = getActiveSubmission();

    if (submission) return renderSubmittedState(roundId, submission);

    // PPT Upload
    if (roundId === "ppt") {
      return (
        <div className="space-y-6">
          <div>
            <label className="text-sm font-medium text-neutral-800">
              Upload PPT / PDF
            </label>
            <input
              type="file"
              accept=".pdf,.ppt,.pptx"
              onChange={(e) => setFile(e.target.files[0])}
              className="p-3 bg-neutral-50 border border-neutral-200 rounded-xl text-sm w-full"
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-5 py-3 bg-neutral-900 text-white rounded-xl text-sm font-medium hover:bg-black hover:scale-[1.03] transition shadow disabled:opacity-60"
          >
            {submitting ? "Submitting…" : "Submit File"}
          </button>
        </div>
      );
    }

    // Repo Submit
    if (roundId === "repo") {
      return (
        <div className="space-y-6">
          <div>
            <label className="text-sm font-medium text-neutral-800">
              GitHub Repository Link
            </label>
            <input
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="https://github.com/username/repo"
              className="mt-1 p-3 bg-neutral-50 border border-neutral-200 rounded-xl text-sm w-full"
            />
          </div>

          <div>
            <label className="text-sm font-medium text-neutral-800">
              Demo Video URL
            </label>
            <input
              value={video}
              onChange={(e) => setVideo(e.target.value)}
              placeholder="YouTube/Drive link"
              className="mt-1 p-3 bg-neutral-50 border border-neutral-200 rounded-xl text-sm w-full"
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-5 py-3 bg-neutral-900 text-white rounded-xl text-sm font-medium hover:bg-black hover:scale-[1.03] transition shadow disabled:opacity-60"
          >
            {submitting ? "Submitting…" : "Submit Repo + Video"}
          </button>
        </div>
      );
    }

    // Viva Start
    if (roundId === "viva") {
  return (
    <div className="flex flex-col items-start gap-4">

      <label className="text-sm font-medium text-neutral-800">
        Upload Project Report (PDF)
      </label>

      <input
        type="file"
        accept="application/pdf"
        onChange={(e) => setPdfFile(e.target.files[0])}
        className="block w-full text-sm text-neutral-700 
                   file:mr-4 file:py-2 file:px-4 
                   file:rounded-lg file:border-0 
                   file:text-sm file:font-medium
                   file:bg-neutral-900 file:text-white
                   hover:file:bg-black cursor-pointer"
      />

      <p className="text-sm text-neutral-700">
        This round requires a live interview session.
      </p>

      <button
        onClick={handleVivaSubmit}
        disabled={submitting}
        className="px-5 py-3 bg-neutral-900 text-white rounded-xl 
                   text-sm font-medium hover:bg-black hover:scale-[1.03] 
                   transition shadow disabled:opacity-60"
      >
        {submitting ? "Starting…" : "Start Interview"}
      </button>
    </div>
  );
}


    return (
      <p className="text-sm text-neutral-500">Unknown round type</p>
    );
  };

  // ------------------------------
  // MAIN RETURN UI
  // ------------------------------
  return (
    <div className="space-y-6">

      {/* Round Selector */}
      <div className="flex gap-3 overflow-x-auto pb-2">
        {rounds.map((r) => {
          const key = r.id || r._id;
          return (
            <button
              key={key}
              onClick={() => setActiveRoundId(key)}
              className={`px-4 py-2 rounded-xl text-xs font-medium transition-all ${
                key === activeRoundId
                  ? "bg-neutral-900 text-white shadow"
                  : "bg-white border border-neutral-300 hover:border-neutral-500"
              }`}
            >
              {String(r.id || r.name || key).toUpperCase()}
            </button>
          );
        })}
      </div>

      {/* Main Card */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="bg-white rounded-2xl border border-neutral-200 p-6 shadow-sm space-y-6"
      >
        <div className="flex items-center justify-between">
          <h4 className="font-bold text-base text-neutral-900">
            {String(active?.id || active?.name || "ROUND").toUpperCase()} Submission
          </h4>

          {subsLoading && (
            <span className="text-[11px] text-neutral-400 animate-pulse">
              Syncing…
            </span>
          )}
          {subsError && !subsLoading && (
            <span className="text-[11px] text-red-500">{subsError}</span>
          )}
        </div>

        {renderUI()}
      </motion.div>
    </div>
  );
}
