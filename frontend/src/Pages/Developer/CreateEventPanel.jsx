import { useState } from "react";
import { motion } from "framer-motion";
import api from "@/utils/api";
import { FileText, FolderGit2, Mic, UploadCloud } from "lucide-react";

export default function CreateEventPanel({ onCreate }) {
  const [form, setForm] = useState({
    name: "",
    summary: "",
    description: "",
    date: "",
    registrationDeadline: "",
    prize: "",
    maxTeams: "",
    minMembers: "",
    maxMembers: "",
    bannerFile: null,
    logoFile: null,
    rounds: [],
  });

  const [aiPrompt, setAiPrompt] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  const [errors, setErrors] = useState({});
  const [submitStatus, setSubmitStatus] = useState("idle");
  const [submitMessage, setSubmitMessage] = useState("");

  const update = (field, value) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const toggleRound = (roundId) => {
    setForm((prev) => {
      const exists = prev.rounds.some((r) => r.id === roundId);
      return exists
        ? { ...prev, rounds: prev.rounds.filter((r) => r.id !== roundId) }
        : { ...prev, rounds: [...prev.rounds, { id: roundId, description: "" }] };
    });
  };

  const updateRoundDescription = (roundId, value) =>
    setForm((prev) => ({
      ...prev,
      rounds: prev.rounds.map((r) =>
        r.id === roundId ? { ...r, description: value } : r
      ),
    }));


  const handleAiGenerate = async () => {
    if (!aiPrompt.trim()) return;

    try {
      setAiLoading(true);

      const res = await api.post("/ai-models/create-event-ai", {
        event_details: aiPrompt,
      });

      const ai = res.data.event;

      setForm((prev) => ({
        ...prev,
        name: ai.name || prev.name,
        summary: ai.summary || prev.summary,
        description: ai.description || prev.description,
        date: ai.date || prev.date,
        registrationDeadline: ai.registrationDeadline || prev.registrationDeadline,
        prize: ai.prize || prev.prize,
        maxTeams: ai.maxTeams?.toString() || prev.maxTeams,
        minMembers: ai.minMembers?.toString() || prev.minMembers,
        maxMembers: ai.maxMembers?.toString() || prev.maxMembers,
      }));

      setSubmitStatus("success");
      setSubmitMessage("AI data applied!");
      setTimeout(() => {
        setSubmitStatus("idle");
        setSubmitMessage("");
      }, 1200);

    } catch (err) {
      setSubmitStatus("error");
      setSubmitMessage("AI failed to generate event.");
    } finally {
      setAiLoading(false);
    }
  };


  const validate = () => {
    const err = {};

    if (!form.name.trim()) err.name = "Event name is required.";
    if (!form.date) err.date = "Event date is required.";
    if (!form.registrationDeadline) err.registrationDeadline = "Registration deadline required.";

    if (
      form.registrationDeadline &&
      form.date &&
      new Date(form.registrationDeadline) > new Date(form.date)
    )
      err.registrationDeadline = "Deadline must be before event date.";

    if (!form.prize || isNaN(Number(form.prize)))
      err.prize = "Prize must be numeric.";

    if (!form.maxTeams || Number(form.maxTeams) <= 0)
      err.maxTeams = "Max teams must be positive.";

    if (!form.minMembers || Number(form.minMembers) <= 0)
      err.minMembers = "Min members must be positive.";

    if (!form.maxMembers || Number(form.maxMembers) <= 0)
      err.maxMembers = "Max members must be positive.";

    if (Number(form.minMembers) > Number(form.maxMembers))
      err.minMembers = "Min cannot exceed max.";

    if (form.rounds.length === 0)
      err.rounds = "Select at least one round.";

    setErrors(err);
    return Object.keys(err).length === 0;
  };


  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validate()) {
      setSubmitStatus("error");
      setSubmitMessage("Fix the highlighted errors.");
      return;
    }

    try {
      setSubmitStatus("loading");
      setSubmitMessage("");

      const fd = new FormData();

      fd.append("name", form.name);
      fd.append("summary", form.summary);
      fd.append("description", form.description);
      fd.append("date", form.date);
      fd.append("registrationDeadline", form.registrationDeadline);

      fd.append("prize", form.prize);
      fd.append("maxTeams", form.maxTeams);
      fd.append("minMembers", form.minMembers);
      fd.append("maxMembers", form.maxMembers);

      fd.append("rounds", JSON.stringify(form.rounds));

      if (form.bannerFile) fd.append("bannerFile", form.bannerFile);
      if (form.logoFile) fd.append("logoFile", form.logoFile);

      const res = await api.post("/org/create", fd);

      setSubmitStatus("success");
      setSubmitMessage("Event created!");

      onCreate(res.data.data);

      setTimeout(() => {
        setSubmitStatus("idle");
        setSubmitMessage("");
      }, 1400);
    } catch {
      setSubmitStatus("error");
      setSubmitMessage("Failed to create event.");
    }
  };


  const ROUND_TYPES = [
    { id: "ppt", label: "PPT Submission", icon: <FileText size={20} /> },
    { id: "repo", label: "Repository + Video", icon: <FolderGit2 size={20} /> },
    { id: "viva", label: "Virtual Viva", icon: <Mic size={20} /> },
  ];


  const FileInput = ({ label, file, onChange }) => (
    <div>
      {!file ? (
        <label className="block border border-neutral-300 rounded-xl px-4 py-3 text-sm cursor-pointer hover:bg-neutral-100 transition">
          <div className="flex items-center gap-3 text-neutral-700">
            <UploadCloud size={18} />
            <span>{label}</span>
          </div>
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => onChange(e.target.files?.[0] || null)}
          />
        </label>
      ) : (
        <div className="flex items-center gap-3 p-2 bg-neutral-50 border border-neutral-300 rounded-xl shadow-sm mt-2">
          <img
            src={URL.createObjectURL(file)}
            className="h-14 w-14 rounded-lg object-cover border"
          />
          <div className="flex-1">
            <p className="text-neutral-800 text-sm font-semibold">{file.name}</p>
            <p className="text-[10px] text-neutral-500">
              {(file.size / 1024).toFixed(1)} KB
            </p>
          </div>
          <button
            onClick={() => onChange(null)}
            className="text-neutral-600 hover:text-red-600 transition font-bold text-xl px-2"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-12"
    >
      {/* LEFT SIDE FORM */}
      <div>
        <h2 className="text-2xl font-semibold mb-1">Create Event</h2>
        <p className="text-neutral-600 text-sm mb-4">
          Configure event details, rounds, and media.
        </p>

        {submitMessage && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className={`mb-4 p-3 rounded-lg text-sm border ${
              submitStatus === "success"
                ? "bg-green-100 text-green-700 border-green-300"
                : "bg-red-100 text-red-700 border-red-300"
            }`}
          >
            {submitMessage}
          </motion.div>
        )}

        <form onSubmit={handleSubmit} className="space-y-10">

          {/* EVENT DETAILS */}
          <section className="space-y-4">
            <h3 className="text-lg font-semibold">Event Details</h3>

            <input
              className="w-full rounded-xl border border-neutral-300 px-3 py-2 text-sm shadow-sm"
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="Event Name"
            />
            {errors.name && <p className="text-xs text-red-600">{errors.name}</p>}

            <input
              type="date"
              className="w-full rounded-xl border border-neutral-300 px-3 py-2 text-sm shadow-sm"
              value={form.date}
              onChange={(e) => update("date", e.target.value)}
            />
            {errors.date && <p className="text-xs text-red-600">{errors.date}</p>}

            <input
              type="date"
              className="w-full rounded-xl border border-neutral-300 px-3 py-2 text-sm shadow-sm"
              value={form.registrationDeadline}
              onChange={(e) => update("registrationDeadline", e.target.value)}
            />
            {errors.registrationDeadline && (
              <p className="text-xs text-red-600">{errors.registrationDeadline}</p>
            )}

            <input
              className="w-full rounded-xl border border-neutral-300 px-3 py-2 text-sm shadow-sm"
              value={form.summary}
              onChange={(e) => update("summary", e.target.value)}
              placeholder="Short summary"
            />

            <textarea
              className="w-full rounded-xl border border-neutral-300 px-3 py-2 text-sm shadow-sm min-h-[100px]"
              value={form.description}
              onChange={(e) => update("description", e.target.value)}
              placeholder="Detailed description"
            />
          </section>

          <div className="h-[1px] bg-neutral-200" />

          {/* CONFIG */}
          <section className="space-y-4">
            <h3 className="text-lg font-semibold">Configuration</h3>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <input
                type="number"
                className="rounded-xl border border-neutral-300 px-3 py-2 text-sm shadow-sm"
                value={form.prize}
                onChange={(e) => update("prize", e.target.value)}
                placeholder="Prize (₹)"
              />
              {errors.prize && <p className="text-xs text-red-600">{errors.prize}</p>}

              <input
                type="number"
                className="rounded-xl border border-neutral-300 px-3 py-2 text-sm shadow-sm"
                value={form.maxTeams}
                onChange={(e) => update("maxTeams", e.target.value)}
                placeholder="Max Teams"
              />
              {errors.maxTeams && (
                <p className="text-xs text-red-600">{errors.maxTeams}</p>
              )}

              <div className="flex items-center gap-2">
                <input
                  type="number"
                  className="w-20 rounded-xl border border-neutral-300 px-3 py-2 text-sm shadow-sm"
                  value={form.minMembers}
                  onChange={(e) => update("minMembers", e.target.value)}
                  placeholder="Min"
                />
                <span className="text-xs text-neutral-500">to</span>
                <input
                  type="number"
                  className="w-20 rounded-xl border border-neutral-300 px-3 py-2 text-sm shadow-sm"
                  value={form.maxMembers}
                  onChange={(e) => update("maxMembers", e.target.value)}
                  placeholder="Max"
                />
              </div>
              {errors.minMembers && (
                <p className="text-xs text-red-600">{errors.minMembers}</p>
              )}
            </div>
          </section>

          <div className="h-[1px] bg-neutral-200" />

          {/* MEDIA */}
          <section className="space-y-4">
            <h3 className="text-lg font-semibold">Media</h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FileInput
                label="Upload Banner"
                file={form.bannerFile}
                onChange={(f) => update("bannerFile", f)}
              />
              <FileInput
                label="Upload Logo"
                file={form.logoFile}
                onChange={(f) => update("logoFile", f)}
              />
            </div>
          </section>

          <div className="h-[1px] bg-neutral-200" />

          {/* ROUNDS */}
          <section className="space-y-2">
            <h3 className="text-lg font-semibold">Rounds</h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              {ROUND_TYPES.map((round) => {
                const selected = form.rounds.some((r) => r.id === round.id);

                return (
                  <motion.div
                    key={round.id}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => toggleRound(round.id)}
                    className={`p-4 border rounded-xl cursor-pointer flex flex-col gap-2 shadow-sm transition ${
                      selected
                        ? "bg-neutral-900 border-neutral-900 text-white"
                        : "bg-white border-neutral-200 hover:bg-neutral-100"
                    }`}
                  >
                    {round.icon}
                    <span className="text-sm font-medium">{round.label}</span>
                  </motion.div>
                );
              })}
            </div>

            {errors.rounds && (
              <p className="text-xs text-red-600">{errors.rounds}</p>
            )}

            {form.rounds.map((r) => {
              const roundData = ROUND_TYPES.find((x) => x.id === r.id);

              return (
                <div
                  key={r.id}
                  className="border border-neutral-200 rounded-xl p-4 bg-neutral-50 mb-3"
                >
                  <p className="text-xs font-semibold text-neutral-700 mb-2 flex items-center gap-2">
                    {roundData.icon} {roundData.label} Instructions
                  </p>

                  <textarea
                    className="w-full rounded-xl border border-neutral-300 px-3 py-2 text-xs min-h-[70px]"
                    value={r.description}
                    onChange={(e) =>
                      updateRoundDescription(r.id, e.target.value)
                    }
                    placeholder="Judging criteria, submission instructions..."
                  />
                </div>
              );
            })}
          </section>

          <motion.button
            type="submit"
            whileTap={{ scale: 0.96 }}
            className="mt-2 rounded-xl bg-neutral-900 text-white px-6 py-3 text-sm shadow hover:bg-black transition"
            disabled={submitStatus === "loading"}
          >
            {submitStatus === "loading"
              ? "Saving..."
              : submitStatus === "success"
              ? "Saved!"
              : "Save Event"}
          </motion.button>
        </form>
      </div>

      {/* RIGHT AI PANEL */}
      <div className="lg:border-l lg:border-neutral-200 lg:pl-8">
        <h3 className="text-sm font-semibold mb-2">AI Event Builder</h3>
        <p className="text-xs text-neutral-600 mb-3">
          Describe your event and AI will pre-fill details.
        </p>

        <textarea
          className="w-full rounded-xl border border-neutral-300 px-3 py-2 text-sm min-h-[110px]"
          value={aiPrompt}
          onChange={(e) => setAiPrompt(e.target.value)}
        />

        <button
          onClick={handleAiGenerate}
          disabled={!aiPrompt.trim() || aiLoading}
          className="mt-3 rounded-xl border border-neutral-300 px-4 py-2 text-sm hover:bg-neutral-100 disabled:opacity-40"
        >
          {aiLoading ? "Generating..." : "Generate with AI"}
        </button>
      </div>
    </motion.div>
  );
}
