"use client";

import { useState, type FormEvent } from "react";
import type { PendingClarify } from "@/lib/conversation";

interface Props {
  pending: PendingClarify;
  sessionId: string | null;
  onSubmit?: (
    sessionId: string,
    questionId: string,
    answers: { id: string; selected: string[]; custom?: string }[],
  ) => Promise<void>;
}

export default function ClarifyCard({ pending, sessionId, onSubmit }: Props) {
  const locked = pending.answers != null;
  const [sent, setSent] = useState(locked);
  const [selected, setSelected] = useState<Record<string, string[]>>(() => {
    const initial: Record<string, string[]> = {};
    for (const answer of pending.answers ?? []) initial[answer.id] = answer.selected;
    return initial;
  });
  const [custom, setCustom] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const answer of pending.answers ?? []) initial[answer.id] = answer.custom ?? "";
    return initial;
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  function toggle(id: string, option: string, allowMultiple: boolean) {
    setSelected((current) => {
      const chosen = current[id] ?? [];
      if (!allowMultiple) return { ...current, [id]: [option] };
      return {
        ...current,
        [id]: chosen.includes(option) ? chosen.filter((item) => item !== option) : [...chosen, option],
      };
    });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (locked || submitting || !sessionId || !onSubmit) return;
    const answers = pending.questions.map((question) => {
      const choice = selected[question.id] ?? [];
      const note = (custom[question.id] ?? "").trim();
      return { id: question.id, selected: choice, ...(note ? { custom: note } : {}) };
    });
    if (answers.some((answer) => answer.selected.length === 0 && !answer.custom)) {
      setError("每题至少选择一项，或写一句补充。");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      await onSubmit(sessionId, pending.questionId, answers);
      setSent(true);
    } catch (err) {
      setSubmitting(false);
      setError(err instanceof Error ? err.message : "提交失败，请重试。");
    }
  }

  const disabled = locked || sent || submitting;

  return (
    <form onSubmit={submit} className="mb-4 rounded-xl border border-line bg-surface px-4 py-3" aria-label="需要补充条件">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-[13px] font-medium text-ink">需要补充条件</p>
        <span className="text-[11px] text-ink-faint">{locked || sent ? "已提交" : "研究已暂停"}</span>
      </div>
      <fieldset disabled={disabled} className="space-y-4 disabled:opacity-80">
        {pending.questions.map((question) => {
          const choice = selected[question.id] ?? [];
          return (
            <div key={question.id}>
              <p className="mb-2 text-[13px] text-ink">{question.prompt}</p>
              <div className="space-y-1.5">
                {question.options.map((option) => (
                  <label key={option} className="flex items-start gap-2 text-[13px] text-ink-dim">
                    <input
                      className="mt-0.5"
                      type={question.allowMultiple ? "checkbox" : "radio"}
                      name={question.id}
                      value={option}
                      checked={choice.includes(option)}
                      onChange={() => toggle(question.id, option, question.allowMultiple)}
                    />
                    <span>{option}</span>
                  </label>
                ))}
              </div>
              <input
                className="mt-2 w-full rounded-lg border border-line bg-paper px-2.5 py-1.5 text-[13px] text-ink"
                placeholder="补充（可选）"
                value={custom[question.id] ?? ""}
                onChange={(event) => setCustom((current) => ({ ...current, [question.id]: event.target.value }))}
              />
            </div>
          );
        })}
      </fieldset>
      {error && <p className="mt-2 text-[12px] text-err">{error}</p>}
      {!locked && !sent && (
        <button
          type="submit"
          disabled={disabled || !sessionId || !onSubmit}
          className="mt-3 rounded-lg bg-accent px-3 py-1.5 text-[13px] text-white disabled:opacity-50"
        >
          {submitting ? "提交中…" : "提交并继续"}
        </button>
      )}
    </form>
  );
}
